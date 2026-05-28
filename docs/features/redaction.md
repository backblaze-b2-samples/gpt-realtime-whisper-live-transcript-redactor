<!-- last_verified: 2026-05-28 -->
# Feature: Layered Redaction

## Purpose

Run three deterministic detectors against every finalized transcript
segment and substitute `[REDACTED:<TYPE>]` placeholders before the
redacted variant is persisted or shown to the user.

## Used By

- UI: `/record` (inline severity chips), `/sessions/[id]` (manifest table)
- API: `service/realtime_session.py` calls `service/redaction.py` on every
  `transcript.completed` event; `redaction.py` returns a `RedactionResult`

## Core Files

- `services/api/app/service/redaction.py` — orchestrator (dedupe overlaps, substitute spans, build manifest)
- `services/api/app/service/redaction_detectors.py` — three detectors
- `services/api/app/types/redaction.py` — Pydantic models
- `services/api/tests/test_redaction.py` — unit tests

## Detectors

### Layer 1 — PII (regex)

| Type | Severity | Notes |
|---|---|---|
| `email` | medium | Standard local-part@domain |
| `phone` | medium | US + international E.164 |
| `ipv4`, `ipv6` | medium | |
| `mac_address` | medium | Standard colon-separated form |
| `credit_card` | high | Luhn-checked; non-conforming 16-digit runs are ignored |
| `ssn` | high | 3-2-4 dashed shape |

### Layer 2 — Secrets (regex)

| Type | Pattern |
|---|---|
| `aws_access_key` | `AKIA[0-9A-Z]{16}` |
| `github_pat` | `ghp_[A-Za-z0-9]{36,}` |
| `github_pat_v2` | `github_pat_[A-Za-z0-9_]{60,}` |
| `openai_api_key` | `sk-[A-Za-z0-9]{20,}` |
| `slack_token` | `xox[abprs]-[A-Za-z0-9-]{10,}` |
| `stripe_live_secret` | `sk_live_[A-Za-z0-9]{20,}` |
| `stripe_live_publishable` | `pk_live_[A-Za-z0-9]{20,}` |
| `jwt` | 3-segment base64 `eyJ...` |

All `severity: high`.

### Layer 3 — Custom glossary

Case-insensitive whole-word match against `config/glossary.json` in B2.
Severity defaults to `low` and is configurable per term in `/settings`.
Term type is rendered as `glossary:<label-or-term>`.

## Overlap resolution

Detectors run independently; their spans can overlap. The orchestrator
sorts by severity (high > medium > low) then by length (longer first)
and drops any later span that overlaps an already-kept one. The result
is a deterministic sorted list of non-overlapping detections.

## Substitution

`redact_segment()` returns both the original text and the redacted text,
plus the list of detections (with offsets pointing into the **original**
text). The redacted text replaces each kept span with
`[REDACTED:<TYPE>]` (uppercase).

## Manifest schema

`redactions.json` (one per session) carries:

```jsonc
{
  "session_id": "...",
  "modes": ["pii", "secrets", "glossary"],
  "detections": [
    {
      "segment_index": 3,
      "start": 14,
      "end": 27,
      "detector": "pii",
      "type": "email",
      "severity": "medium",
      "original_length": 13
    }
  ],
  "counts_by_type": { "email": 2, "ssn": 1 },
  "counts_by_severity": { "high": 1, "medium": 2 }
}
```

## Original-text sha256 hashing for audit

Every `transcript.completed` audit event records the sha256 of the
original (pre-redaction) segment text. An auditor with access to the
redacted bundle and the manifest can verify integrity by re-hashing the
original (when stored) and matching against the audit trail.

## Storage mode and the production default flip

`SESSION_STORE_ORIGINALS_DEFAULT` toggles whether `transcript.original.json`
and `audio.<ext>` are persisted alongside the redacted bundle:

- **v1 default: `true`** — convenient for development testing; you can
  replay the audio and compare original vs redacted transcripts. The
  README's [Production Configuration](../../README.md#-production-configuration-read-this-before-deploying)
  callout is mandatory reading before deploying.
- **Production recommendation: `false`** — only the redacted transcript
  + redactions JSON + manifest (with hashes) are written. See
  [SECURITY.md](../SECURITY.md#storage-mode--default-flip-for-production)
  for the full storage-mode discussion.

Per-session toggles on `/record` and per-default toggles on `/settings`
override the env-var default in either direction.

## v2 roadmap

- LLM-based redaction for names that aren't in standard PII patterns
- Per-deployment severity overrides for glossary terms
- Diarization-aware redaction (drop entire speaker turns)

## Verification

- Test files: `services/api/tests/test_redaction.py`
- Pass criteria: emails, SSNs, AWS keys, glossary terms all redacted; Luhn-invalid CC patterns NOT redacted; disabled modes do nothing
- Quick verify: `pnpm test:api`

## Related Docs

- [Realtime Transcription](realtime-transcription.md)
- [Custom Glossary](custom-glossary.md)
- [Audit Trail](audit-trail.md)
