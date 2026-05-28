"""Unit tests for the export renderers (TXT / SRT / VTT)."""

from app.service.exports import _render_srt, _render_txt, _render_vtt
from app.types.transcripts import TranscriptSegment


def _segs() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            index=0, started_at_ms=0, ended_at_ms=2000, text="hello world"
        ),
        TranscriptSegment(
            index=1, started_at_ms=2500, ended_at_ms=5500, text="line two"
        ),
    ]


def test_txt_render_one_per_line():
    out = _render_txt(_segs())
    assert out.startswith("hello world")
    assert "line two" in out


def test_srt_uses_comma_separator():
    out = _render_srt(_segs())
    assert "00:00:00,000 --> 00:00:02,000" in out
    assert "00:00:02,500 --> 00:00:05,500" in out
    assert out.startswith("1\n")


def test_vtt_starts_with_header():
    out = _render_vtt(_segs())
    assert out.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:02.000" in out
