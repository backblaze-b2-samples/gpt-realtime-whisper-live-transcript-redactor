<!-- last_verified: 2026-05-28 -->
# Feature: Exports

## Purpose

Generate `.txt`, `.srt`, or `.vtt` exports from the **redacted**
transcript on demand. Stored under `sessions/.../exports/` so presigned
download URLs are stable.

## Used By

- UI: `/sessions/[id]` exports panel
- API: `POST /sessions/{id}/exports`

## Core Files

- `services/api/app/runtime/exports.py`
- `services/api/app/service/exports.py`
- `services/api/app/types/exports.py`

## Contract

- **Input**: `{ "format": "txt" | "srt" | "vtt" }`
- **Output**: `ExportInfo` with the storage key and a 10-minute presigned URL
- **Side effect**: appends an `export.generated` audit event to the session manifest

## Format details

- **`.txt`** — one segment per line, no timestamps
- **`.srt`** — sequential cue numbers, comma-separated millisecond timestamps (`HH:MM:SS,mmm`)
- **`.vtt`** — `WEBVTT` header, period-separated millisecond timestamps (`HH:MM:SS.mmm`)

All three render strictly from the redacted transcript — there is no
code path that exports the original.

## Why no PDF / DOCX in v1

PDFs and DOCX require binary library dependencies (ReportLab,
python-docx). The point of this sample is the realtime + redaction
pipeline; a text-only export surface keeps the dependency footprint
small. Plumbing for additional formats can drop into
`service/exports.py::_RENDERERS`.

## Verification

- Test files: `services/api/tests/test_exports.py`
- Pass criteria: TXT line-per-segment; SRT comma-separated; VTT starts with `WEBVTT`

## Related Docs

- [Redaction](redaction.md)
- [Session Library](session-library.md)
