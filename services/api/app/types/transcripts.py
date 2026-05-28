"""Transcript segment / variant types."""

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    """One finalized utterance from the realtime transcription stream."""

    index: int
    started_at_ms: int
    ended_at_ms: int
    text: str


class Transcript(BaseModel):
    """An ordered list of finalized segments.

    Two variants are persisted (or not, depending on storage mode):
      - transcript.redacted.json — always written
      - transcript.original.json — written only on opt-in
    """

    session_id: str
    variant: str  # "redacted" or "original"
    segments: list[TranscriptSegment] = Field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments)
