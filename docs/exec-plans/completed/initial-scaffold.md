# Plan: `gpt-realtime-whisper-live-transcript-redactor`

> **Source of truth:** the starter kit lives at
> `.claude/scratch/vcsk-10a0840f-d234-4ee7-a540-3899a6e8afa6/` (a fresh
> clone of `vibe-coding-starter-kit`, made by Phase 0 of this skill).
> Every reference to "the starter kit" below means that scratch path.
>
> **Parent CLAUDE.md note:** the skill references `../CLAUDE.md`, which
> does not exist at `/Users/epavez/Documents/sampleapps/CLAUDE.md`. The
> parent-level standards (S3 API only, custom `user_agent_extra`,
> standardized `B2_*` env var names) are enforced via this plan and the
> `b2-doctor` skill, mirroring the convention used by sibling samples
> (`voice-memo-ai-second-brain`, `ai-meeting-notes`, etc.). The build and
> review treat `b2-doctor` output as the standards check.

## 1. Purpose

`gpt-realtime-whisper-live-transcript-redactor` is a Backblaze B2 sample
that demonstrates compliance-safe live transcript handling. A user opens
`/record`, grants microphone access, and streams audio through the
backend into the **OpenAI Realtime API with GPT-Realtime-Whisper
transcription**. The UI shows transcript deltas as they arrive, runs a
**three-layer redaction pass** (PII regex, secret-pattern regex, custom
glossary string match) over each finalized utterance segment, and
displays detected entities inline with severity chips. When the user
stops, the session is finalized into a durable B2 "session bundle":
**always** a redacted transcript, a redaction manifest, and an event-log
audit trail; **only on explicit opt-in** the raw audio and unredacted
transcript. Exports (TXT, SRT, VTT) are generated on-demand from the
redacted variant. The sample targets developers building voice/meeting
tools that need an auditable, privacy-default transcript pipeline —
think contact-center QA, legal intake, healthcare scribing — and shows
how B2 can hold both the compliance evidence (manifest + redacted text)
and, when allowed, the raw evidence (audio + original transcript)
without a database.

## 2. Architecture delta from `vibe-coding-starter-kit`

The starter kit is mostly file-upload plumbing; this sample replaces the
core feature surface (no longer "upload a file, see its metadata") with
a realtime-streaming + redaction workflow, but preserves the backbone:
monorepo layout, design system, sidebar shell, layered FastAPI
architecture, structural tests, B2 S3 client conventions, dashboard
scaffold, and the `/files` bucket explorer.

