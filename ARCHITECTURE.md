<!-- last_verified: 2026-05-28 -->
# Architecture

`gpt-realtime-whisper-live-transcript-redactor` is a Backblaze B2 sample
that demonstrates compliance-safe live transcript handling. A user opens
`/record`, grants microphone access, streams audio through the backend
to the OpenAI Realtime API for GPT-Realtime-Whisper transcription, and
the UI shows transcript deltas with inline severity-tagged redactions.
On finalize the backend writes a privacy-default session bundle to B2.

## Components

- **apps/web/** — Next.js 16 frontend (App Router, Tailwind v4, shadcn/ui)
  - `/record` — live mic streaming UI with AudioWorklet PCM capture
  - `/sessions` + `/sessions/[id]` — sample-scoped redaction-session library
  - `/files` — full bucket explorer (kept from the starter)
  - `/upload` — file-mode session capture (drag in existing audio)
  - `/settings` — custom glossary editor + storage defaults
- **services/api/** — FastAPI backend (layered architecture)
  - WebSocket bridge `/ws/sessions/{id}` between browser PCM and OpenAI Realtime
  - REST API for session CRUD, exports, glossary, and the legacy file-explorer routes
  - Layered redaction engine (`service/redaction.py` + `service/redaction_detectors.py`)
  - Session state machine (`service/realtime_session.py`)
  - B2 session-prefix adapter (`repo/b2_sessions.py`)
  - OpenAI Realtime adapter (`repo/openai_realtime_client.py`)
  - OpenAI PII extraction adapter (`repo/openai_redactor.py`)
- **packages/shared/** — TypeScript type definitions mirroring the Pydantic models

## Realtime Pipeline

```
[Mic] -> AudioWorklet (PCM16 24kHz mono)
      -> WebSocket /ws/sessions/{id}  (runtime/realtime.py)
      -> OpenAIRealtimeClient        (repo/openai_realtime_client.py)
      -> transcript.delta            (forwarded to browser)
      -> transcript.completed        (service/realtime_session.py)
      -> redact_segment              (service/redaction.py)
      -> manifest mutation + audit event append
      -> finalize() on stop:
         - PutObject transcript.redacted.json (always)
         - PutObject redactions.json          (always)
         - PutObject manifest.json            (always)
         - PutObject transcript.original.json (opt-in)
         - PutObject audio.<ext>              (opt-in)
```

### Invariants of the pipeline

1. **The session manifest is the source of truth.** Derived state (does
   the bundle have audio? does it have an unredacted transcript?) is
   computed by HEAD'ing the predictable keys at list time. The library
   page never trusts client-side cache or in-memory aggregates.
2. **Frames never persist before redaction completes.** The redacted
   transcript and redactions JSON are written together; if a finalize
   step fails the manifest is sealed with `status=errored` so the audit
   trail still reflects what happened.
3. **WebSocket frame handling lives in `runtime/`.** The service layer
   (`realtime_session.py`) is a pure state machine. Mixing them
   collapses the layer boundary; structural test
   `test_fastapi_websocket_only_in_runtime` enforces this.
4. **External streaming SDKs live in `repo/`.** The `websockets`
   client used to talk to OpenAI is contained to `repo/openai_realtime_client.py`,
   mirroring the existing `boto3` containment rule. Structural test
   `test_websockets_client_only_in_repo` enforces this.

## Backend Layering

```
types/     Pydantic models — sessions, transcripts, redactions, exports, glossary
  |
config/    Settings (pydantic-settings) — B2 + OpenAI + redaction defaults
  |
repo/      Data access — b2_client, b2_sessions, openai_realtime_client, openai_redactor
  |
service/   Business logic — sessions, realtime_session, redaction, redaction_detectors, exports, glossary, upload, files, metadata
  |
runtime/   FastAPI routes — sessions, realtime (WebSocket bridge), exports, glossary, files, upload, health, metrics
```

### Layering Rules

1. Dependencies flow downward only: `types -> config -> repo -> service -> runtime`
2. No backward imports
3. `boto3` only in `repo/`
4. `websockets` client SDK only in `repo/`
5. FastAPI `WebSocket` handlers only in `runtime/`
6. All boundary data uses Pydantic models
7. Each file stays under 300 lines

## B2 Layout

```
sessions/<YYYY>/<MM>/<session-id>/
  manifest.json                  # SessionManifest (always)
  transcript.redacted.json       # Transcript variant=redacted (always)
  redactions.json                # RedactionManifest (always)
  transcript.original.json       # Transcript variant=original (opt-in)
  audio.<ext>                    # raw bytes (opt-in)
  exports/transcript.txt|srt|vtt # on-demand exports (redacted-only)

config/
  glossary.json                  # custom-glossary CRUD target

uploads/                         # kept for /files consumers
```

Session id pattern: `^[0-9]{14}-[A-Za-z0-9]{6,12}$` (timestamp + url-safe suffix).

## Boundary Invariants

- **No external SDK leakage** — `boto3` lives in `repo/b2_client.py` and
  `repo/b2_sessions.py`; `websockets` lives in `repo/openai_realtime_client.py`;
  OpenAI chat-completions PII extraction lives in `repo/openai_redactor.py`.
- **No raw dicts at boundaries** — all data crossing layer boundaries
  uses typed Pydantic models.
- **No mutable globals** — settings is read-only after init.
- **Validated inputs** — all HTTP inputs validated by FastAPI/Pydantic;
  every file key validated against a path-traversal regex; session ids
  validated against `SESSION_ID_REGEX`.

## Deployment

- **Local dev** — `pnpm dev` runs both services concurrently
  - Web: `localhost:3000`
  - API: `localhost:8000`
- **Railway** — two services from the same repo; see `infra/railway/README.md`.

## External Services

- **Backblaze B2 S3 API** — storage of record for everything (sessions,
  exports, glossary).
- **OpenAI Realtime API** — drives streaming transcription via
  `repo/openai_realtime_client.py`. Reachability is probed by `/health`.
- **OpenAI chat completions** — extracts PII spans for the redaction layer via
  `repo/openai_redactor.py`.

## Observability

- Structured JSON logging on all requests with `request_id`
- Request timing middleware
- `/metrics` (Prometheus format)
- `/health` reports both `b2_connected` and `openai_reachable`

## Canonical Files

- Realtime bridge: `services/api/app/runtime/realtime.py`
- Session state machine: `services/api/app/service/realtime_session.py`
- Redaction orchestrator: `services/api/app/service/redaction.py`
- Detectors: `services/api/app/service/redaction_detectors.py`
- B2 session adapter: `services/api/app/repo/b2_sessions.py`
- OpenAI Realtime adapter: `services/api/app/repo/openai_realtime_client.py`
- OpenAI PII extraction adapter: `services/api/app/repo/openai_redactor.py`
- Exports: `services/api/app/service/exports.py`
- Pydantic models: `services/api/app/types/`
- Structural tests: `services/api/tests/test_structure.py`
- Frontend API client: `apps/web/src/lib/api-client.ts`
- AudioWorklet (must be served at top-level URL): `apps/web/public/audio-worklet.js`

## Core Features

- [Realtime Transcription](docs/features/realtime-transcription.md)
- [Layered Redaction](docs/features/redaction.md)
- [Session Library](docs/features/session-library.md)
- [Audit Trail](docs/features/audit-trail.md)
- [Exports](docs/features/exports.md)
- [Custom Glossary](docs/features/custom-glossary.md)
- [Session Capture](docs/features/session-capture.md)
- [Dashboard](docs/features/dashboard.md)
- [File Browser](docs/features/file-browser.md)
- [Metadata Extraction](docs/features/metadata-extraction.md)

## References

- [docs/SECURITY.md](docs/SECURITY.md) — security incl. storage-mode default flip
- [docs/RELIABILITY.md](docs/RELIABILITY.md)
- [AGENTS.md](AGENTS.md)
