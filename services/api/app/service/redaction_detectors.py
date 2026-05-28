"""Three deterministic detectors run against finalized transcript segments.

Layer 1: PII regex          (emails, phones, IP, MAC, CC w/ Luhn, SSN-shaped)
Layer 2: Secret patterns    (AWS / GitHub / OpenAI / Slack / JWT / Stripe)
Layer 3: Glossary           (case-insensitive whole-word match against B2)

Each detector returns `list[Detection]` with byte offsets relative to the
segment text. The orchestrator (`service/redaction.py`) merges and
deduplicates overlapping spans before substitution.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.types.glossary import Glossary, GlossaryTerm
from app.types.redaction import Detection, DetectionSeverity

# --- PII patterns ----------------------------------------------------------

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)"
)
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
_IPV6_RE = re.compile(r"\b(?:[A-Fa-f0-9]{1,4}:){7}[A-Fa-f0-9]{1,4}\b")
_MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")
_CC_RE = re.compile(r"\b(?:\d[ -]?){13,18}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def _luhn_ok(s: str) -> bool:
    digits = [int(c) for c in s if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _emit(
    pattern: re.Pattern[str],
    text: str,
    segment_index: int,
    type_: str,
    severity: DetectionSeverity,
    extra_check=None,
) -> Iterable[Detection]:
    for m in pattern.finditer(text):
        matched = m.group(0)
        if extra_check is not None and not extra_check(matched):
            continue
        yield Detection(
            segment_index=segment_index,
            start=m.start(),
            end=m.end(),
            detector="pii",
            type=type_,
            severity=severity,
            original_length=m.end() - m.start(),
        )


def detect_pii(text: str, segment_index: int) -> list[Detection]:
    out: list[Detection] = []
    out.extend(_emit(_SSN_RE, text, segment_index, "ssn", "high"))
    out.extend(_emit(_CC_RE, text, segment_index, "credit_card", "high", _luhn_ok))
    out.extend(_emit(_EMAIL_RE, text, segment_index, "email", "medium"))
    out.extend(_emit(_PHONE_RE, text, segment_index, "phone", "medium"))
    out.extend(_emit(_IPV4_RE, text, segment_index, "ipv4", "medium"))
    out.extend(_emit(_IPV6_RE, text, segment_index, "ipv6", "medium"))
    out.extend(_emit(_MAC_RE, text, segment_index, "mac_address", "medium"))
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
