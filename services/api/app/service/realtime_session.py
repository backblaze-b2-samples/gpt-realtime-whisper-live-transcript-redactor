"""Per-session state machine for realtime transcription + redaction.

States: started -> streaming -> segment_completed (repeats) -> finalized

The runtime WebSocket bridge (`runtime/realtime.py`) instantiates a
`RealtimeSessionState` for each connected session and calls the methods
defined here. This module does NOT touch sockets — it just coordinates
redaction, manifest mutation, and B2 persistence.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from app.repo import b2_sessions
from app.service import redaction as redaction_svc
from app.service.glossary import load_glossary
from app.service.sessions import get_session
from app.types.glossary import Glossary
from app.types.redaction import Detection
from app.types.sessions import AuditEvent, SessionManifest
from app.types.transcripts import TranscriptSegment

logger = logging.getLogger(__name__)


class RealtimeSessionState:
    """Mutable state held by the bridge for one active session."""

    def __init__(self, session_id: str) -> None:
        self.manifest: SessionManifest = get_session(session_id)
        self.original_segments: list[TranscriptSegment] = []
        self.redacted_segments: list[TranscriptSegment] = []
        self.all_detections: list[Detection] = []
        self.audio_bytes: bytearray = bytearray()
        self.glossary: Glossary | None = (
            load_glossary() if "glossary" in self.manifest.redaction_modes else None
        )
        self._next_index = 0
        # Append the streaming-start audit event in-memory; persisted on finalize.
        self.manifest.events.append(
            AuditEvent(type="streaming.started", at=datetime.now(UTC), detail={})
        )

    def append_audio_chunk(self, chunk: bytes) -> None:
        """Buffer raw PCM if originals are being stored; always track bytes."""
        self.manifest.audio_bytes_received += len(chunk)
        if self.manifest.store_original_audio:
            self.audio_bytes.extend(chunk)

    def add_completed_segment(self, text: str, duration_ms: int) -> dict:
        """Run redaction on a finalized utterance and emit the UI payload.

        Returns the JSON-serializable event the bridge will forward to the
        browser. Side effects: mutate manifest, append segments, audit event.
        """
        index = self._next_index
        self._next_index += 1

        result = redaction_svc.redact_segment(
            text,
            segment_index=index,
            modes=self.manifest.redaction_modes,
            glossary=self.glossary,
        )

        started_at_ms = self.manifest.duration_ms
        ended_at_ms = started_at_ms + max(0, duration_ms)
        self.manifest.duration_ms = ended_at_ms
        self.manifest.segment_count = index + 1

        self.original_segments.append(
            TranscriptSegment(
                index=index,
                started_at_ms=started_at_ms,
                ended_at_ms=ended_at_ms,
                text=result.original_text,
            )
        )
        self.redacted_segments.append(
            TranscriptSegment(
                index=index,
                started_at_ms=started_at_ms,
                ended_at_ms=ended_at_ms,
                text=result.redacted_text,
            )
        )
        self.all_detections.extend(result.detections)
        self.manifest.detection_count += len(result.detections)
        for det in result.detections:
            self.manifest.detection_counts_by_severity[det.severity] = (
                self.manifest.detection_counts_by_severity.get(det.severity, 0) + 1
            )

        original_hash = hashlib.sha256(result.original_text.encode("utf-8")).hexdigest()
        self.manifest.events.append(
            AuditEvent(
                type="transcript.completed",
                at=datetime.now(UTC),
                detail={"segment_index": index, "original_text_sha256": original_hash},
            )
        )
        if result.detections:
            self.manifest.events.append(
                AuditEvent(
                    type="redaction.applied",
                    at=datetime.now(UTC),
                    detail={
                        "segment_index": index,
                        "count": len(result.detections),
                        "types": sorted({d.type for d in result.detections}),
                    },
                )
            )

        return {
            "type": "segment",
            "segment": {
                "index": index,
                "started_at_ms": started_at_ms,
                "ended_at_ms": ended_at_ms,
                "redacted_text": result.redacted_text,
            },
            "detections": [d.model_dump() for d in result.detections],
        }

    def finalize(self, audio_extension: str | None = "webm") -> SessionManifest:
        """Persist redacted bundle (+ originals on opt-in) and seal the manifest."""
        now = datetime.now(UTC)
        sid = self.manifest.session_id

        redacted_payload = {
            "session_id": sid,
            "variant": "redacted",
            "segments": [s.model_dump() for s in self.redacted_segments],
        }
        b2_sessions.put_transcript_redacted(sid, redacted_payload)
        redacted_text = " ".join(s.text for s in self.redacted_segments)
        self.manifest.redacted_text_sha256 = hashlib.sha256(
            redacted_text.encode("utf-8")
        ).hexdigest()

        manifest_payload = redaction_svc.build_manifest(
            sid, self.manifest.redaction_modes, self.all_detections
        )
        b2_sessions.put_redactions(sid, manifest_payload.model_dump(mode="json"))

        if self.manifest.store_original_transcript:
            original_payload = {
                "session_id": sid,
                "variant": "original",
                "segments": [s.model_dump() for s in self.original_segments],
            }
            b2_sessions.put_transcript_original(sid, original_payload)
            original_text = " ".join(s.text for s in self.original_segments)
            self.manifest.original_text_sha256 = hashlib.sha256(
                original_text.encode("utf-8")
            ).hexdigest()

        if self.manifest.store_original_audio and self.audio_bytes and audio_extension:
            b2_sessions.put_audio(sid, audio_extension, bytes(self.audio_bytes))
            self.manifest.audio_extension = audio_extension

        self.manifest.finalized_at = now
        self.manifest.status = "finalized"
        self.manifest.events.append(
            AuditEvent(
                type="session.finalized",
                at=now,
                detail={
                    "segment_count": self.manifest.segment_count,
                    "detection_count": self.manifest.detection_count,
                },
            )
        )
        b2_sessions.put_manifest(self.manifest)
        return self.manifest

    def mark_errored(self, message: str) -> None:
        self.manifest.status = "errored"
        self.manifest.events.append(
            AuditEvent(
                type="session.errored",
                at=datetime.now(UTC),
                detail={"message": message},
            )
        )
        b2_sessions.put_manifest(self.manifest)
