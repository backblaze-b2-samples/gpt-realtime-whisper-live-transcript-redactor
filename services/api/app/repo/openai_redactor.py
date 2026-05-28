"""OpenAI chat-completions adapter for LLM-backed PII extraction.

The deterministic regex detectors in `service/redaction_detectors.py`
match typed-text shapes (API-key prefixes, hyphenated tokens). Speech
transcription returns natural language — people's names, "john at
example dot com", spelled-out card numbers — which those patterns can
never match, and regex fundamentally cannot recognize a *name* at all.
The `pii` redaction layer therefore delegates extraction to a small chat
model that reads one finalized transcript segment and returns the PII
spans verbatim; the service layer maps each span back to character
offsets and runs the same substitution pipeline as the other layers.

Boundary discipline: this is the only place besides
`openai_realtime_client.py` that talks to OpenAI. The service layer sees
typed `PiiEntity` records and never touches HTTP.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Categories the model is asked to tag. `type` is free-form downstream
# (it only feeds the `[REDACTED:<TYPE>]` label), but constraining the
# prompt keeps the labels consistent from one segment to the next.
_PII_TYPES = (
    "name",
    "phone",
    "email",
    "address",
    "date_of_birth",
    "government_id",
    "financial",
    "credentials",
    "other",
)

_SYSTEM_PROMPT = (
    "You are a PII detection engine for transcribed speech. The user "
    "message is one transcript segment. Identify every span that is "
    "personally identifying information: people's names, phone numbers, "
    "email addresses, physical or mailing addresses, dates of birth, "
    "government IDs (SSN, passport, driver's license), and financial "
    "account or card numbers. In speech these are frequently spoken as "
    'words or spelled out ("john at example dot com", "five five five '
    'one two three"), so capture the full natural-language span exactly '
    "as it appears in the input text. Respond with JSON only, shaped as "
    '{"entities": [{"text": <verbatim substring>, "type": <one of '
    f"{list(_PII_TYPES)}>, "
    '"severity": <"high"|"medium"|"low">}]}. Use "high" for government '
    "IDs, financial data, and full names paired with other identifiers; "
    '"medium" for standalone names, phones, emails, and addresses; "low" '
    "otherwise. Return an empty list when there is no PII. Never add "
    "explanations."
)


@dataclass
class PiiEntity:
    """One PII span the model reported, verbatim from the input text."""

    text: str
    type: str
    severity: str


async def detect_pii_entities(text: str) -> list[PiiEntity]:
    """Return the PII spans the model found in `text`.

    Fails open to an empty list (logged) on any error: a redaction *miss*
    is recoverable and visible in the audit trail, whereas raising here
    would abort session finalize and lose the whole transcript bundle.
    """
    if not settings.openai_api_key:
        logger.warning("PII redaction skipped: OPENAI_API_KEY not configured")
        return []
    if not text.strip():
        return []

    payload = {
        "model": settings.redaction_pii_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    try:
        async with httpx.AsyncClient(
            timeout=settings.redaction_pii_timeout_s
        ) as client:
            resp = await client.post(
                f"{settings.openai_api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "User-Agent": (
                        "b2ai-gpt-realtime-whisper-live-transcript-redactor"
                    ),
                },
                json=payload,
            )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        raw = json.loads(content)
    except Exception as e:
        logger.warning("PII extraction call failed: %s", e)
        return []

    return _parse_entities(raw)


def _parse_entities(raw: object) -> list[PiiEntity]:
    """Validate the model's JSON into `PiiEntity` records, dropping junk.

    Defensive on purpose: the model output is untrusted, so anything that
    isn't a well-formed entity with a non-empty `text` is skipped rather
    than allowed to crash the redaction pass.
    """
    if not isinstance(raw, dict):
        return []
    items = raw.get("entities")
    if not isinstance(items, list):
        return []
    out: list[PiiEntity] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        span = item.get("text")
        if not isinstance(span, str) or not span.strip():
            continue
        etype = item.get("type")
        etype = etype if isinstance(etype, str) and etype else "other"
        sev = item.get("severity")
        sev = sev if sev in ("high", "medium", "low") else "medium"
        out.append(PiiEntity(text=span, type=etype, severity=sev))
    return out
