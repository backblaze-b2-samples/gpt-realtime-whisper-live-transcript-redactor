<!-- last_verified: 2026-05-28 -->
# Feature: Session Library

## Purpose

The sample-scoped asset explorer at `/sessions`. Lists every redaction
session with derived storage-mode badges and per-session stats. Each
row links to `/sessions/[id]` for the full split-pane detail view.

## Used By

- UI: `/sessions`, `/sessions/[id]`
- API: `GET /sessions`, `GET /sessions/stats`, `GET /sessions/stats/activity`, `GET /sessions/{id}`, `GET /sessions/{id}/transcript`, `DELETE /sessions/{id}`

## Core Files

- `apps/web/src/app/sessions/page.tsx`
- `apps/web/src/app/sessions/[id]/page.tsx`
- `apps/web/src/components/sessions/sessions-list.tsx`
- `apps/web/src/components/sessions/session-detail.tsx`
- `services/api/app/runtime/sessions.py`
- `services/api/app/service/sessions.py`
- `services/api/app/repo/b2_sessions.py`

## Why it's separate from `/files`

The `/files` route (kept from the starter) is a **bucket-wide tree**.
It surfaces every key under the bucket — `sessions/`, `uploads/`,
`config/`, plus anything else operators dump into the same bucket.

The `/sessions` route is **sample-scoped**. It only shows objects under
the `sessions/` prefix, parses session ids out of the layout, and
hydrates each row with the session manifest. Filters and badges are
domain-specific: duration, detection count, storage mode.

Per the skill's non-negotiable contract, both routes ship together.

## Library row shape

`SessionSummary` carries derived state:

- `session_id`, `created_at`, `finalized_at`, `status`
- `storage_mode` — `originals_stored` or `redacted_only`
- `duration_ms`, `detection_count`, `detection_counts_by_severity`
- `segment_count`
- `has_audio`, `has_original_transcript` — computed by HEADing the
  predictable keys via `b2_sessions.head_session_state_parallel`

The storage-mode badge uses these last two booleans rather than trusting
the manifest's stored mode — they tell you what is **actually** in B2
right now, which is the audit-correct answer.

## Detail-view transcript preview

`/sessions/[id]` fetches the redacted transcript via
`GET /sessions/{id}/transcript` (`useSessionTranscript`) and renders the
segments in a "Redacted transcript" card. The endpoint returns an empty
`Transcript` (not a 404) for a session that produced no completed
segments, so the panel degrades to an empty-state message. Only the
**redacted** variant is exposed here — the original transcript, when
stored, is reachable through `/files`, never the library detail view.

## Stats

`GET /sessions/stats` aggregates across all sessions and drives the
dashboard `StatsCards`:

- `total_sessions`, `total_duration_ms`
- `total_detections`, `detections_by_severity`
- `sessions_today`
- `storage_mode_counts` — number of sessions in each mode

## Delete cascade

`DELETE /sessions/{id}` walks the session prefix and uses
`delete_objects` to remove every object — manifest, both transcripts,
redactions JSON, audio (if present), every export — in batched 1000-key
calls.

## Verification

- Test files: `services/api/tests/test_sessions.py`
- Pass criteria: id pattern enforced, well-formed ids accepted

## Related Docs

- [Realtime Transcription](realtime-transcription.md)
- [Audit Trail](audit-trail.md)
- [File Browser](file-browser.md)
