"""Generate redacted-only TXT / SRT / VTT exports for a session bundle."""

from __future__ import annotations

from datetime import UTC, datetime

from app.repo import b2_sessions
from app.repo.b2_client import get_presigned_url
from app.service.sessions import get_session, validate_session_id
from app.types.exports import ExportFormat, ExportInfo
from app.types.sessions import AuditEvent
from app.types.transcripts import Transcript, TranscriptSegment


def _load_redacted(session_id: str) -> Transcript:
    raw = b2_sessions.get_transcript_redacted(session_id)
    if raw is None:
        return Transcript(session_id=session_id, variant="redacted", segments=[])
    return Transcript(**raw)


def _format_timestamp(ms: int, separator: str) -> str:
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, milliseconds = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{milliseconds:03d}"


def _render_txt(segments: list[TranscriptSegment]) -> str:
    return "\n".join(s.text for s in segments) + ("\n" if segments else "")


def _render_srt(segments: list[TranscriptSegment]) -> str:
    parts: list[str] = []
    for i, s in enumerate(segments, start=1):
        parts.append(str(i))
        parts.append(
            f"{_format_timestamp(s.started_at_ms, ',')} --> "
            f"{_format_timestamp(s.ended_at_ms, ',')}"
        )
        parts.append(s.text)
        parts.append("")
    return "\n".join(parts)


def _render_vtt(segments: list[TranscriptSegment]) -> str:
    parts: list[str] = ["WEBVTT", ""]
    for s in segments:
        parts.append(
            f"{_format_timestamp(s.started_at_ms, '.')} --> "
            f"{_format_timestamp(s.ended_at_ms, '.')}"
        )
        parts.append(s.text)
        parts.append("")
    return "\n".join(parts)


_RENDERERS = {
    "txt": _render_txt,
    "srt": _render_srt,
    "vtt": _render_vtt,
}


def generate_export(session_id: str, fmt: ExportFormat) -> ExportInfo:
    validate_session_id(session_id)
    manifest = get_session(session_id)
    transcript = _load_redacted(session_id)
    body = _RENDERERS[fmt](transcript.segments)
    key = b2_sessions.put_export(session_id, fmt, body)

    # Append an audit event in-place; persist the manifest so the audit
    # trail reflects the export.
    manifest.events.append(
        AuditEvent(
            type="export.generated",
            at=datetime.now(UTC),
            detail={"format": fmt, "key": key, "size_bytes": len(body.encode("utf-8"))},
        )
    )
    b2_sessions.put_manifest(manifest)

    url = get_presigned_url(key, filename=f"{session_id}.{fmt}")
    return ExportInfo(
        session_id=session_id,
        format=fmt,
        key=key,
        size_bytes=len(body.encode("utf-8")),
        url=url,
    )
