"""Detectors run against finalized transcript segments.

Layer 1: PII (LLM)          names, phones, emails, addresses, gov IDs, …
Layer 2: Secret patterns    (AWS / GitHub / OpenAI / Slack / JWT / Stripe)
Layer 3: Glossary           (case-insensitive whole-word match against B2)

Layers 2 and 3 are deterministic regex and return spans directly. Layer 1
is LLM-backed (`repo/openai_redactor.py`) because the input is transcribed
*speech* — PII arrives as natural language ("john at example dot com",
spelled-out numbers, plain names) that regex cannot match. Every detector
returns `list[Detection]` with character offsets relative to the segment
text. The orchestrator (`service/redaction.py`) merges and deduplicates
overlapping spans before substitution.
"""

from __future__ import annotations

import re

from app.repo import openai_redactor
from app.types.glossary import Glossary, GlossaryTerm
from app.types.redaction import Detection

# --- PII (LLM-backed) ------------------------------------------------------


async def detect_pii_llm(text: str, segment_index: int) -> list[Detection]:
    """Extract PII via the chat model, then map each verbatim span back to
    character offsets in `text`.

    The model is asked to return spans exactly as they appear, so we locate
    every occurrence with an exact (escaped) match. A span the model
    paraphrased and that therefore can't be found is dropped — we never
    redact a range we can't anchor in the original text.
    """
    entities = await openai_redactor.detect_pii_entities(text)
    out: list[Detection] = []
    for ent in entities:
        span = ent.text.strip()
        if not span:
            continue
        for m in re.finditer(re.escape(span), text):
            out.append(
                Detection(
                    segment_index=segment_index,
                    start=m.start(),
                    end=m.end(),
                    detector="pii",
                    type=ent.type,
                    severity=ent.severity,
                    original_length=m.end() - m.start(),
                )
            )
    return out


# --- Secret patterns -------------------------------------------------------

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{36,}\b")),
    ("github_pat_v2", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b")),
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe_live_secret", re.compile(r"\bsk_live_[A-Za-z0-9]{20,}\b")),
    ("stripe_live_publishable", re.compile(r"\bpk_live_[A-Za-z0-9]{20,}\b")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ),
]


def detect_secrets(text: str, segment_index: int) -> list[Detection]:
    out: list[Detection] = []
    for type_, pattern in _SECRET_PATTERNS:
        for m in pattern.finditer(text):
            out.append(
                Detection(
                    segment_index=segment_index,
                    start=m.start(),
                    end=m.end(),
                    detector="secrets",
                    type=type_,
                    severity="high",
                    original_length=m.end() - m.start(),
                )
            )
    return out


# --- Glossary --------------------------------------------------------------


def _build_glossary_pattern(term: str) -> re.Pattern[str]:
    """Case-insensitive whole-word match. Escapes regex metachars."""
    return re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)


def detect_glossary(
    text: str, segment_index: int, glossary: Glossary | None
) -> list[Detection]:
    if not glossary or not glossary.terms:
        return []
    out: list[Detection] = []
    for term in glossary.terms:
        gt: GlossaryTerm = term
        if not gt.term.strip():
            continue
        pat = _build_glossary_pattern(gt.term.strip())
        for m in pat.finditer(text):
            out.append(
                Detection(
                    segment_index=segment_index,
                    start=m.start(),
                    end=m.end(),
                    detector="glossary",
                    type=f"glossary:{gt.label or gt.term}",
                    severity=gt.severity,
                    original_length=m.end() - m.start(),
                )
            )
    return out
