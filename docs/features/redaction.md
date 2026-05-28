<!-- last_verified: 2026-05-28 -->
# Feature: Layered Redaction

## Purpose

Run three detector layers against every finalized transcript segment and
substitute `[REDACTED:<TYPE>]` placeholders before the redacted variant
is persisted or shown to the user.

The `pii` layer is **LLM-backed**; `secrets` and `glossary` are
deterministic regex. This split is deliberate: the input is transcribed
*speech*, where PII arrives as natural language — a spoken name, "john at
example dot com", a spelled-out card number — that regex cannot match,
and regex fundamentally cannot recognize a person's name at all.
Structured secrets (API keys, tokens) and operator-defined glossary terms
*do* appear as exact strings, so regex stays the right, cheaper tool
there.

## Used By

- UI: `/record` (inline severity chips), `/sessions/[id]` (manifest table)
- API: `service/realtime_session.py` calls `service/redaction.py` on every
  `transcript.completed` event; `redaction.py` returns a `RedactionResult`

## Core Files

- `services/api/app/service/redaction.py` — orchestrator (dedupe overlaps, substitute spans, build manifest); `redact_segment` is **async** because the PII layer makes a network call
- `services/api/app/service/redaction_detectors.py` — detectors (`detect_pii_llm`, `detect_secrets`, `detect_glossary`)
- `services/api/app/repo/openai_redactor.py` — OpenAI chat-completions adapter for PII extraction
- `services/api/app/types/redaction.py` — Pydantic models
- `services/api/tests/test_redaction.py` — unit tests (PII layer stubbed)

## Detectors

### Layer 1 — PII (LLM)

`detect_pii_llm` sends the finalized segment to a small chat model
(`REDACTION_PII_MODEL`, default `gpt-4o-mini`) via
`repo/openai_redactor.py`. The model returns PII spans **verbatim** as
JSON; the detector anchors each span to character offsets with an exact
match (every occurrence) and emits `Detection`s with `detector="pii"`.
Spans the model paraphrases and that can't be located are dropped — we
never redact a range we can't anchor in the original text.

| Type | Typical severity | Examples it catches |
|---|---|---|
| `name` | medium–high | "John Smith", spoken plainly |
| `phone` | medium | "five five five one two three…", "555-123-4567" |
| `email` | medium | "john at example dot com", `john@example.com` |
| `address` | medium | "12 Oak Street, Springfield" |
| `date_of_birth` | high | "March 3rd 1990" |
| `government_id` | high | SSN, passport, driver's license (however spoken) |
| `financial` | high | card / account numbers, spelled out or not |
| `credentials` | high | spoken passwords / PINs |

Failure handling: the call **fails open** to "no PII" (logged) on missing
key, timeout, or upstream error — a redaction *miss* is visible in the
audit trail, whereas raising would abort finalize and lose the whole
transcript bundle. The per-segment call is bounded by
`REDACTION_PII_TIMEOUT_S` (default 15s).

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

- Per-deployment severity overrides for glossary terms
- Diarization-aware redaction (drop entire speaker turns)
- Batch/streaming PII extraction to lower per-segment latency on
  high-turn-count sessions

## Verification

- Test files: `services/api/tests/test_redaction.py`
- Pass criteria: stubbed PII entities are anchored and redacted (incl.
  spoken-form spans and every occurrence); AWS keys + glossary terms
  redacted by the regex layers; secrets-only mode never invokes the LLM;
  disabled modes do nothing
- Quick verify: `pnpm test:api`

## Related Docs

- [Realtime Transcription](realtime-transcription.md)
- [Custom Glossary](custom-glossary.md)
- [Audit Trail](audit-trail.md)
