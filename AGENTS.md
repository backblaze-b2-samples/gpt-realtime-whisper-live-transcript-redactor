<!-- last_verified: 2026-05-28 -->
# AGENTS.md

`gpt-realtime-whisper-live-transcript-redactor` — stream microphone audio
through OpenAI's GPT-Realtime-Whisper, redact PII / secrets / custom
terms inline, and ship a privacy-default session bundle to Backblaze B2.
This file is the authoritative control surface for all coding agents.
Read it first.

## 1. Repository Map

```
apps/web/                          Next.js 16 frontend (App Router, Tailwind v4, shadcn/ui)
  src/app/record/                  Live /record page
  src/app/sessions/                /sessions library + /sessions/[id] detail
  src/app/files/                   Full-bucket explorer (kept from starter)
  src/app/upload/                  Audio file-mode capture
  src/app/settings/                Glossary editor + storage defaults
  src/components/record/           Realtime UI controls
  src/components/sessions/         Library + detail components
  src/components/settings/         Glossary editor
  src/lib/audio-capture.ts         getUserMedia + AudioWorkletNode wrapper
  public/audio-worklet.js          PCM16 24kHz encoder — MUST be served at top-level URL
services/api/                      FastAPI backend (layered)
  app/types/                       Pydantic models
  app/config/settings.py           pydantic-settings — B2 + OpenAI + redaction defaults
  app/repo/b2_client.py            B2 S3 adapter (legacy file API)
  app/repo/b2_sessions.py          B2 session-prefix adapter (manifest / transcripts / exports / glossary)
  app/repo/openai_realtime_client.py  OpenAI Realtime websocket adapter
  app/repo/openai_redactor.py      OpenAI chat-completions PII span extraction adapter
  app/service/redaction.py         Three-layer redaction orchestrator
  app/service/redaction_detectors.py  PII / secrets / glossary detectors
  app/service/sessions.py          Session id, library, stats, delete cascade
  app/service/realtime_session.py  Per-session streaming state machine
  app/service/exports.py           TXT / SRT / VTT renderers
  app/service/glossary.py          Custom glossary CRUD
  app/service/files.py / upload.py / metadata.py   Starter file API (kept)
  app/runtime/realtime.py          WebSocket bridge /ws/sessions/{id}
  app/runtime/sessions.py          REST: POST/GET/DELETE /sessions, /sessions/stats
  app/runtime/exports.py           REST: POST /sessions/{id}/exports
  app/runtime/glossary.py          REST: GET/PUT /glossary
  app/runtime/files.py / upload.py / health.py / metrics.py
packages/shared/                   Shared TS types (mirrors Pydantic)
docs/                              System of record (features, workflows, security, reliability)
```

## 2. App Identity

This is NOT a generic starter. The dashboard, sidebar, README, and feature
docs are about realtime transcription + redaction. The bucket-explorer
surface (`/files`) is intentionally kept because the same B2 bucket holds
session bundles plus any other tooling output — ops need a single tree.

**Storage convention (`b2_sessions.py` is the only path constructor):**

| Prefix | Producer | Notes |
|---|---|---|
| `sessions/<YYYY>/<MM>/<id>/manifest.json` | `service/sessions.py` + `service/realtime_session.py` | Always written |
| `sessions/<YYYY>/<MM>/<id>/transcript.redacted.json` | `service/realtime_session.py::finalize` | Always written |
| `sessions/<YYYY>/<MM>/<id>/redactions.json` | `service/realtime_session.py::finalize` | Always written |
| `sessions/<YYYY>/<MM>/<id>/transcript.original.json` | `service/realtime_session.py::finalize` | Opt-in only |
| `sessions/<YYYY>/<MM>/<id>/audio.<ext>` | `service/realtime_session.py::finalize` | Opt-in only |
| `sessions/<YYYY>/<MM>/<id>/exports/transcript.{txt,srt,vtt}` | `service/exports.py` | On demand |
| `config/glossary.json` | `service/glossary.py` | Edited from `/settings` |
| `uploads/` | `service/upload.py` | File-mode capture target, kept for `/files` consumers |

## 3. Architectural Invariants

**Backend layering**: `types -> config -> repo -> service -> runtime`

- No backward imports across layers
- `boto3` only in `repo/` (every S3 client construction sets
  `Config(user_agent_extra="b2ai-gpt-realtime-whisper-live-transcript-redactor (backblaze-b2-samples)")`)
