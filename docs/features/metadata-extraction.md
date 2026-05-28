<!-- last_verified: 2026-05-28 -->
# Feature: Metadata Extraction

## Purpose

Extract rich metadata for audio files uploaded via `/upload` and return
it alongside the upload result. Audio-format duration / codec / bitrate
is what matters here; the image and PDF extractors remain available for
`/files` consumers that drop non-audio content into the bucket.

## Used By

- API: `POST /upload` (called after B2 upload)
- UI: upload results, file metadata panel in `/files`

## Core Files

- `services/api/app/service/metadata.py`
- `apps/web/src/components/files/file-metadata-panel.tsx`

## Inputs

- `file_data: bytes`
- `filename: str`
- `content_type: str`

## Outputs

- `FileMetadataDetail`: filename, size, hashes (md5 + sha256), mime, extension, uploaded_at
- Audio (when extractable): `duration_seconds`, `codec`, `bitrate`
- Image / PDF fields still present in the schema for cross-tool parity, populated when applicable

## How realtime durations are tracked

`/record` sessions do **not** rely on this extractor — duration is
tracked by `service/realtime_session.py` from audio bytes received and
the sample rate. The metadata extractor is only invoked on the
file-mode `/upload` path.

## Edge Cases

- Corrupt audio / image / PDF -> per-extractor `try/except`, missing fields stay null
- Unknown content type -> only hashes + size + extension populated

## Verification

- Quick verify: `pnpm test:api`

## Related Docs

- [Session Capture](session-capture.md)
- [File Browser](file-browser.md)
