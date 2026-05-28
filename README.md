<!-- last_verified: 2026-05-28 -->
# GPT-Realtime-Whisper Live Transcript Redactor

Stream microphone audio through OpenAI's GPT-Realtime-Whisper, redact PII / secrets / custom terms inline, and ship a privacy-default session bundle to **[Backblaze B2](https://www.backblaze.com/sign-up/ai-cloud-storage?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-gpt-realtime-whisper-live-transcript-redactor)** — compliance evidence and audit trail included, raw audio kept only on explicit opt-in.

**What you get out of the box:**
- Live `/record` page that streams the mic to OpenAI Realtime and renders transcript deltas with inline redaction chips
- Three-layer deterministic redaction (PII regex, secret patterns, custom glossary) with severity-tagged detections
- B2-backed session bundles: redacted transcript + redaction manifest + append-only audit trail are always written; raw audio + original transcript only on opt-in
- Per-session library at `/sessions`, full bucket explorer at `/files`, and a settings page with a custom-glossary editor
- Export pipeline producing redacted `.txt`, `.srt`, and `.vtt` from the redacted transcript JSON

## What it looks like

- `/record` — start/stop the live stream, watch the transcript form, see redactions land as severity-coloured chips
- `/sessions` — sample-scoped library of redaction sessions with storage-mode badges
- `/sessions/[id]` — split-pane detail page: redacted transcript (always) + original (if stored), redaction manifest, audit-trail event log, exports
- `/files` — full B2 bucket explorer (kept from the starter; ops can see every artifact)

## Quick Start

