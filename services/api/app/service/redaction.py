"""Orchestrator for the three redaction layers.

Given a segment text + active modes + glossary, returns a
`RedactionResult` with `[REDACTED:<TYPE>]` substitutions applied and the
list of `Detection`s that fired. Detection offsets always refer to the
ORIGINAL text — the substituted text is rebuilt by walking the original
left-to-right.
"""

from __future__ import annotations

from collections import defaultdict

from app.service.redaction_detectors import (
    detect_glossary,
    detect_pii,
    detect_secrets,
)
from app.types.glossary import Glossary
from app.types.redaction import Detection, RedactionManifest, RedactionResult

VALID_MODES = {"pii", "secrets", "glossary"}


def _dedupe_overlapping(detections: list[Detection]) -> list[Detection]:
    """Keep the higher-severity / longer match on overlap.

    Detection spans can overlap when, say, an email contains an IP shape
    or a glossary term inside an SSN-shaped digit run. Resolve by
    sorting longest-first, then high-severity-first, and dropping
    anything that overlaps an already-kept span.
    """
    severity_rank = {"high": 3, "medium": 2, "low": 1}
    ordered = sorted(
        detections,
        key=lambda d: (
            -severity_rank.get(d.severity, 0),
            -(d.end - d.start),
            d.start,
        ),
    )
    kept: list[Detection] = []
    for det in ordered:
        if any(
            det.segment_index == k.segment_index
            and det.start < k.end
            and det.end > k.start
            for k in kept
        ):
            continue
        kept.append(det)
    return sorted(kept, key=lambda d: (d.segment_index, d.start))


def _substitute(text: str, detections: list[Detection]) -> str:
    """Replace each detected span with `[REDACTED:<TYPE>]`."""
    if not detections:
        return text
    out_parts: list[str] = []
    cursor = 0
    for det in sorted(detections, key=lambda d: d.start):
        if det.start < cursor:
            # Shouldn't happen after dedupe, but stay safe.
            continue
        out_parts.append(text[cursor : det.start])
        out_parts.append(f"[REDACTED:{det.type.upper()}]")
        cursor = det.end
    out_parts.append(text[cursor:])
    return "".join(out_parts)


def redact_segment(
    segment_text: str,
    segment_index: int,
    modes: list[str],
    glossary: Glossary | None = None,
) -> RedactionResult:
    """Run the enabled detectors against one segment and return the result."""
    active = {m for m in modes if m in VALID_MODES}
    detections: list[Detection] = []
    if "pii" in active:
        detections.extend(detect_pii(segment_text, segment_index))
    if "secrets" in active:
        detections.extend(detect_secrets(segment_text, segment_index))
    if "glossary" in active and glossary is not None:
        detections.extend(detect_glossary(segment_text, segment_index, glossary))

    deduped = _dedupe_overlapping(detections)
    return RedactionResult(
        segment_index=segment_index,
        original_text=segment_text,
        redacted_text=_substitute(segment_text, deduped),
        detections=deduped,
    )


def build_manifest(
    session_id: str, modes: list[str], all_detections: list[Detection]
) -> RedactionManifest:
    by_type: dict[str, int] = defaultdict(int)
    by_severity: dict[str, int] = defaultdict(int)
    for det in all_detections:
        by_type[det.type] += 1
        by_severity[det.severity] += 1
    return RedactionManifest(
        session_id=session_id,
        modes=modes,
        detections=all_detections,
        counts_by_type=dict(by_type),
        counts_by_severity=dict(by_severity),
    )
