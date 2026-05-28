"""Pydantic models for the realtime redaction session domain."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Session id pattern: <YYYYMMDDHHMMSS>-<6..12 url-safe chars>
SESSION_ID_REGEX = r"^[0-9]{14}-[A-Za-z0-9]{6,12}$"

StorageMode = Literal["redacted_only", "originals_stored"]
SessionStatus = Literal["recording", "finalized", "errored"]


class AuditEvent(BaseModel):
    """Single audit-trail entry appended to a session manifest."""

    type: str
    at: datetime
    detail: dict = Field(default_factory=dict)


class SessionManifest(BaseModel):
    """Source-of-truth descriptor for a session bundle in B2.

    Always written to `sessions/<YYYY>/<MM>/<id>/manifest.json` at
    finalize. Auditors compare derived state (object presence + the
    sha256 hashes here) against the redacted transcript.
    """

    session_id: str = Field(pattern=SESSION_ID_REGEX)
    created_at: datetime
    finalized_at: datetime | None = None
    status: SessionStatus = "recording"
    storage_mode: StorageMode
    store_original_audio: bool
    store_original_transcript: bool
    redaction_modes: list[str]
    model: str
    duration_ms: int = 0
    audio_bytes_received: int = 0
    segment_count: int = 0
    detection_count: int = 0
    detection_counts_by_severity: dict[str, int] = Field(default_factory=dict)
    original_text_sha256: str | None = None
    redacted_text_sha256: str | None = None
    audio_extension: str | None = None
    events: list[AuditEvent] = Field(default_factory=list)


class SessionSummary(BaseModel):
    """Library-row shape — what /sessions renders per session."""

    session_id: str
    created_at: datetime
    finalized_at: datetime | None
    status: SessionStatus
    storage_mode: StorageMode
    duration_ms: int
    detection_count: int
    detection_counts_by_severity: dict[str, int]
    segment_count: int
    has_audio: bool
    has_original_transcript: bool


class SessionStartRequest(BaseModel):
    """Body for POST /sessions — overrides for per-session toggles."""

    redaction_modes: list[str] | None = None
    store_original_audio: bool | None = None
    store_original_transcript: bool | None = None


class SessionStartResponse(BaseModel):
    session_id: str
    created_at: datetime
    storage_mode: StorageMode
    redaction_modes: list[str]
    model: str


class SessionStats(BaseModel):
    total_sessions: int
    total_duration_ms: int
    total_detections: int
    detections_by_severity: dict[str, int]
    sessions_today: int
    storage_mode_counts: dict[str, int]


class DailySessionCount(BaseModel):
    date: str
    sessions: int
    detections: int
