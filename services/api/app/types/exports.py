"""Export format types — redacted-only TXT, SRT, VTT."""

from typing import Literal

from pydantic import BaseModel

ExportFormat = Literal["txt", "srt", "vtt"]


class ExportRequest(BaseModel):
    format: ExportFormat


class ExportInfo(BaseModel):
    session_id: str
    format: ExportFormat
    key: str
    size_bytes: int
    url: str | None = None
