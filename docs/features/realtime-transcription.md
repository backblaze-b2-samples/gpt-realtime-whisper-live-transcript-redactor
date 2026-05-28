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

The client targets the **GA** Realtime API shape. We connect to
`wss://api.openai.com/v1/realtime?intent=transcription` with only an
`Authorization: Bearer` header — the legacy `OpenAI-Beta: realtime=v1`
header is **not** sent (it now triggers `beta_api_shape_disabled`). The
session is configured with a single `session.update`:

- `session.type: "transcription"`
- `session.audio.input.format: {"type": "audio/pcm", "rate": 24000}` (24kHz mono)
- `session.audio.input.transcription.model: <OPENAI_REALTIME_MODEL>` — default `gpt-realtime-whisper`

`turn_detection` is intentionally **omitted**: `gpt-realtime-whisper`
rejects it ("Turn detection is not supported for this transcription
model"). Incremental `delta` events still stream live as audio arrives;
the finalized `completed` event (which drives redaction) is produced when
the bridge issues an explicit `commit()` on `stop`. A recording therefore
yields one finalized segment covering the whole turn.

> Requires `websockets` >= 14 (`additional_headers`, `ClientConnection`).

## Browser audio path

Float32 mic input -> AudioWorklet `pcm16-encoder` -> ~40ms PCM16 chunks
posted via `MessagePort` -> WebSocket binary frame.

The worklet does a simple linear-interpolation downsample from the
AudioContext's native rate (typically 44.1k/48k) to 24kHz, then clamps
each Float32 sample to Int16.

## Reconnection and fail-soft

- On `stop` (or browser disconnect), the bridge issues a final `commit()`
  and waits up to 15s for the trailing `completed` transcript before tearing
  down — without this the last (and, for `gpt-realtime-whisper`, the only)
  utterance would be lost.
- If the OpenAI key is missing, the bridge sends a single `error` event and
  closes with code `1011`. The session manifest is marked `errored` and
  persisted (and `finalize()` is skipped so it is not overwritten back to
  `finalized`).
- If the browser disconnects without sending `stop`, the bridge still
  commits and calls `finalize()` on its way out — the partial turn is
  transcribed and persisted. All client sends after a disconnect are
  best-effort and never crash the handler.
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
