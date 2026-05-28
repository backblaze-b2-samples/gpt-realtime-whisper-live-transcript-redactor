<!-- last_verified: 2026-05-28 -->
# Feature: Audit Trail

## Purpose

Every session bundle carries an append-only `events[]` array inside its
`manifest.json`. The audit trail is how an auditor verifies what the
backend saw and what it persisted — independent of whether the
originals are still around.

## Used By

- API: every `runtime/realtime.py` and `service/realtime_session.py` call appends events; `runtime/sessions.py` returns the manifest
- UI: `/sessions/[id]` renders the event log

## Event types

| Type | When | Detail fields |
|---|---|---|
| `session.started` | `POST /sessions` accepts | `redaction_modes`, `storage_mode` |
| `streaming.started` | WebSocket bridge accepts | (empty) |
| `audio.received` | every ~5 s of audio + once at finalize for the tail | `bytes_received`, `duration_ms_received` |
| `transcript.completed` | each finalized utterance | `segment_index`, `original_text_sha256` |
| `redaction.applied` | per segment, only if detections fired | `segment_index`, `count`, `types` |
| `export.generated` | `POST /sessions/{id}/exports` | `format`, `key`, `size_bytes` |
| `session.finalized` | bridge finishes finalize | `segment_count`, `detection_count` |
| `session.errored` | bridge crashes or upstream returns error | `message` |

### `audio.received` cadence

The bridge emits an `audio.received` event after every
`AUDIO_RECEIVED_EVENT_INTERVAL_BYTES` (~5 seconds of 24 kHz PCM16 mono =
240 000 bytes) and once more at finalize to capture the tail window.
A 30-minute session therefore produces ~360 events — coarse enough to
keep manifests small, fine enough to give an auditor a timeline of when
audio actually arrived. The aggregate counter
`manifest.audio_bytes_received` is updated on every chunk and provides
the session-level rollup that the per-window events do not replace.

## Schema

```jsonc
{
  "session_id": "20260528103045-abc12345",
  "created_at": "...",
  "finalized_at": "...",
  "status": "finalized",
  "storage_mode": "originals_stored",
  "store_original_audio": true,
  "store_original_transcript": true,
  "redaction_modes": ["pii", "secrets", "glossary"],
  "model": "gpt-realtime-whisper",
  "duration_ms": 12345,
  "audio_bytes_received": 123456,
  "segment_count": 7,
  "detection_count": 3,
  "detection_counts_by_severity": { "high": 1, "medium": 2 },
  "original_text_sha256": "deadbeef...",
  "redacted_text_sha256": "cafef00d...",
  "audio_extension": "webm",
  "events": [ ... ]
}
```

## Verifying a session

1. Read `manifest.json` — confirm `redacted_text_sha256` matches the
   sha256 of `transcript.redacted.json`'s segment texts concatenated by
   `" "`.
2. Walk the `events[]` log; for each `transcript.completed` event,
   confirm the per-segment original sha256 matches the corresponding
   segment in `transcript.original.json` (when stored).
3. Walk `redactions.json`; confirm every detection has a corresponding
   `[REDACTED:<TYPE>]` token in the redacted transcript at the
   reconstructed offset.

If originals were not stored, you can still verify the manifest is
internally consistent (event log lines up with `segment_count` and
`detection_count`) — you simply cannot independently re-hash the
originals.

## Related Docs

- [Redaction](redaction.md) (counts_by_severity origin)
- [Realtime Transcription](realtime-transcription.md)
- [SECURITY.md](../SECURITY.md)
