"""Pydantic models for the layered redaction engine."""

from typing import Literal

from pydantic import BaseModel, Field

DetectorSource = Literal["pii", "secrets", "glossary"]
DetectionSeverity = Literal["low", "medium", "high"]


class Detection(BaseModel):
    """One redacted span surfaced by a detector layer."""

    segment_index: int
    start: int  # character offset within the segment text
    end: int
    detector: DetectorSource
    type: str  # e.g. "email", "ssn", "aws_access_key", "glossary:foo"
    severity: DetectionSeverity
    original_length: int


class RedactionResult(BaseModel):
    """Output of applying detectors to a single segment."""

    segment_index: int
    original_text: str
    redacted_text: str
    detections: list[Detection] = Field(default_factory=list)


class RedactionManifest(BaseModel):
    """The full audit trail of every detection in a session.

    Persisted to `sessions/<YYYY>/<MM>/<id>/redactions.json` on finalize.
    """

    session_id: str
    modes: list[str]
    detections: list[Detection] = Field(default_factory=list)
    counts_by_type: dict[str, int] = Field(default_factory=dict)
    counts_by_severity: dict[str, int] = Field(default_factory=dict)