- `websockets` client SDK only in `repo/`
- FastAPI `WebSocket` handlers only in `runtime/` — service layer stays pure
- All boundary data validated by Pydantic
- Session ids match `^[0-9]{14}-[A-Za-z0-9]{6,12}$`
- All session keys are constructed via `app.repo.b2_sessions`; never inline

**Frontend**: shadcn/ui components in `src/components/ui/` are generated —
never modify them.

**Data fetching**: every API call flows through TanStack Query hooks in
`apps/web/src/lib/queries.ts`. No bare `useEffect + fetch`. New endpoints
touch three files: `runtime/<router>.py`, `lib/api-client.ts`,
`lib/queries.ts`.

**AudioWorklet**: lives at `apps/web/public/audio-worklet.js` (top-level
URL). Do NOT move it under `src/`; the bundler will mangle the path and
`addModule()` will fail at runtime.

## 4. Quality Expectations

- DRY — extract shared code only when used in 2+ places
- Structured JSON logging only — no `print()`
- No raw SDK calls outside `repo/`
- Files stay under 300 lines (enforced by structural test)
- Tests added or updated for every behavior change
- Docs updated in same PR as code changes
- Lint clean before merge
- Prefer boring, composable libraries

## 5. Mechanical Enforcement

| Rule | Enforced by |
|------|-------------|
| No backward imports | `tests/test_structure.py::test_no_backward_imports` |
| No boto3 outside repo/ | `tests/test_structure.py::test_boto3_only_in_repo` |
| No websockets-client outside repo/ | `tests/test_structure.py::test_websockets_client_only_in_repo` |
| No FastAPI WebSocket outside runtime/ | `tests/test_structure.py::test_fastapi_websocket_only_in_runtime` |
| File size < 300 lines | `tests/test_structure.py::test_file_size_limits` |
| All layers exist | `tests/test_structure.py::test_all_layers_exist` |
| No bare print() | ruff `T20` |
| Import ordering | ruff `I001` |
| Frontend strict equality | eslint `eqeqeq` |

## 6. Commands

```bash
pnpm dev               # frontend + backend
pnpm dev:web           # frontend only
pnpm dev:api           # backend only

pnpm lint              # frontend eslint
pnpm build             # frontend type check + build
pnpm lint:api          # backend ruff
pnpm test:api          # backend pytest
pnpm check:structure   # structural boundary tests
pnpm test:e2e          # Playwright e2e
```

## 7. Agent Workflow

1. Read this file first.
2. Review [ARCHITECTURE.md](ARCHITECTURE.md) before structural changes.
3. For non-trivial changes, create a plan in `docs/exec-plans/active/`.
4. Implement the smallest coherent change.
5. Run: `pnpm lint && pnpm lint:api && pnpm test:api && pnpm check:structure`
6. Update docs in the same PR (see §9).
7. Move completed plans to `docs/exec-plans/completed/`.

## 8. Frontend Conventions

See [docs/dev-workflows.md](docs/dev-workflows.md) for full details.

## 9. Doc Update Mapping

| Change Type | Update Location |
|-------------|-----------------|
| Realtime stream / OpenAI client | `docs/features/realtime-transcription.md` |
| Redaction detectors / severity | `docs/features/redaction.md` |
| Session library / asset explorer | `docs/features/session-library.md` |
| Audit trail / manifest fields | `docs/features/audit-trail.md` |
| Export renderers | `docs/features/exports.md` |
| Custom glossary | `docs/features/custom-glossary.md` |
| `/record` + `/upload` flow | `docs/features/session-capture.md` |
| Dashboard metrics | `docs/features/dashboard.md` |
| `/files` browser | `docs/features/file-browser.md` |
| User journeys | `docs/app-workflows.md` |
| System layout | `ARCHITECTURE.md` |
| Dev / testing process | `docs/dev-workflows.md` |
| Setup / scope | `README.md` |
| Security | `docs/SECURITY.md` |
| Reliability | `docs/RELIABILITY.md` |
| Active work | `docs/exec-plans/active/` |
| Known tech debt | `docs/exec-plans/tech-debt-tracker.md` |

If documentation and implementation conflict, update docs in the same PR.

## 10. When Unsure

- Prefer boring, stable libraries
- Prefer small PRs
- Add tests with every change
- Never bypass lint rules without explicit instruction
- Ask before destructive or irreversible changes
