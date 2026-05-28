<!-- last_verified: 2026-05-28 -->
# Feature: Session Capture

## Purpose

Two ways to feed audio into the realtime redaction pipeline:

- **`/record`** — live microphone streaming via `AudioWorklet` + WebSocket
- **`/upload`** — drop in an existing audio file (MP3 / WAV / WebM / OGG / M4A / FLAC)

## Used By

- UI: `/record`, `/upload`
- API: `WS /ws/sessions/{id}`, `POST /sessions`, `POST /upload`

## Core Files

### Live recording

- `apps/web/src/app/record/page.tsx`
- `apps/web/src/components/record/record-controls.tsx`
- `apps/web/src/lib/audio-capture.ts`
- `apps/web/public/audio-worklet.js`
- `services/api/app/runtime/realtime.py`
- `services/api/app/service/realtime_session.py`

### File-mode upload

- `apps/web/src/app/upload/page.tsx`
- `apps/web/src/components/upload/upload-form.tsx`
- `apps/web/src/components/upload/dropzone.tsx`
- `services/api/app/runtime/upload.py`
- `services/api/app/service/upload.py`

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

## /upload contract

`POST /upload` is now audio-only — the content-type allowlist in
`service/upload.py` matches what OpenAI Realtime can ingest. The
uploaded file is stored at `uploads/<sanitized-name>` under the
starter's existing path so `/files` keeps working. v1 does NOT
automatically open a realtime session for an uploaded file — that's
documented as a v2 expansion in the upload UI.

## Edge cases

- Browser without AudioWorklet support: `startCapture` throws, UI shows an `ErrorState`
- OpenAI key missing: bridge sends `error` event and closes
- File > 100MB: client rejects pre-flight, server enforces with 413
- Non-audio content-type: server rejects with 415

## Related Docs

- [Realtime Transcription](realtime-transcription.md)
- [Redaction](redaction.md)
- [Session Library](session-library.md)