| Keep (as-is or cosmetic rename) | Trim / rewrite | Add (new for this sample) |
|---|---|---|
| Monorepo layout (`apps/web` Next.js 16, `services/api` FastAPI, `packages/shared` TS types) | README, AGENTS, ARCHITECTURE rewritten around realtime transcription + redaction (no generic "upload files" framing) | **/record page** — live mic streaming UI: AudioWorklet PCM capture, transcript-stream pane with inline redaction highlights, entities sidebar, session controls (start, stop, export) |
| Layered backend invariants: `types → config → repo → service → runtime`, structural tests, 300-line cap, no `boto3` outside `repo/` | `apps/web/src/app/page.tsx` (dashboard) — keep the file/structure, replace stats and chart payloads with session-centric metrics | **/sessions page** — sample-scoped library of redaction sessions (the asset explorer required by the skill); cards show duration, entity count by severity, storage mode (privacy-default vs originals-stored) |
| **`/files` full-bucket explorer (NON-NEGOTIABLE KEEP)** — `apps/web/src/app/files/`, `components/files/`, `runtime/files.py`, `service/files.py` unchanged in structure (only rename strings) | `/upload` page repurposed: now uploads an existing audio file and streams it through the same realtime pipeline (no longer the generic-file upload). The starter's upload-metadata path remains for `/files` consumers. | **/sessions/[id] detail page** — split-pane view: redacted transcript (always) + original (only if stored), redaction-manifest table with severity, audit-trail event log, exports panel, audio player (only if stored), delete button |
| `/design` design system showcase, design tokens (`globals.css`), Mona Sans display font, all `components/ui/*` primitives | Dashboard `recent-uploads-table.tsx` reframed as `recent-sessions-table.tsx`; same shape, different domain | **/settings page** — kept from starter (was nearly empty) and extended with custom-glossary editor and per-session-default toggles (`Store original audio`, `Store original transcript`, redaction modes) |
| TanStack Query data layer (`lib/queries.ts`, `lib/api-client.ts`), refresh context, query client | Audio handling — the starter allows `audio/mpeg`/`audio/wav` uploads to `/files`. Kept for the bucket explorer, but `/upload` now goes through the session pipeline instead. | **Realtime backend** — FastAPI WebSocket `/ws/sessions/{id}` bridges browser PCM frames to OpenAI Realtime; pushes transcript deltas + redaction events back to the browser as JSON messages |
| B2 S3 client w/ `Config(user_agent_extra=...)` pattern; `B2_*` env var names | `docs/features/file-upload.md`, `file-browser.md`, `dashboard.md`, `metadata-extraction.md` rewritten for the session-centric framing (see §5) | **OpenAI Realtime client** — `repo/openai_realtime_client.py` wraps the OpenAI WebSocket using `websockets` (sync style via `asyncio`); configures `input_audio_transcription` with the `gpt-realtime` / Whisper model and emits typed events |
| Pre-commit hooks, JSON logging, `/health` w/ B2 connectivity check, `/metrics` Prometheus endpoint, request-id tracing | `.env.example` extended with `OPENAI_API_KEY`, `OPENAI_REALTIME_MODEL`, `REDACTION_DEFAULT_MODES`, `SESSION_STORE_ORIGINALS_DEFAULT` (see §8) | **Redaction engine** — `service/redaction.py` (orchestrator) + `service/redaction_detectors.py` (three detectors: PII regex, secret patterns, glossary). Returns structured `Detection[]` with offsets, type, severity, source detector; replaces matched spans with `[REDACTED:<TYPE>]` |
| `pnpm dev`, `pnpm test:api`, `pnpm check:structure`, `pnpm lint`, `pnpm lint:api`, `pnpm doctor` commands | Recent-uploads chart `upload-chart.tsx` reframed to plot sessions-per-day + entities-detected-per-day; same Recharts surface | **Session orchestrator** — `service/sessions.py` (id generation, manifest read/write, list/head/delete cascade) and `service/realtime_session.py` (per-session state machine: started → streaming → segment_completed → finalized; coordinates redaction calls and B2 writes) |
| Doctor script (`scripts/doctor.mjs`) — preflight env checks; extended to verify `OPENAI_API_KEY` presence and that the audio worklet file is served | `service/upload.py` content-type allowlist trimmed: only audio MIME types accepted at `/upload` (the realtime ingest endpoint); the bucket-explorer upload path (now its own route) keeps the broader allowlist for ops parity | **Exports** — `service/exports.py` produces `.txt` (plain redacted text), `.srt` (timed redacted captions), `.vtt` (web-vtt redacted captions) from the redacted transcript JSON; written to `sessions/.../exports/` on demand |
| Playwright e2e harness (extended with a `/record` smoke test that mocks the WebSocket) | — | **Audit trail** — every session's manifest carries an `events[]` log: `session.started`, `audio.received` (with byte/ms counters), `transcript.completed` (with sha256 hash of original text), `redaction.applied` (with detection count + types), `export.generated`, `session.finalized` |
| Structural test (`tests/test_structure.py`) — extended with one new rule: WebSocket frame handling must live in `runtime/`, not `service/` (mirrors existing "no `boto3` outside `repo/`" pattern) | — | **Frontend audio capture** — `apps/web/src/lib/audio-capture.ts` (getUserMedia + AudioContext + AudioWorkletNode) and `apps/web/public/audio-worklet.js` (PCM16 24kHz mono encoder) — required by OpenAI Realtime input format |
| Health endpoint w/ B2 connectivity check (extended: also reports OpenAI reachability via `HEAD https://api.openai.com/v1/models` with short timeout, so the dashboard surfaces "AI service offline" with a Retry button via the starter's `ErrorState`) | — | **B2 prefixes** — `sessions/<YYYY>/<MM>/<session-id>/...` (manifest, transcript variants, redactions, audio, exports). `uploads/` retained for parity with `/files` consumers. |

### Bucket-explorer policy (explicit, per skill non-negotiable)

- **Keep**: `/files` route, `components/files/`, `runtime/files.py`,
  `service/files.py`, `repo/b2_client.py` listing helpers — unchanged in
  structure (only rename strings). This is the full-bucket explorer the
  skill mandates and it remains useful here: ops/admin can see every
  session bundle, every export, every artifact in one tree.
- **Add (sample-scoped)**: `/sessions` (library of redaction sessions
  scoped to the `sessions/` prefix) and `/sessions/[id]` (detail page).
  Filters and sorts are session-domain (by date, duration, entity
  count, storage mode) — not file-domain.

### Non-goals (explicit out of scope for v1)

- **No diarization / speaker labels.** Realtime API may surface speaker
  turns; v1 ignores them. Documented as a v2 upgrade in
  `docs/features/realtime-transcription.md`.
- **No LLM-based redaction.** v1 ships fast deterministic detectors
  (regex + glossary). A v2 path to send segments through an LLM for
  context-aware redaction (e.g. names that aren't in standard PII
  patterns) is documented in `docs/features/redaction.md` but not
  implemented.
- **No multi-tenant auth, no per-user data isolation.** Single-tenant
  local-dev sample, matching the convention of every other sample.
- **No PDF / DOCX exports.** v1 ships `.txt`, `.srt`, `.vtt` only —
  text-format exports require no binary library dependencies.
- **No client-side audio recording fallback.** OpenAI Realtime requires
  PCM16 24kHz mono; we capture exactly that via AudioWorklet. Browsers
  without AudioWorklet support (very old) get an `ErrorState` telling
  them what's wrong.
- **No realtime cost meter.** Realtime API token/audio billing is
  documented in `docs/features/realtime-transcription.md` (developer
  responsibility) but the UI does not surface a per-session cost.
- **No mobile PWA / service worker.** This sample's hook is desktop
  realtime + redaction, not phone capture. Mobile is a v2.

### Open questions — resolved

The user's command listed two open questions; the plan resolves them
explicitly so the build is unambiguous. Both can be revisited at plan
approval if the user wants a different call.

**Q1: Which redaction entities ship in v1?**
**A: All three layers — PII, secrets, custom glossary — with
deterministic detectors only.** The point of this sample is to
demonstrate **layered** redaction with an auditable manifest. Shipping
fewer layers undersells the demo. The detectors are intentionally
lightweight (regex + string match), with severity tags so the UI can
surface the layered nature. Out of the box:

- **PII layer** — emails, phone numbers (US + international E.164),
  IPv4/IPv6, MAC addresses, credit-card-shaped digits (Luhn-checked),
  SSN-shaped digits. Severity: `high` for SSN / credit card, `medium`
  for the rest.
- **Secrets layer** — well-known patterns: AWS access key (`AKIA…`),
  AWS secret (length + entropy heuristic), GitHub PAT (`ghp_…`,
  `github_pat_…`), OpenAI key (`sk-…`), Slack token (`xox[abprs]-…`),
  JWT (3-segment base64), Stripe (`sk_live_…`, `pk_live_…`). Severity:
  `high`.
- **Glossary layer** — case-insensitive whole-word match against a
  user-defined list stored at `config/glossary.json` in B2 (editable
  from `/settings`). Severity: `low` (configurable to `medium` /
  `high` per term in a future iteration; v1 ships everything at `low`
  with a per-term override field on the schema).

**Q2: Should original audio / transcripts be stored by default or
require explicit opt-in?**
**A: Developer-default — store originals by default for dev testing,
with a prominent README note to flip the toggle for production /
privacy-sensitive deployments.** The user's directive: defaulting to
"store originals" makes the sample app immediately useful for
debugging (you can replay the audio and compare original vs redacted
transcripts) without the friction of changing a setting. The privacy
posture is preserved structurally — the toggles, the manifest fields,
and the per-session UI controls all exist — only the default flips.
Concretely:

- Every session writes `transcript.redacted.json`, `redactions.json`,
  and `manifest.json` (with event log and original-text sha256 hashes)
  — these are always written and never opt-in.
- By default, sessions **also** write `audio.<ext>` (raw recording)
  and `transcript.original.json` (unredacted transcript). Two
  independent toggles on `/record` and in `/settings` let the user
  disable either or both per session.
- The manifest records the storage mode used
  (`store_original_audio: bool`, `store_original_transcript: bool`)
  so an auditor can confirm what was preserved vs purged.
- Env var `SESSION_STORE_ORIGINALS_DEFAULT` controls the initial UI
  toggle state. **v1 ships with `true`**; the README includes a
  prominent "Production Configuration" callout (see §10 below)
  telling operators to flip this to `false` and consider tightening
  the bucket lifecycle policy if they are deploying for compliance
  use.

## 3. B2 surface (S3 API only — no `b2-native`)

| Operation | Used by | Notes |
|---|---|---|
| `PutObject` | Session finalize (manifest + redacted transcript + redactions JSON), opt-in original audio + original transcript, on-demand exports, glossary save from `/settings` | All session writes serialize through `repo/b2_sessions.py`; no path-construction outside that module. |
| `GetObject` | Session detail (read manifest + transcripts + redactions), export download, glossary load, audio playback fallback (when presign isn't applicable) | `repo/b2_sessions.py::get_manifest`, `get_transcript_redacted`, `get_transcript_original`, `get_redactions`, `get_export` |
| `HeadObject` | `/sessions` library row hydration (does `audio.<ext>` exist? does `transcript.original.json` exist? — derives the "storage mode" badge); dashboard aggregates; `/health` B2 connectivity probe (existing) | Batch HEADs via `repo/b2_sessions.head_session_state_parallel`, modeled on `voice-memo-ai-second-brain`'s `head_audio_objects_parallel` |
| `ListObjectsV2` | `/sessions` library list (`sessions/` prefix), `/files` full-bucket explorer (unchanged), dashboard rollups | Existing `repo/b2_client.list_files` reused; new `repo/b2_sessions.list_sessions` adds prefix + parsing |
| `DeleteObject` / `DeleteObjects` | Session delete (must cascade: manifest, both transcript variants, redactions, audio, every export) | `service/sessions.delete_session` walks the session prefix, deletes every key under it in one `DeleteObjects` batch |
| Presigned URL (`generate_presigned_url`) | Inline audio playback on `/sessions/[id]` (when originals stored), export download | Existing `repo/b2_client.get_presigned_url` reused; 10-minute TTL matches starter |

**No `b2-native` usage anywhere.** Every `boto3.client("s3", …)`
instantiation MUST pass `Config(user_agent_extra=
"b2ai-gpt-realtime-whisper-live-transcript-redactor")`.

## 4. Key features (seeds for README and feature docs)

1. **Realtime transcription** — Stream microphone audio to GPT-Realtime
   with Whisper input transcription via a backend WebSocket bridge; see
   incremental transcript deltas land in the UI within ~200ms.
2. **Layered redaction** — Every finalized utterance segment runs through
   three deterministic detectors (PII regex, secret patterns, custom
   glossary). Detections appear in the UI as colored chips by severity
   the moment a segment closes.
3. **Privacy-default session bundles** — Every session always writes a
   redacted transcript + redaction manifest + audit-trail event log to
   B2. Raw audio and raw transcript are written **only** when the user
   explicitly opts in per session.
4. **Audit trail** — Every session manifest contains an append-only
   `events[]` log (session start, audio received bytes/ms, segment
   completed with original-text sha256 hash, redaction applied with
   detection count + types, exports generated, session finalized). An
   auditor can verify the manifest matches a redacted transcript
   without needing the original.
5. **Exports** — Redacted-only `.txt`, `.srt`, `.vtt` exports generated
   on demand from `/sessions/[id]`. Stored under
   `sessions/.../exports/` so download URLs are presigned-stable.
6. **Custom glossary** — Per-deployment list of additional terms to
   redact (project codenames, customer names, internal jargon), edited
   from `/settings`, stored at `config/glossary.json` in B2. Applied
   alongside the built-in PII and secrets detectors.
7. **Full B2 bucket explorer (kept from starter)** — `/files` tree view
   for ops-style browsing across `sessions/`, `uploads/`, and
   `config/`.

## 5. Doc transforms

### Rewritten (same path, new content)

- `README.md` — keep skeleton (badges, Quick Start, env table, design
  system pointer, commands matrix) but reframe top section as realtime
  transcript redactor; add `OPENAI_API_KEY` and the three
  `REDACTION_*` / `SESSION_*` env vars to the table; new "What it
  looks like" section references `/record`, `/sessions`, and
  `/sessions/[id]`.
- `AGENTS.md` — update H1 + one-line description; rewrite Repository
  Map for new routes, new repo helpers (`openai_realtime_client.py`,
  `b2_sessions.py`), new service modules (`realtime_session.py`,
  `redaction.py`, `redaction_detectors.py`, `exports.py`); extend
  "Storage convention" with the `sessions/<YYYY>/<MM>/<id>/` layout
  table; update `user_agent_extra` value to
  `b2ai-gpt-realtime-whisper-live-transcript-redactor`.
- `ARCHITECTURE.md` — add a "Pipeline" subsection with the diagram
  `Mic → AudioWorklet (PCM16) → WS /ws/sessions/{id} → OpenAI Realtime
  → transcript.delta → service.redaction → B2 PutObject (segment
  append) → finalize`; document the "session manifest is the source of
  truth, derived state is computed from object presence" invariant.
- `docs/app-workflows.md` — rewrite user journeys around the four real
  flows: (a) live-record a session, (b) review a past session, (c)
  export a redacted variant, (d) configure the glossary.
- `docs/dev-workflows.md` — extend with OpenAI key setup, AudioWorklet
  serving notes (the worklet file must be at
  `apps/web/public/audio-worklet.js`, not bundled), and a "How to swap
  providers" pointer at `repo/openai_realtime_client.py`.
- `docs/features/dashboard.md` — reframe metrics (sessions / total
  minutes / total detections / detections by severity) and recent
  activity (recent sessions with storage-mode badges).
- `docs/features/file-browser.md` — keep largely unchanged; update
  preface to list the new bucket prefixes (`sessions/`, `config/`).
- `docs/features/file-upload.md` → rewritten in place to
  `docs/features/session-capture.md` (file renamed, content covers
  both `/record` and the file-mode `/upload`, plus the documented
  `POST /sessions` API contract).
- `docs/features/metadata-extraction.md` — kept; clarifies that
  audio-format metadata (duration, codec, sample rate) is extracted
  for `/files` uploads via the starter's existing extractor. Session
  duration is tracked separately by the realtime pipeline (audio bytes
  received ÷ sample rate).

### Newly stubbed

- `docs/features/realtime-transcription.md` — WebSocket contract,
  OpenAI Realtime config, AudioWorklet PCM16 format, model selection
  via `OPENAI_REALTIME_MODEL`, reconnection behavior, fail-soft on
  upstream errors.
- `docs/features/redaction.md` — the three detector layers, severity
  ladder, manifest schema, original-text sha256 hashing for audit,
  v2 LLM-redaction roadmap.
- `docs/features/session-library.md` — `/sessions` page, the asset
  explorer pattern, sample-scoped vs bucket-wide views, storage-mode
  badges.
- `docs/features/audit-trail.md` — events schema, what gets logged,
  how to verify a redacted transcript against the manifest hashes.
- `docs/features/exports.md` — TXT / SRT / VTT formats, redacted-only
  guarantee, presigned download flow.
- `docs/features/custom-glossary.md` — `config/glossary.json` shape,
  case-insensitive whole-word match, editing from `/settings`.

### Deleted

- None — every starter-kit feature doc has a renamed or repurposed
  counterpart in this sample.

### Exec plan

- This file (after build completes) is moved by Phase 5 to
  `./gpt-realtime-whisper-live-transcript-redactor/docs/exec-plans/completed/initial-scaffold.md`.

## 6. Rename table

The builder applies these globally (skip `node_modules`, `.venv`, `dist`,
`build`, `.next`, `pnpm-lock.yaml`, `package-lock.json`).

| From (in `vibe-coding-starter-kit`) | To (in `gpt-realtime-whisper-live-transcript-redactor`) | Where it appears |
|---|---|---|
| `vibe-coding-starter-kit` | `gpt-realtime-whisper-live-transcript-redactor` | `package.json` name, `pnpm-workspace` filters, README badges, repo URLs, image tags, workflow slugs, docs cross-links |
| `vibe_coding_starter_kit` | `gpt_realtime_whisper_live_transcript_redactor` | Python module / fixture names if present, env-var prefix never (B2_* stays B2_*) |
| `Vibe Coding Starter Kit` | `GPT-Realtime-Whisper Live Transcript Redactor` | README H1, AGENTS H1, ARCHITECTURE H1, `<title>` and metadata in Next layout, docs/features/*.md H1s where relevant |
| `@vibe-coding-starter-kit/web` | `@gpt-realtime-whisper-live-transcript-redactor/web` | Workspace package name, `pnpm --filter` invocations in `package.json` scripts, README commands |
| `@vibe-coding-starter-kit/shared` | `@gpt-realtime-whisper-live-transcript-redactor/shared` | Shared package name, web `package.json` dependency |
| `b2ai-oss-start` | `b2ai-gpt-realtime-whisper-live-transcript-redactor` | `Config(user_agent_extra=...)` literal in every `boto3.client("s3", …)` call; UTM `utm_content` query-string parameter on every Backblaze sign-up / docs link |
| `Build me a dashboard…` / "starter kit" marketing hooks | "Stream microphone audio, redact PII / secrets / custom terms in realtime, and ship a privacy-default session bundle to B2 — a compliance-safe transcript workbench." | README opening, ARCHITECTURE intro, AGENTS intro |
| `File Upload`, `File Browser`, `Dashboard` (UI titles) | Kept where they refer to `/files` (full-bucket explorer); reframed where they refer to the now-removed generic upload page: `File Upload` → `Session Capture`, plus new titles `Live Recording`, `Sessions`, `Session Detail`, `Glossary` | Sidebar nav strings, page `<h1>`s, e2e test selectors |
| `Recent Uploads` (dashboard table) | `Recent Sessions` | `apps/web/src/components/dashboard/recent-uploads-table.tsx` → renamed `recent-sessions-table.tsx`; queries & types renamed accordingly |
| `useFiles`, `useDeleteFile`, `useUploadFile` (kept for /files), plus **new** `useSessions`, `useSession`, `useDeleteSession`, `useGenerateExport`, `useGlossary`, `useSaveGlossary` | (additions, not renames) | `apps/web/src/lib/queries.ts`, `lib/api-client.ts` |
| `FileMetadata`, `FileMetadataDetail` (kept for /files) plus **new** `Session`, `SessionManifest`, `TranscriptSegment`, `Redaction`, `RedactionManifest`, `AuditEvent`, `ExportRequest`, `Glossary` | (additions, not renames) | `packages/shared/src/types.ts`, `services/api/app/types/sessions.py`, `types/transcripts.py`, `types/redaction.py`, `types/exports.py`, `types/glossary.py` |
| README hook "Stop wiring boilerplate and start building." | "Stream microphone audio through OpenAI's GPT-Realtime-Whisper, redact PII / secrets / custom terms inline, and ship a privacy-default session bundle to Backblaze B2 — compliance evidence and audit trail included, raw audio kept only on explicit opt-in." | README first paragraph |

> **Reviewer note (for Phase 3):** The standard reviewer checks for
> leftover `vibe-coding-starter-kit` strings. Any occurrence outside an
> explicit "Derived from `vibe-coding-starter-kit`" historical-note
> context is ❌. The reviewer also verifies the rename of `b2ai-oss-start`
> to `b2ai-gpt-realtime-whisper-live-transcript-redactor` in every
> boto3-client construction site under `services/api/app/repo/`.

## 7. Sample-scoped routes (summary)

| Route | Component | Purpose |
|---|---|---|
| `/` | `apps/web/src/app/page.tsx` | Dashboard — sessions count, total minutes, detections by severity, recent sessions table |
| `/record` | `apps/web/src/app/record/page.tsx` | Live realtime recording: AudioWorklet → WebSocket → transcript stream with inline redaction chips |
| `/upload` | `apps/web/src/app/upload/page.tsx` | Upload an existing audio file, stream it through the same realtime pipeline |
| `/sessions` | `apps/web/src/app/sessions/page.tsx` | **Sample-specific asset explorer** — library of redaction sessions scoped to the `sessions/` prefix |
| `/sessions/[id]` | `apps/web/src/app/sessions/[id]/page.tsx` | Session detail — redacted + (if stored) original transcripts side-by-side, redaction manifest, audit-trail log, exports |
| `/settings` | `apps/web/src/app/settings/page.tsx` | Custom glossary CRUD + per-session-default storage toggles |
| `/files` | `apps/web/src/app/files/page.tsx` | **Bucket explorer (kept from starter, non-negotiable)** — full-bucket tree |
| `/design` | `apps/web/src/app/design/page.tsx` | Design system showcase (kept) |

## 8. New env vars

Added to `.env.example` alongside the existing `B2_*` keys (which are
unchanged):

```
# OpenAI Realtime (required) — drives live transcription via the
# GPT-Realtime-Whisper Realtime API and the dashboard's "AI service
# reachable" health probe.
OPENAI_API_KEY=your_openai_api_key

# Optional: realtime model override. Default targets the
# GPT-Realtime-Whisper transcription preset.
# OPENAI_REALTIME_MODEL=gpt-realtime-whisper

# Optional: which redaction detectors run by default on /record.
# Comma-separated subset of {pii, secrets, glossary}. UI lets the user
# toggle per session.
# REDACTION_DEFAULT_MODES=pii,secrets,glossary

# Storage default. When true (v1 default — convenient for dev testing),
# /record writes raw audio AND the unredacted transcript alongside the
# redacted bundle. When false, only the redacted transcript + manifest +
# audit trail are written (privacy default — flip this in production).
# Per-session toggles on /record override this default either way.
# SESSION_STORE_ORIGINALS_DEFAULT=true
```

The doctor script (`scripts/doctor.mjs`) is extended to surface a
warning (not an error) if `OPENAI_API_KEY` is unset, with a one-line
hint about where to get one — matching the starter's existing
fail-fast tone.

## 9. Required README "Production Configuration" callout

Because v1 stores raw audio and unredacted transcripts by default, the
README MUST surface a prominent callout — explicitly directed at
operators who deploy this sample for any real compliance-sensitive use.
The callout lives directly under the "Quick Start" section (so a
user setting up `.env` for the first time can't miss it). Wording is
left to the builder but the callout MUST include:

1. A clearly-flagged heading ("Production Configuration" with a
   visual marker such as `> ⚠️` blockquote or a dedicated `##`-level
   section).
2. The exact env var to flip:
   `SESSION_STORE_ORIGINALS_DEFAULT=false`.
3. A one-line rationale that v1 defaults to storing originals
   ("convenient for development testing — you can replay audio and
   compare the original vs redacted transcript") and that real
   deployments should flip it.
4. A pointer to `docs/SECURITY.md` (or
   `docs/features/redaction.md`) for the full storage-mode discussion
   and a recommendation to also configure a B2 bucket Lifecycle Rule
   to expire `sessions/.../audio.*` and `sessions/.../transcript.original.json`
   objects on a short schedule if the operator wants belt-and-suspenders
   defense.
5. A note that the per-session toggles on `/record` and `/settings`
   override the env-var default in either direction, so an operator
   can leave the default at `false` and grant per-session opt-in for
   debugging.

The callout MUST also be cross-referenced from `docs/features/redaction.md`
and `docs/SECURITY.md` so anyone reading the security or redaction docs
in isolation discovers it.

## 10. Parent CLAUDE.md note

See the source-of-truth callout at the top of this file. In short:
`/Users/epavez/Documents/sampleapps/CLAUDE.md` does not exist; the
standards (S3-only default, `Config(user_agent_extra=…)` on every
boto3 S3 client, standard `B2_*` env var names) are enforceable via
this plan and the `b2-doctor` skill. The builder and reviewer should
treat `b2-doctor` output as the standards check, mirroring the
convention used in every sibling sample's exec plan.
