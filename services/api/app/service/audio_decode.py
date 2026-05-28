"""Decode uploaded audio files to PCM16 24 kHz mono for the realtime pipeline.

OpenAI Realtime requires PCM16 mono at 24 kHz. The browser-side
AudioWorklet already produces exactly that format for `/record`; this
module handles the file-mode path used by `/upload`: take an uploaded
audio file, normalize it to the same wire format, and yield framed
chunks the bridge can `send_audio` exactly like a live mic stream.

v1 supports WAV (PCM16 / PCM 8-bit / float32, any sample rate, mono or
stereo). MP3, WebM, M4A and OGG are documented as a v2 expansion — they
need a heavy native decoder (ffmpeg / pyav) and would balloon the
sample's dependency footprint. The `/upload` page surfaces this
constraint up front; the realtime ingest path 415s anything else.

Layering: pure decoding. No boto3, no FastAPI, no network. Lives in
`service/` because the result feeds the same `RealtimeSessionState`
state machine the live bridge uses.
"""

from __future__ import annotations

import audioop
import io
import logging
import wave
from collections.abc import Iterator
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# OpenAI Realtime wire format — must match `repo/openai_realtime_client.py`.
TARGET_SAMPLE_RATE = 24_000
TARGET_SAMPLE_WIDTH_BYTES = 2  # 16-bit
TARGET_CHANNELS = 1

# Stream chunks of ~100 ms of PCM16 at 24 kHz — small enough that
# transcript deltas come back interactively, large enough that we don't
# spam the upstream socket. 24,000 samples/s * 2 bytes/sample * 0.1 s.
DEFAULT_FRAME_BYTES = 4_800

# Pipeline-mode audio is capped at ~30 min to keep the synchronous
# request bounded. Anyone bumping into this should switch to /record.
MAX_DECODED_BYTES = 30 * 60 * TARGET_SAMPLE_RATE * TARGET_SAMPLE_WIDTH_BYTES


class AudioDecodeError(Exception):
    """Raised when the uploaded file cannot be decoded into PCM16 24 kHz mono."""

    def __init__(self, detail: str, status_code: int = 415):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


@dataclass
class DecodedAudio:
    pcm16: bytes
    sample_rate: int
    channels: int
    sample_width_bytes: int

    @property
    def duration_ms(self) -> int:
        bytes_per_second = self.sample_rate * self.channels * self.sample_width_bytes
        if bytes_per_second == 0:
            return 0
        return (len(self.pcm16) * 1000) // bytes_per_second


def _decode_wav(data: bytes) -> DecodedAudio:
    """Read a WAV container and produce raw PCM in the file's native format.

    Supports PCM16, PCM8 (unsigned), and 32-bit float WAV variants. The
    caller is responsible for resampling and downmixing afterwards.
    """
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
    except (wave.Error, EOFError) as e:
        raise AudioDecodeError(f"Could not parse WAV file: {e}") from None
    if sample_width not in (1, 2, 4):
        raise AudioDecodeError(
            f"Unsupported WAV sample width: {sample_width * 8}-bit"
        )
    # Float32 WAV: not a `wave` module audioop op — reject for now.
    # `wave.getsampwidth()` returns 4 for both PCM32 and FLOAT32; we don't
    # disambiguate the WAVE_FORMAT_EXTENSIBLE / IEEE_FLOAT compression
    # code from stdlib, so we 415 instead of guessing.
    if sample_width == 4:
        raise AudioDecodeError(
            "32-bit WAV is not supported in v1 — please convert to 16-bit PCM."
        )
    # Promote PCM8 (unsigned, 0..255) to PCM16 (signed, -32768..32767) so
    # the rest of the pipeline operates on a single width.
    if sample_width == 1:
        raw = audioop.lin2lin(raw, 1, 2)
        sample_width = 2
    return DecodedAudio(
        pcm16=raw,
        sample_rate=sample_rate,
        channels=channels,
        sample_width_bytes=sample_width,
    )


def _to_mono_pcm16(decoded: DecodedAudio) -> DecodedAudio:
    """Downmix multi-channel audio to mono PCM16."""
    if decoded.channels == 1:
        return decoded
    if decoded.channels != 2:
        raise AudioDecodeError(
            f"Unsupported channel count: {decoded.channels} (only mono / stereo)"
        )
    mono = audioop.tomono(decoded.pcm16, decoded.sample_width_bytes, 0.5, 0.5)
    return DecodedAudio(
        pcm16=mono,
        sample_rate=decoded.sample_rate,
        channels=1,
        sample_width_bytes=decoded.sample_width_bytes,
    )


def _resample_to_target(decoded: DecodedAudio) -> DecodedAudio:
    """Resample to TARGET_SAMPLE_RATE using audioop.ratecv (linear)."""
    if decoded.sample_rate == TARGET_SAMPLE_RATE:
        return decoded
    converted, _ = audioop.ratecv(
        decoded.pcm16,
        decoded.sample_width_bytes,
        decoded.channels,
        decoded.sample_rate,
        TARGET_SAMPLE_RATE,
        None,
    )
    return DecodedAudio(
        pcm16=converted,
        sample_rate=TARGET_SAMPLE_RATE,
        channels=decoded.channels,
        sample_width_bytes=decoded.sample_width_bytes,
    )


def decode_to_pcm16_24khz_mono(data: bytes, content_type: str) -> DecodedAudio:
    """Decode an uploaded audio file to PCM16 24 kHz mono.

    v1 accepts WAV only. Other formats are rejected with a 415 so the
    pipeline-mode `/upload` is honest about its scope.
    """
    if not data:
        raise AudioDecodeError("Empty file", status_code=400)
    # Strip MIME parameters like `; codecs=1` that Chrome / Firefox attach
    # to recorded blobs. The allowlist is exact-match on the bare type.
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct not in ("audio/wav", "audio/x-wav", "audio/wave"):
        raise AudioDecodeError(
            "Pipeline-mode upload accepts WAV only in v1. "
            "Use /record for live capture, or convert your file to "
            "16-bit PCM WAV before uploading.",
            status_code=415,
        )
    decoded = _decode_wav(data)
    decoded = _to_mono_pcm16(decoded)
    decoded = _resample_to_target(decoded)
    if len(decoded.pcm16) > MAX_DECODED_BYTES:
        raise AudioDecodeError(
            "Decoded audio exceeds the 30-minute pipeline cap. "
            "Split the file or use /record.",
            status_code=413,
        )
    return decoded


def iter_frames(
    pcm16: bytes, frame_bytes: int = DEFAULT_FRAME_BYTES
) -> Iterator[bytes]:
    """Yield fixed-size PCM16 frames suitable for `send_audio_chunk`."""
    if frame_bytes <= 0:
        raise ValueError("frame_bytes must be > 0")
    for offset in range(0, len(pcm16), frame_bytes):
        yield pcm16[offset : offset + frame_bytes]