You need: Node.js >= 20, pnpm >= 9, Python >= 3.11, < 3.13[^audioop], a free **[Backblaze B2 account](https://www.backblaze.com/sign-up/ai-cloud-storage?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-gpt-realtime-whisper-live-transcript-redactor)**, and an **[OpenAI API key](https://platform.openai.com/api-keys)**.

[^audioop]: The WAV decoder in `services/api/app/service/audio_decode.py` depends on the stdlib `audioop` module, which was removed in Python 3.13. Tracking the upgrade is on the tech-debt tracker.

```bash
git clone https://github.com/backblaze-b2-samples/gpt-realtime-whisper-live-transcript-redactor.git
cd gpt-realtime-whisper-live-transcript-redactor

pnpm install

cd services/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ../..

cp .env.example .env  # then fill in B2_* and OPENAI_API_KEY

pnpm dev
```

`pnpm dev` runs `pnpm doctor` first — a preflight check that catches the common setup gotchas (wrong Node/Python version, missing venv, missing or placeholder `.env`, missing `apps/web/public/audio-worklet.js`, ports already taken). Run it standalone any time with `pnpm doctor`.

> ## ⚠️ Production Configuration (read this before deploying)
>
> **v1 ships with `SESSION_STORE_ORIGINALS_DEFAULT=true`.** This is convenient
> for development testing — you can replay audio and compare original vs
> redacted transcripts side-by-side — but it is the **wrong default for any
> real compliance-sensitive deployment**.
>
> Before you ship this app to production:
>
> 1. Set `SESSION_STORE_ORIGINALS_DEFAULT=false` in your deployment env.
>    Sessions will then write only the redacted transcript, redaction
>    manifest, and audit-trail event log; the raw audio and unredacted
>    transcript are skipped entirely.
> 2. Configure a B2 bucket **Lifecycle Rule** to expire
>    `sessions/*/audio.*` and `sessions/*/transcript.original.json` on
>    a short schedule (e.g. 24h) so any per-session opt-in to "store
>    originals" is bounded.
> 3. Audit your operators: per-session toggles on `/record` and defaults on
>    `/settings` override the env-var default in either direction. An
>    operator can leave the default at `false` and grant per-session
>    opt-in for debugging.
> 4. Read [docs/SECURITY.md](docs/SECURITY.md#storage-mode--default-flip-for-production)
>    and [docs/features/redaction.md](docs/features/redaction.md#storage-mode-and-the-production-default-flip)
>    for the full discussion.

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `B2_ENDPOINT` | yes | B2 S3-compatible endpoint URL |
| `B2_REGION` | yes | B2 region (e.g. `us-west-004`) |
| `B2_KEY_ID` | yes | B2 application key ID |
| `B2_APPLICATION_KEY` | yes | B2 application key secret |
| `B2_BUCKET_NAME` | yes | B2 bucket to use as the storage of record |
| `OPENAI_API_KEY` | yes | Drives realtime transcription via OpenAI Realtime |
| `OPENAI_REALTIME_MODEL` | no | Defaults to `gpt-realtime-whisper` |
| `REDACTION_DEFAULT_MODES` | no | Comma list of `pii,secrets,glossary`; per-session toggles override |
| `SESSION_STORE_ORIGINALS_DEFAULT` | no | `true` (dev default) / `false` (production recommended) |
| `API_CORS_ORIGINS` | no | Comma list of allowed origins for the API (defaults: `http://localhost:3000,http://localhost:3001`) |

See `.env.example` for the full annotated file.

## Core Features

- [Realtime Transcription](docs/features/realtime-transcription.md) — WebSocket bridge from browser PCM16 to OpenAI Realtime
- [Layered Redaction](docs/features/redaction.md) — three deterministic detectors (PII, secrets, glossary) with severity
- [Session Library](docs/features/session-library.md) — the sample-scoped asset explorer at `/sessions`
- [Audit Trail](docs/features/audit-trail.md) — append-only manifest event log + sha256 hashes for verification
- [Exports](docs/features/exports.md) — redacted-only `.txt`, `.srt`, `.vtt`
- [Custom Glossary](docs/features/custom-glossary.md) — case-insensitive whole-word redaction terms editable from `/settings`
- [Session Capture](docs/features/session-capture.md) — `/record` (live) + `/upload` (file-mode) into the same pipeline
- [File Browser](docs/features/file-browser.md) — the starter's full-bucket tree view, kept
- [Dashboard](docs/features/dashboard.md) — sessions / minutes / detections / storage-mode breakdown
- [Metadata Extraction](docs/features/metadata-extraction.md) — kept for `/files` consumers

## Tech Stack

- TypeScript, Next.js 16, React 19, Tailwind v4, shadcn/ui, Recharts
- TanStack Query — caching, dedup, retry, stale-while-revalidate for every fetch
- Python 3.11+ (< 3.13 — see Quick Start footnote), FastAPI, boto3, Pydantic v2, `websockets` (OpenAI Realtime upstream)
- Backblaze B2 (S3-compatible object storage)
- OpenAI Realtime API (transcription only, no LLM redaction in v1)
- pnpm workspaces (monorepo)

## Commands

| Command | What it does |
|---------|-------------|
| `pnpm dev` | Start frontend + backend |
| `pnpm dev:web` | Frontend only |
| `pnpm dev:api` | Backend only |
| `pnpm build` | Build frontend |
| `pnpm lint` | Lint frontend |
| `pnpm lint:api` | Lint backend (ruff) |
| `pnpm test:api` | Run backend tests |
| `pnpm check:structure` | Verify layering rules + WebSocket boundary |
| `pnpm test:e2e` | Playwright e2e tests (run `pnpm --filter @gpt-realtime-whisper-live-transcript-redactor/web exec playwright install chromium` once first) |

## Documentation Map

| Doc | Purpose |
|-----|---------|
| [AGENTS.md](AGENTS.md) | Agent table of contents — start here |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System layout, layering, data flows, realtime pipeline |
| [docs/features/](docs/features/) | Feature docs (realtime, redaction, sessions, audit, exports, glossary, files, dashboard) |
| [docs/design-system.md](docs/design-system.md) | Design tokens, primitives, AI elements |
| [docs/app-workflows.md](docs/app-workflows.md) | User journeys |
| [docs/dev-workflows.md](docs/dev-workflows.md) | Engineering workflows and testing |
| [docs/SECURITY.md](docs/SECURITY.md) | Security principles incl. storage-mode flip |
| [docs/RELIABILITY.md](docs/RELIABILITY.md) | Reliability expectations |
| [docs/exec-plans/](docs/exec-plans/) | Execution plans and tech debt tracker |

## License

MIT License - see [LICENSE](LICENSE) for details.

## Derived from

This sample is derived from [`vibe-coding-starter-kit`](https://github.com/backblaze-b2-samples/vibe-coding-starter-kit) — see the rename history in `docs/exec-plans/completed/`.

## Claude Agent B2 Skill

Manage Backblaze B2 from your terminal using natural language (list/search, audits, stale or large file detection, security checks, safe cleanup).

Repo: [https://github.com/backblaze-b2-samples/claude-skill-b2-cloud-storage](https://github.com/backblaze-b2-samples/claude-skill-b2-cloud-storage)
