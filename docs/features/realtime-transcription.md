<!-- last_verified: 2026-05-28 -->
# Feature: Realtime Transcription

## Purpose

Stream microphone audio from the browser through a backend WebSocket
bridge into the OpenAI Realtime API and surface transcript deltas to
the UI in near-real-time.

## Used By

- UI: `/record` page, `components/record/record-controls.tsx`
- API: `WS /ws/sessions/{session_id}`

## Core Files

- `apps/web/public/audio-worklet.js` — PCM16 24kHz mono encoder (top-level URL)
- `apps/web/src/lib/audio-capture.ts` — getUserMedia + AudioWorkletNode wrapper
- `apps/web/src/components/record/record-controls.tsx` — UI state machine
- `services/api/app/runtime/realtime.py` — FastAPI WebSocket bridge
- `services/api/app/service/realtime_session.py` — per-session state machine
- `services/api/app/repo/openai_realtime_client.py` — OpenAI Realtime adapter

## WebSocket Contract

- **URL**: `wss://<api>/ws/sessions/{session_id}` (built via `realtimeSessionUrl()` in `api-client.ts`)
- **Client -> server**:
  - Binary frames: PCM16 24kHz mono chunks straight from the AudioWorklet
  - Text control frames: `{"type":"stop"}` to commit the current buffer and finalize
- **Server -> client** (JSON text frames):
  - `{"type":"delta","text":"..."}` — incremental transcription
  - `{"type":"segment","segment":{...},"detections":[...]}` — finalized utterance with redaction result
  - `{"type":"error","message":"..."}` — upstream error
  - `{"type":"finalized","session_id":"...","segment_count":N,"detection_count":M}` — bundle persisted

## OpenAI Realtime config

- `modalities: ["text"]` — no LLM responses, transcription only
- `input_audio_format: "pcm16"` (24kHz mono)
- `input_audio_transcription.model: <OPENAI_REALTIME_MODEL>` — default `gpt-realtime-whisper`
- `turn_detection: {"type": "server_vad"}` — server decides segment boundaries

## Browser audio path

Float32 mic input -> AudioWorklet `pcm16-encoder` -> ~40ms PCM16 chunks
posted via `MessagePort` -> WebSocket binary frame.

The worklet does a simple linear-interpolation downsample from the
AudioContext's native rate (typically 44.1k/48k) to 24kHz, then clamps
each Float32 sample to Int16.

## Reconnection and fail-soft

- If the OpenAI key is missing, the bridge sends a single `error` event and
  closes with code `1011`. The session manifest is marked `errored` and
  persisted so the audit trail reflects the failure.
- If the browser disconnects without sending `stop`, the bridge still
  calls `finalize()` on its way out — partial transcripts are persisted.
- A reconnect attempt requires creating a new session (a new id) — the
  existing session is finalized, not resumed. v2 may add resumption.

## Non-goals (v1)

- No diarization / speaker labels
- No client-side fallback for browsers without AudioWorklet support — these get an `ErrorState`
- No realtime cost meter — token/audio billing is the operator's responsibility

## Verification

- Test files: structural test enforces `websockets` only in `repo/` and FastAPI WebSocket only in `runtime/`
- Pass criteria: `pnpm check:structure` green; `/record` e2e smoke test renders the page

## Related Docs

- [Redaction](redaction.md)
- [Audit Trail](audit-trail.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
