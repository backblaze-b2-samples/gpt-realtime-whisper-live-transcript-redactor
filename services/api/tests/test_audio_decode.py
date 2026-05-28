"""Tests for the WAV -> PCM16 24 kHz mono decoder used by the
pipeline-mode `/sessions/upload` endpoint."""

import io
import struct
import wave

import pytest

from app.service.audio_decode import (
    DEFAULT_FRAME_BYTES,
    TARGET_SAMPLE_RATE,
    AudioDecodeError,
    decode_to_pcm16_24khz_mono,
    iter_frames,
)


def _wav_bytes(
    sample_rate: int,
    channels: int,
    sample_width: int,
    frames: bytes,
) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(frames)
    return buf.getvalue()


def test_decodes_pcm16_24khz_mono_passthrough():
    # 100 ms of silence at the target format.
    frames = b"\x00\x00" * (TARGET_SAMPLE_RATE // 10)
    data = _wav_bytes(TARGET_SAMPLE_RATE, 1, 2, frames)
    out = decode_to_pcm16_24khz_mono(data, "audio/wav")
    assert out.sample_rate == TARGET_SAMPLE_RATE
    assert out.channels == 1
    assert out.sample_width_bytes == 2
    # 100 ms ~= 4800 bytes
    assert 4500 < len(out.pcm16) <= 4800
    assert 90 <= out.duration_ms <= 110


def test_resamples_from_48khz():
    frames = b"\x01\x00" * 4_800  # 100 ms @ 48 kHz mono
    data = _wav_bytes(48_000, 1, 2, frames)
    out = decode_to_pcm16_24khz_mono(data, "audio/wav")
    assert out.sample_rate == TARGET_SAMPLE_RATE
    # 100 ms at 24 kHz mono = 4800 bytes (± a few from ratecv linear interp)
    assert 4500 <= len(out.pcm16) <= 4900


def test_downmixes_stereo_to_mono():
    # 100 ms stereo @ 24 kHz: interleaved L/R samples.
    n_samples = TARGET_SAMPLE_RATE // 10
    frames = (b"\x10\x00\x20\x00") * n_samples  # 4 bytes per stereo sample
    data = _wav_bytes(TARGET_SAMPLE_RATE, 2, 2, frames)
    out = decode_to_pcm16_24khz_mono(data, "audio/wav")
    assert out.channels == 1
    # Mono should be exactly half the stereo byte count.
    assert len(out.pcm16) == 4 * n_samples // 2


def test_promotes_8bit_to_16bit():
    # 100 ms of "silence" at 8-bit unsigned (mid value 128).
    frames = b"\x80" * (TARGET_SAMPLE_RATE // 10)
    data = _wav_bytes(TARGET_SAMPLE_RATE, 1, 1, frames)
    out = decode_to_pcm16_24khz_mono(data, "audio/wav")
    assert out.sample_width_bytes == 2
    assert out.channels == 1


def test_rejects_non_wav_content_type():
    frames = b"\x00\x00" * 1000
    data = _wav_bytes(TARGET_SAMPLE_RATE, 1, 2, frames)
    with pytest.raises(AudioDecodeError) as ei:
        decode_to_pcm16_24khz_mono(data, "audio/mpeg")
    assert ei.value.status_code == 415


def test_rejects_empty_file():
    with pytest.raises(AudioDecodeError) as ei:
        decode_to_pcm16_24khz_mono(b"", "audio/wav")
    assert ei.value.status_code == 400


def test_rejects_corrupt_wav_with_415():
    with pytest.raises(AudioDecodeError) as ei:
        decode_to_pcm16_24khz_mono(b"not a wav file", "audio/wav")
    assert ei.value.status_code == 415


def test_accepts_content_type_with_codecs_parameter():
    # Chrome / Firefox attach `; codecs=1` to recorded WAV blobs. The
    # allowlist must strip MIME parameters before matching.
    frames = b"\x00\x00" * (TARGET_SAMPLE_RATE // 10)
    data = _wav_bytes(TARGET_SAMPLE_RATE, 1, 2, frames)
    out = decode_to_pcm16_24khz_mono(data, "audio/wav; codecs=1")
    assert out.sample_rate == TARGET_SAMPLE_RATE
    assert out.channels == 1
    # And with a quoted parameter, with extra whitespace, and mixed case.
    out2 = decode_to_pcm16_24khz_mono(data, 'AUDIO/Wave;   codecs="1"')
    assert out2.sample_rate == TARGET_SAMPLE_RATE


def _wav_32bit_bytes(sample_rate: int, channels: int, n_samples: int) -> bytes:
    """Construct a minimal 32-bit PCM WAV file header by hand.

    `wave.open` only writes the basic PCM format; we build the bytes
    directly so the test fixture stays in-process and matches the existing
    `struct.pack` style asked for in the round-3 brief.
    """
    sample_width = 4  # 32-bit
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    data_size = n_samples * channels * sample_width
    fmt_chunk = struct.pack(
        "<4sIHHIIHH",
        b"fmt ",
        16,            # fmt chunk size
        1,             # PCM format code (1 = linear PCM)
        channels,
        sample_rate,
        byte_rate,
        block_align,
        sample_width * 8,
    )
    data_chunk = struct.pack("<4sI", b"data", data_size) + (b"\x00" * data_size)
    riff_size = 4 + len(fmt_chunk) + len(data_chunk)
    header = struct.pack("<4sI4s", b"RIFF", riff_size, b"WAVE")
    return header + fmt_chunk + data_chunk


def test_rejects_32bit_wav_with_415():
    # 100 ms of 32-bit silence @ 24 kHz mono.
    data = _wav_32bit_bytes(TARGET_SAMPLE_RATE, 1, TARGET_SAMPLE_RATE // 10)
    with pytest.raises(AudioDecodeError) as ei:
        decode_to_pcm16_24khz_mono(data, "audio/wav")
    assert ei.value.status_code == 415
    assert "32-bit" in ei.value.detail


def test_iter_frames_chunks_exactly():
    data = b"\x00" * (DEFAULT_FRAME_BYTES * 3 + 17)
    frames = list(iter_frames(data))
    assert len(frames) == 4
    assert all(len(f) == DEFAULT_FRAME_BYTES for f in frames[:3])
    assert len(frames[-1]) == 17


def test_iter_frames_rejects_zero_size():
    with pytest.raises(ValueError):
        list(iter_frames(b"abcd", frame_bytes=0))
