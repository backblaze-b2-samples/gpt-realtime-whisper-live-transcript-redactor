<!-- last_verified: 2026-05-28 -->
# App Workflows

User journeys inside the application.

## Live-record a session

- User navigates to `/record`
- Optionally adjusts the per-session toggles (which redaction layers, whether to store originals)
- Clicks **Start recording** — the browser requests mic permission, the AudioWorklet starts capturing PCM16 24kHz mono, and the WebSocket bridge connects to OpenAI Realtime via the backend
- As OpenAI sends transcript deltas, italicized text accumulates in the transcript pane
- When a segment is finalized, the backend runs the three-layer redaction pass and pushes a `segment` event back; the UI renders the redacted text and severity chips for each detection
- User clicks **Stop** — the backend finalizes the session bundle (manifest, redacted transcript, redactions JSON, plus opt-in originals/audio) and persists everything to B2
- See: [Realtime Transcription](features/realtime-transcription.md), [Redaction](features/redaction.md), [Audit Trail](features/audit-trail.md)

## Review a past session

- User navigates to `/sessions`
- Library shows each session with duration, detection counts, and a storage-mode badge (`Originals stored` / `Redacted only`)
- Clicking a row opens `/sessions/[id]`
- Detail page renders the session summary, the append-only audit event log, and the export panel
- If originals were stored, the unredacted transcript and an inline audio player are also available
- User can delete the session — the backend cascades deletion across every object under the prefix
- See: [Session Library](features/session-library.md)

## Export a redacted variant

- From `/sessions/[id]`, user picks `.txt`, `.srt`, or `.vtt`
- Backend renders the export from the **redacted** transcript JSON only (never the original)
- Result is written to `sessions/.../exports/transcript.<fmt>` and returned with a presigned URL
- An `export.generated` event is appended to the manifest
- See: [Exports](features/exports.md)

## Configure the custom glossary

- User navigates to `/settings`
- Adds terms (project codenames, customer names, internal jargon) with per-term severity
- Saving PUTs the full list to `/glossary`, which writes `config/glossary.json` in B2
- Subsequent sessions load the glossary at start and apply case-insensitive whole-word matching alongside the built-in PII and secrets detectors
- See: [Custom Glossary](features/custom-glossary.md)

## Browse the bucket (ops view)

- User navigates to `/files`
- Sees the full tree — `sessions/`, `config/`, `uploads/`, plus any external tools' output
- Preview / download / delete still work per the starter contract
- See: [File Browser](features/file-browser.md)
