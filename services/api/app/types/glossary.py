"""Custom-glossary types — case-insensitive whole-word redaction terms."""

from typing import Literal

from pydantic import BaseModel, Field

GlossarySeverity = Literal["low", "medium", "high"]


class GlossaryTerm(BaseModel):
    term: str
    severity: GlossarySeverity = "low"
    label: str | None = None  # optional category override


class Glossary(BaseModel):
    version: int = 1
    terms: list[GlossaryTerm] = Field(default_factory=list)
