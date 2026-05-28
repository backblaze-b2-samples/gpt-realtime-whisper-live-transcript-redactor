<!-- last_verified: 2026-05-28 -->
# Feature: Session Capture

## Purpose

Two ways to feed audio into the realtime redaction pipeline:

- **`/record`** — live microphone streaming via `AudioWorklet` + WebSocket
- **`/upload`** — drop in an existing audio file and stream it through the
  **same** realtime pipeline (no second code path; the file is decoded
  to PCM16 24 kHz mono and fed to `OpenAIRealtimeClient` exactly like a
  live mic stream)

## Used By

- UI: `/record`, `/upload`
- API: `WS /ws/sessions/{id}`, `POST /sessions`, `POST /sessions/upload`,
  `POST /upload` (legacy bucket-explorer ingest at `uploads/`)

## Core Files

### Live recording

- `apps/web/src/app/record/page.tsx`
- `apps/web/src/components/record/record-controls.tsx`
- `apps/web/src/lib/audio-capture.ts`
- `apps/web/public/audio-worklet.js`
- `services/api/app/runtime/realtime.py`
- `services/api/app/service/realtime_session.py`

### File-mode pipeline upload

- `apps/web/src/app/upload/page.tsx`
- `apps/web/src/components/upload/pipeline-upload-form.tsx`
- `services/api/app/runtime/session_upload.py`
- `services/api/app/service/audio_decode.py`
- `services/api/app/service/realtime_session.py` (shared with `/record`)
- `services/api/app/repo/openai_realtime_client.py` (shared with `/record`)

### Legacy bucket-explorer ingest (`/files` consumers only)

- `services/api/app/runtime/upload.py`
- `services/api/app/service/upload.py`

The legacy `/upload` route remains for parity with the bucket-explorer
(`/files`) — drop any audio file at `uploads/<name>` for ops viewing. It
no longer powers the `/upload` page.

## POST /sessions contract

Creates a session manifest with per-session options:

```json
{
  "redaction_modes": ["pii", "secrets", "glossary"],
  "store_original_audio": true,
  "store_original_transcript": true
}
```

All fields are optional; missing fields fall back to env defaults
(`REDACTION_DEFAULT_MODES`, `SESSION_STORE_ORIGINALS_DEFAULT`). Response
echoes the resolved values + the generated `session_id`.

## POST /sessions/upload contract

Pipeline-mode ingest. Accepts a multipart `file` field with a WAV
payload (PCM16 / PCM8, mono or stereo, any sample rate up to ~30 min
decoded duration). The handler:

1. Reads the file (size capped by `MAX_FILE_SIZE`).
2. Decodes to PCM16 24 kHz mono via `service/audio_decode.py`.
3. Creates a session with env defaults (`POST /sessions` semantics).
4. Opens an `OpenAIRealtimeClient` and streams the PCM in
   ~100 ms frames with a small inter-frame sleep (so deltas have room
   to flow back).
5. Commits the buffer, drains the resulting
   `conversation.item.input_audio_transcription.completed` events
   into the shared `RealtimeSessionState`, and finalizes the bundle.
6. When `SESSION_STORE_ORIGINALS_DEFAULT=true` (the v1 default), the
   **original WAV** is persisted to `sessions/.../audio.wav`. We deliberately
   do NOT write the in-flight resampled PCM — only the playable file.

Response:

```json
{
  "session_id": "20260528103045-abc12345",
  "segment_count": 5,
  "detection_count": 2,
  "duration_ms_received": 12345
}
```

### v1 format constraint

Pipeline-mode upload accepts **WAV only**. MP3 / WebM / M4A / OGG / FLAC
need a heavy native decoder (ffmpeg / pyav) and would balloon the
sample's dependency footprint. They are documented v2 work; the
endpoint 415s anything else. Users with non-WAV audio can convert
locally (`ffmpeg -i in.m4a -ar 24000 -ac 1 out.wav`) or use
`/record` to capture live.

The legacy `POST /upload` content-type allowlist is unchanged (it
keeps ingesting all audio MIME types to `uploads/` for `/files`); only
the pipeline path is WAV-only.

## /upload (legacy) contract

`POST /upload` accepts MP3 / WAV / WebM / OGG / M4A / FLAC and writes
to `uploads/<sanitized-name>` for the bucket explorer. It does **not**
open a realtime session.

## Edge cases

- Browser without AudioWorklet support: `startCapture` throws, UI shows an `ErrorState`
- OpenAI key missing: bridge sends `error` event and closes
- File > 100MB: client rejects pre-flight, server enforces with 413
- Non-audio content-type: server rejects with 415

## Related Docs

- [Realtime Transcription](realtime-transcription.md)
- [Redaction](redaction.md)
- [Session Library](session-library.md)
