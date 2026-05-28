<!-- last_verified: 2026-05-28 -->
# Feature: Custom Glossary

## Purpose

A per-deployment list of additional terms to redact — project
codenames, customer names, internal jargon — applied alongside the
built-in PII and secrets detectors.

## Used By

- UI: `/settings` glossary editor
- API: `GET /glossary`, `PUT /glossary`
- Detector: `service/redaction_detectors.py::detect_glossary`

## Core Files

- `services/api/app/runtime/glossary.py`
- `services/api/app/service/glossary.py`
- `services/api/app/repo/b2_sessions.py::get_glossary` / `put_glossary`
- `services/api/app/types/glossary.py`
- `apps/web/src/components/settings/glossary-editor.tsx`

## Storage

Stored at `config/glossary.json` in the B2 bucket. Reads and writes go
through `b2_sessions.py` so the path is the only one in the codebase.

## Schema

```jsonc
{
  "version": 1,
  "terms": [
    { "term": "Project Falcon", "severity": "medium", "label": null },
    { "term": "AcmeCorp",       "severity": "low",    "label": "customer" }
  ]
}
```

- `term` — the literal string to match (case-insensitive whole word)
- `severity` — `low` | `medium` | `high` (controls UI chip colour)
- `label` — optional override used in the rendered detection type
  (`glossary:<label-or-term>`)

## Match behavior

- Case-insensitive
- Whole-word — bounded by `\b` so "ACME" matches in "ACME Corp" but NOT in "ACMEPRO"
- Regex metachars in the term are escaped before compilation
- Empty terms are silently dropped

## CRUD via /settings

The editor loads the full list on mount, lets the user add/remove/edit
severity, and saves the whole list as one PUT. Duplicate terms are
deduped case-insensitively (last write wins for severity).

## Verification

- Glossary tests covered in `services/api/tests/test_redaction.py::test_glossary_case_insensitive`

## Related Docs

- [Redaction](redaction.md)
- [Settings UI](../app-workflows.md#configure-the-custom-glossary)
