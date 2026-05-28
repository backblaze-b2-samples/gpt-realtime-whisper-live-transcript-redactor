<!-- last_verified: 2026-03-10 -->
# Tech Debt Tracker

Known tech debt items. Agents update this when they discover or create tech debt.

| Description | Impact | Proposed Resolution | Priority | Status |
|---|---|---|---|---|
| `datetime.utcnow()` deprecated in Python 3.12+ | Naive datetimes, future breakage | Replace with `datetime.now(UTC)` in `repo/b2_client.py`, `service/metadata.py` | High | Resolved |
| S3 client recreated on every API call | Connection pool wasted, added latency | Cache client as module-level singleton via `lru_cache` | High | Resolved |
| `get_upload_stats()` pagination broken at 1000 objects | Stats silently wrong for large buckets | Check `IsTruncated` + use `ContinuationToken` | High | Resolved |
| `record_upload()` never called | `/metrics` always reports 0 uploads | Call from `runtime/upload.py` after successful upload | Medium | Resolved |
| Metrics counters not thread-safe | Race conditions under concurrent requests | Use `threading.Lock` (matches `service/files.py` pattern) | Medium | Resolved |
| `_humanize_bytes` duplicated in Python (repo + service) | DRY violation, drift risk | Extract to `app/types/formatting.py` shared util | Medium | Resolved |
| `humanizeBytes` duplicated in TypeScript | DRY violation | Extract to `lib/utils.ts` | Low | Open |
| `formatDate` duplicated in TypeScript | DRY violation | Extract to `lib/utils.ts` | Low | Open |
| No test harness for feature specs | No automated verification | Add pytest fixtures + test files per feature | Medium | Resolved (partial — tests added for upload, files, activity, errors) |
| Replace `audioop` for Python 3.13+ compatibility | `requires-python` is pinned to `<3.13` because `audio_decode.py` imports the stdlib `audioop` module, which was removed in 3.13. Blocks running the backend on current upstream Python. | Replace the three `audioop` calls used in `services/api/app/service/audio_decode.py` with pure-Python equivalents (~10 lines each): `audioop.ratecv` (linear resampling), `audioop.tomono` (stereo→mono downmix with per-channel weights), and `audioop.lin2lin` (PCM8→PCM16 width promotion). Each is small and well-specified; reference implementations exist in the CPython history and in the `audioop-lts` PyPI backport. Deliverable: drop `requires-python = "<3.13"` from `services/api/pyproject.toml` and the matching guard in `scripts/doctor.mjs`. | Medium | Open |
