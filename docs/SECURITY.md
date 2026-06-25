<!-- last_verified: 2026-05-28 -->
# Security

Security principles and implementation for `gpt-realtime-whisper-live-transcript-redactor`.

## Trust Boundaries

- **Frontend -> API**: CORS-restricted to configured origins, scoped to `GET/POST/PUT/DELETE/OPTIONS`
- **API -> B2**: Authenticated via `B2_APPLICATION_KEY_ID` + `B2_APPLICATION_KEY`, signature v4, every S3 client carries `user_agent_extra="b2ai-gpt-realtime-whisper-live-transcript-redactor (backblaze-b2-samples)"`
- **API -> OpenAI Realtime**: Authenticated via `OPENAI_API_KEY` over WSS, never relayed to the browser
- **Client -> B2**: Presigned URLs for download (10-min expiry, `Content-Disposition: attachment` for exports)

`B2_REGION` is validated as a Backblaze region token before the API
derives `https://s3.<region>.backblazeb2.com` for boto3. During the B2
env-name migration, the API still accepts `B2_KEY_ID` and `B2_PUBLIC_URL`
as fallbacks and ignores leftover `B2_ENDPOINT`; standardized names take
precedence when both old and new values are present.

## Storage mode — default flip for production

`SESSION_STORE_ORIGINALS_DEFAULT` controls whether raw audio and the
**unredacted** transcript are persisted alongside the redacted bundle.
v1 ships with this flag set to `true` for development convenience — you
can replay the audio and compare original vs redacted transcripts — but
**the production default should be `false`**.

The README's [Production Configuration](../README.md#-production-configuration-read-this-before-deploying)
callout has the operator-facing version of this guidance. Mirrored here
so anyone reading the security docs in isolation also discovers it:

1. Set `SESSION_STORE_ORIGINALS_DEFAULT=false` in your deployment env.
   With the env-var default flipped, sessions write only the redacted
   transcript, redaction manifest, and audit-trail event log. Raw audio
   and the unredacted transcript are skipped entirely.
2. Configure a B2 Lifecycle Rule to expire `sessions/*/audio.*` and
   `sessions/*/transcript.original.json` on a short schedule (e.g. 24h).
   This bounds the blast radius of any per-session opt-in to "store
   originals" — even if an operator flips the toggle on for debugging,
   the originals don't linger.
3. The per-session toggles on `/record` and the defaults on `/settings`
   override the env-var default in either direction. An operator can
   leave the default at `false` and grant per-session opt-in for
   short-lived debugging.

The [Redaction feature doc](features/redaction.md#storage-mode-and-the-production-default-flip)
covers the full storage-mode discussion including how the manifest
records what was preserved vs purged.

## Realtime audio handling

- Browser captures audio at PCM16 24kHz mono via `apps/web/public/audio-worklet.js`
- Frames are pushed binary-only to `/ws/sessions/{id}` — never JSON-wrapped
- The bridge appends to the manifest's `audio_bytes_received` counter for every chunk; the buffered raw bytes are kept in memory only when `store_original_audio=true`
- If the OpenAI Realtime connection fails mid-session, the bridge marks the manifest `errored`, persists the audit event, and closes the socket

## Upload Validation (file-mode `/upload`)

- Filename sanitization: path traversal, null bytes, unsafe chars stripped
- Content-type allowlist: audio only (MP3, WAV, WebM, OGG, M4A, FLAC)
- MIME/extension consistency check
- Chunked streaming with 100MB enforcement
- Empty file rejection

## Key Validation

- Empty keys rejected
- Path traversal patterns rejected (`../`, `%2e%2e`, backslashes, null bytes)
- Session ids validated against `^[0-9]{14}-[A-Za-z0-9]{6,12}$`
- The bucket is the only access boundary — add prefix scoping in
  `services/api/app/service/files.py::validate_key` if your deployment
  shares a bucket with other workloads

## Audit Trail

Every session writes an append-only `events[]` array inside its
`manifest.json`. Events include `session.started`, `streaming.started`,
`transcript.completed` (with `original_text_sha256`), `redaction.applied`
(with detection count + types), `export.generated`, and
`session.finalized`. An auditor can verify the redacted transcript
against the manifest hashes without needing the originals.

See [Audit Trail](features/audit-trail.md) for the schema.

## Secrets Management

- All secrets loaded via environment variables (pydantic-settings)
- Never committed to source control
- `.env.example` documents required variables without values
- `OPENAI_API_KEY` is required for `/record` but optional for the rest of the app — missing keys degrade `/health` to `degraded` rather than failing the API

## Agent Security Rules

- Never commit `.env`, credentials, or API keys
- Never weaken validation without explicit instruction
- Never bypass CORS, auth, or input sanitization
- Always validate at system boundaries
