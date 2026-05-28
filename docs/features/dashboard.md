<!-- last_verified: 2026-05-28 -->
# Feature: Dashboard

## Purpose

At-a-glance view of redaction-session activity and storage-mode mix.

## Used By

- UI: `/` (home)
- API: `GET /sessions/stats`, `GET /sessions`, `GET /sessions/stats/activity`

## Core Files

- `apps/web/src/app/page.tsx`
- `apps/web/src/components/dashboard/stats-cards.tsx`
- `apps/web/src/components/dashboard/recent-sessions-table.tsx`
- `apps/web/src/components/dashboard/session-chart.tsx`
- `services/api/app/runtime/sessions.py`
- `services/api/app/service/sessions.py`

## Metrics

Stats cards display:

- **Total Sessions** — count of finalized + recording sessions in the bucket
- **Total Duration** — sum of `duration_ms` across all sessions, humanized
- **Detections** — sum of `detection_count`
- **Sessions Today** — `created_at` filter

The chart plots sessions and detections per day for the last 7 days.

The recent-sessions table shows the latest 10 sessions with storage-mode
badges (`Originals stored` / `Redacted only`).

## Flow

- Page loads -> parallel API calls: stats, recent sessions, activity
- Errors render via `ErrorState` with a Retry — never silent empty UI
- TanStack Query handles refetch-on-focus, so the dashboard self-heals

## Verification

- Test files: `services/api/tests/test_sessions.py` covers the id pattern; e2e smoke renders the dashboard
- Quick verify: `pnpm test:api`

## Related Docs

- [Session Library](session-library.md)
- [Realtime Transcription](realtime-transcription.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
