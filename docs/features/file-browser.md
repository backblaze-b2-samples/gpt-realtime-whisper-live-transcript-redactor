<!-- last_verified: 2026-05-28 -->
# Feature: File Browser

The `/files` route is the **full bucket explorer** kept from the starter.
It surfaces every key under the configured B2 bucket — `sessions/`,
`config/`, `uploads/`, and anything else that ends up in the same
bucket. Use `/sessions` for the sample-scoped session library.

## Purpose

List, preview, download, and delete every file in the bucket — including
session bundle artifacts (manifest.json, transcripts, exports) so ops can
audit the raw tree.

## Used By

- UI: `/files`, file browser component
- API: `GET /files`, `GET /files/{key}`, `GET /files/{key}/download`, `GET /files/{key}/preview`, `DELETE /files/{key}`

## Core Files

- `apps/web/src/components/files/file-browser.tsx` — tree view with expand/collapse folders, type-specific icons, hover actions
- `apps/web/src/components/files/file-preview.tsx` — preview dialog
- `apps/web/src/components/files/file-metadata-panel.tsx` — structured metadata display
- `apps/web/src/lib/file-tree.ts` — flat keys to folder hierarchy
- `apps/web/src/lib/api-client.ts` — `getFiles()`, `getDownloadUrl()`, `deleteFile()`
- `services/api/app/runtime/files.py` — HTTP handlers
- `services/api/app/service/files.py` — key validation, business logic
- `services/api/app/repo/b2_client.py` — `list_files()`, `get_file_metadata()`, `get_presigned_url()`, `delete_file()`

## Prefixes you will see

| Prefix | Owner | When to use the dedicated UI |
|---|---|---|
| `sessions/` | redaction sessions | `/sessions` library |
| `config/` | glossary | `/settings` editor |
| `uploads/` | file-mode session capture target | `/upload` |

`/files` is the right tool when you need to inspect a raw object,
download an export by its key, or remove a session artifact out-of-band.

## Outputs

- `GET /files` -> `FileMetadata[]` (sorted most-recent-first)
- `GET /files/{key}` -> `FileMetadata`
- `GET /files/{key}/download` -> `{url}` (presigned, attachment disposition, 10-min expiry; bumps the download counter)
- `GET /files/{key}/preview` -> `{url}` (inline disposition, 10-min expiry; does NOT count as a download)
- `DELETE /files/{key}` -> `{deleted: true, key}`

## Edge Cases

- File not found -> 404
- Invalid file key (traversal attempt, empty key) -> 400
- B2 unreachable -> 500 with the global handler returning a safe message
- Empty bucket -> "No files found" state

## Verification

- Test files: `services/api/tests/test_recent_files.py`, `test_delete.py`, `test_download_stats.py`, `test_error_handling.py`
- Quick verify: `pnpm test:api`

## Related Docs

- [Session Library](session-library.md) — the sample-scoped counterpart
- [Session Capture](session-capture.md)
