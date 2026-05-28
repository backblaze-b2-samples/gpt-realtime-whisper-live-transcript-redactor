"""Custom-glossary CRUD — backed by `config/glossary.json` in B2."""

from __future__ import annotations

import logging

from app.repo import b2_sessions
from app.types.glossary import Glossary

logger = logging.getLogger(__name__)


def load_glossary() -> Glossary:
    raw = b2_sessions.get_glossary()
    if raw is None:
        return Glossary()
    try:
        return Glossary(**raw)
    except Exception:
        logger.warning("Glossary JSON is malformed — returning empty list")
        return Glossary()


def save_glossary(glossary: Glossary) -> None:
    # Dedupe by lowercased term, keep last-write-wins severity / label.
    seen: dict[str, dict] = {}
    for t in glossary.terms:
        key = t.term.strip().lower()
        if not key:
            continue
        seen[key] = t.model_dump()
    cleaned = Glossary(version=glossary.version, terms=list(seen.values()))
    b2_sessions.put_glossary(cleaned.model_dump(mode="json"))
