"""Session orchestration: id generation, manifest IO, library list, delete.

This module is the source-of-truth boundary between routes and the
session-bundle layout in B2. Realtime stream processing lives in
`service/realtime_session.py`; this file handles the
non-streaming control-plane operations.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.repo import b2_sessions
from app.types.sessions import (
    SESSION_ID_REGEX,
    AuditEvent,
    DailySessionCount,
    SessionManifest,
    SessionStartRequest,
    SessionStartResponse,
    SessionStats,
    SessionSummary,
)
from app.types.transcripts import Transcript

logger = logging.getLogger(__name__)

_SESSION_ID_RE = re.compile(SESSION_ID_REGEX)
ID_SUFFIX_LENGTH = 8


class SessionError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def generate_session_id(now: datetime | None = None) -> str:
    """Return `<YYYYMMDDHHMMSS>-<8-url-safe-chars>`."""
    ts = (now or datetime.now(UTC)).strftime("%Y%m%d%H%M%S")
    suffix = secrets.token_urlsafe(8)[:ID_SUFFIX_LENGTH]
    # token_urlsafe can include `_` / `-` — restrict to alnum for the regex.
    suffix = re.sub(r"[^A-Za-z0-9]", "0", suffix)
    return f"{ts}-{suffix}"


def validate_session_id(session_id: str) -> None:
    if not _SESSION_ID_RE.fullmatch(session_id):
        raise SessionError("Invalid session id format")


def _resolve_modes(requested: list[str] | None) -> list[str]:
    if requested is None:
        return settings.redaction_default_mode_list
    valid = {"pii", "secrets", "glossary"}
    cleaned = [m.strip().lower() for m in requested if m.strip()]
    return [m for m in cleaned if m in valid]


def start_session(req: SessionStartRequest) -> SessionStartResponse:
    """Create a new session manifest stub and persist it to B2."""
    sid = generate_session_id()
    modes = _resolve_modes(req.redaction_modes)
    default_store = settings.session_store_originals_default
    store_audio = (
        req.store_original_audio
        if req.store_original_audio is not None
        else default_store
    )
    store_transcript = (
        req.store_original_transcript
        if req.store_original_transcript is not None
        else default_store
    )
    storage_mode = (
        "originals_stored" if (store_audio or store_transcript) else "redacted_only"
    )
    now = datetime.now(UTC)
    manifest = SessionManifest(
        session_id=sid,
        created_at=now,
        storage_mode=storage_mode,
        store_original_audio=store_audio,
        store_original_transcript=store_transcript,
        redaction_modes=modes,
        model=settings.openai_realtime_model,
        events=[
            AuditEvent(
                type="session.started",
                at=now,
                detail={
                    "redaction_modes": modes,
                    "storage_mode": storage_mode,
                },
            )
        ],
    )
    b2_sessions.put_manifest(manifest)
    return SessionStartResponse(
        session_id=sid,
        created_at=now,
        storage_mode=storage_mode,
        redaction_modes=modes,
        model=settings.openai_realtime_model,
    )


def get_session(session_id: str) -> SessionManifest:
    validate_session_id(session_id)
    manifest = b2_sessions.get_manifest(session_id)
    if manifest is None:
        raise SessionError("Session not found", status_code=404)
    return manifest


def get_redacted_transcript(session_id: str) -> Transcript:
    """Return the redacted transcript bundle for the detail view.

    Raises `SessionError(404)` via `get_session` if the session doesn't
    exist. A finalized session always has a redacted transcript, but a
    session with zero completed segments writes an empty one — return an
    empty `Transcript` rather than 404 so the detail page renders cleanly.
    """
    get_session(session_id)
    raw = b2_sessions.get_transcript_redacted(session_id)
    if raw is None:
        return Transcript(session_id=session_id, variant="redacted", segments=[])
    return Transcript(**raw)


def list_session_summaries(limit: int = 100) -> list[SessionSummary]:
    """List sessions newest-first with derived state."""
    if limit < 1 or limit > 1000:
        raise ValueError("Limit must be between 1 and 1000")
    sids = b2_sessions.list_sessions()
    head_state = b2_sessions.head_session_state_parallel(sids[:limit])
    summaries: list[SessionSummary] = []
    for sid in sids[:limit]:
        manifest = b2_sessions.get_manifest(sid)
        if manifest is None:
            continue
        state = head_state.get(sid, {"has_audio": False, "has_original_transcript": False})
        summaries.append(
            SessionSummary(
                session_id=manifest.session_id,
                created_at=manifest.created_at,
                finalized_at=manifest.finalized_at,
                status=manifest.status,
                storage_mode=manifest.storage_mode,
                duration_ms=manifest.duration_ms,
                detection_count=manifest.detection_count,
                detection_counts_by_severity=manifest.detection_counts_by_severity,
                segment_count=manifest.segment_count,
                has_audio=bool(state["has_audio"]),
                has_original_transcript=bool(state["has_original_transcript"]),
            )
        )
    summaries.sort(key=lambda s: s.created_at, reverse=True)
    return summaries


def delete_session(session_id: str) -> int:
    """Cascade-delete every object under the session prefix."""
    validate_session_id(session_id)
    return b2_sessions.delete_session(session_id)


def get_session_stats() -> SessionStats:
    """Aggregate metrics for the dashboard."""
    summaries = list_session_summaries(limit=1000)
    total_detections = sum(s.detection_count for s in summaries)
    by_severity: dict[str, int] = defaultdict(int)
    storage_counts: dict[str, int] = defaultdict(int)
    today = datetime.now(UTC).date()
    sessions_today = 0
    total_duration = 0
    for s in summaries:
        for sev, count in s.detection_counts_by_severity.items():
            by_severity[sev] += count
        storage_counts[s.storage_mode] += 1
        if s.created_at.date() == today:
            sessions_today += 1
        total_duration += s.duration_ms
    return SessionStats(
        total_sessions=len(summaries),
        total_duration_ms=total_duration,
        total_detections=total_detections,
        detections_by_severity=dict(by_severity),
        sessions_today=sessions_today,
        storage_mode_counts=dict(storage_counts),
    )


def get_session_activity(days: int = 7) -> list[DailySessionCount]:
    """Daily sessions + detections — drives the dashboard chart."""
    summaries = list_session_summaries(limit=1000)
    today = datetime.now(UTC).date()
    cutoff = today - timedelta(days=days - 1)
    session_counts: dict[str, int] = defaultdict(int)
    detection_counts: dict[str, int] = defaultdict(int)
    for s in summaries:
        d = s.created_at.date()
        if d >= cutoff:
            session_counts[d.isoformat()] += 1
            detection_counts[d.isoformat()] += s.detection_count
    return [
        DailySessionCount(
            date=(cutoff + timedelta(days=i)).isoformat(),
            sessions=session_counts.get(
                (cutoff + timedelta(days=i)).isoformat(), 0
            ),
            detections=detection_counts.get(
                (cutoff + timedelta(days=i)).isoformat(), 0
            ),
        )
        for i in range(days)
    ]
