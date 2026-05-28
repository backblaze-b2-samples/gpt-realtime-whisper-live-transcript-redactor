"""B2 data access for the session-bundle prefix layout.

Every session lives at `sessions/<YYYY>/<MM>/<session-id>/` and is the
unit of read / write / delete. This module is the only place where
session keys are constructed — callers pass session ids, not paths.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from botocore.exceptions import ClientError

from app.config import settings
from app.repo.b2_client import get_s3_client
from app.types.exports import ExportFormat
from app.types.sessions import SessionManifest

SESSIONS_PREFIX = "sessions"
GLOSSARY_KEY = "config/glossary.json"

# Audio extensions we accept on the file-mode /upload endpoint.
AUDIO_EXTENSIONS = ("webm", "mp3", "wav", "m4a", "ogg", "flac")


def session_prefix(session_id: str) -> str:
    """Derive `sessions/YYYY/MM/<id>/` from the session id timestamp."""
    yyyy = session_id[0:4]
    mm = session_id[4:6]
    return f"{SESSIONS_PREFIX}/{yyyy}/{mm}/{session_id}/"


def manifest_key(session_id: str) -> str:
    return f"{session_prefix(session_id)}manifest.json"


def transcript_redacted_key(session_id: str) -> str:
    return f"{session_prefix(session_id)}transcript.redacted.json"


def transcript_original_key(session_id: str) -> str:
    return f"{session_prefix(session_id)}transcript.original.json"


def redactions_key(session_id: str) -> str:
    return f"{session_prefix(session_id)}redactions.json"


def audio_key(session_id: str, extension: str) -> str:
    ext = extension.lstrip(".").lower()
    return f"{session_prefix(session_id)}audio.{ext}"


def export_key(session_id: str, fmt: ExportFormat) -> str:
    return f"{session_prefix(session_id)}exports/transcript.{fmt}"


def _put_json(key: str, payload: dict[str, Any]) -> None:
    client = get_s3_client()
    body = json.dumps(payload, default=str).encode("utf-8")
    try:
        client.put_object(
            Bucket=settings.b2_bucket_name,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
    except ClientError as e:
        raise RuntimeError(f"B2 put_json failed for '{key}': {e}") from e


def _get_json(key: str) -> dict[str, Any] | None:
    client = get_s3_client()
    try:
        resp = client.get_object(Bucket=settings.b2_bucket_name, Key=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404"):
            return None
        raise RuntimeError(f"B2 get_json failed for '{key}': {e}") from e
    return json.loads(resp["Body"].read().decode("utf-8"))


def put_manifest(manifest: SessionManifest) -> None:
    _put_json(manifest_key(manifest.session_id), manifest.model_dump(mode="json"))


def get_manifest(session_id: str) -> SessionManifest | None:
    raw = _get_json(manifest_key(session_id))
    if raw is None:
        return None
    return SessionManifest(**raw)


def put_transcript_redacted(session_id: str, payload: dict[str, Any]) -> None:
    _put_json(transcript_redacted_key(session_id), payload)


def put_transcript_original(session_id: str, payload: dict[str, Any]) -> None:
    _put_json(transcript_original_key(session_id), payload)


def get_transcript_redacted(session_id: str) -> dict[str, Any] | None:
    return _get_json(transcript_redacted_key(session_id))


def get_transcript_original(session_id: str) -> dict[str, Any] | None:
    return _get_json(transcript_original_key(session_id))


def put_redactions(session_id: str, payload: dict[str, Any]) -> None:
    _put_json(redactions_key(session_id), payload)


def get_redactions(session_id: str) -> dict[str, Any] | None:
    return _get_json(redactions_key(session_id))


def put_audio(session_id: str, extension: str, data: bytes) -> str:
    """Store opt-in raw audio and return the storage key."""
    client = get_s3_client()
    key = audio_key(session_id, extension)
    ext = extension.lstrip(".").lower()
    content_type = {
        "webm": "audio/webm",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "m4a": "audio/mp4",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
    }.get(ext, "application/octet-stream")
    try:
        client.put_object(
            Bucket=settings.b2_bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    except ClientError as e:
        raise RuntimeError(f"B2 audio put failed for '{key}': {e}") from e
    return key


def put_export(session_id: str, fmt: ExportFormat, body: str) -> str:
    """Write a redacted export and return the storage key."""
    client = get_s3_client()
    key = export_key(session_id, fmt)
    mime = {"txt": "text/plain", "srt": "application/x-subrip", "vtt": "text/vtt"}[fmt]
    try:
        client.put_object(
            Bucket=settings.b2_bucket_name,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType=mime,
        )
    except ClientError as e:
        raise RuntimeError(f"B2 export put failed for '{key}': {e}") from e
    return key


def list_sessions(max_keys: int = 1000) -> list[str]:
    """List all session ids present under the `sessions/` prefix."""
    client = get_s3_client()
    seen: set[str] = set()
    kwargs: dict = {
        "Bucket": settings.b2_bucket_name,
        "Prefix": SESSIONS_PREFIX + "/",
        "MaxKeys": max_keys,
    }
    try:
        while True:
            resp = client.list_objects_v2(**kwargs)
            for obj in resp.get("Contents", []):
                key = obj["Key"]
                parts = key.split("/")
                if len(parts) >= 5:  # sessions/YYYY/MM/<id>/...
                    seen.add(parts[3])
            if not resp.get("IsTruncated"):
                break
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]
    except ClientError as e:
        raise RuntimeError(f"B2 list_sessions failed: {e}") from e
    return sorted(seen, reverse=True)


def head_object(key: str) -> dict[str, Any] | None:
    client = get_s3_client()
    try:
        return client.head_object(Bucket=settings.b2_bucket_name, Key=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey"):
            return None
        raise RuntimeError(f"B2 head failed for '{key}': {e}") from e


def head_session_state_parallel(session_ids: list[str]) -> dict[str, dict[str, bool]]:
    """For each session id, report whether audio + original transcript exist.

    Returns `{session_id: {has_audio: bool, has_original_transcript: bool}}`.
    """

    def _check(sid: str) -> tuple[str, dict[str, bool]]:
        # Probe a small fixed set of candidate keys per session.
        audio_present = False
        for ext in AUDIO_EXTENSIONS:
            if head_object(audio_key(sid, ext)) is not None:
                audio_present = True
                break
        original_present = head_object(transcript_original_key(sid)) is not None
        return sid, {
            "has_audio": audio_present,
            "has_original_transcript": original_present,
        }

    out: dict[str, dict[str, bool]] = {}
    if not session_ids:
        return out
    with ThreadPoolExecutor(max_workers=8) as pool:
        for sid, state in pool.map(_check, session_ids):
            out[sid] = state
    return out


def delete_session(session_id: str) -> int:
    """Delete every object under a session's prefix. Returns count deleted."""
    client = get_s3_client()
    prefix = session_prefix(session_id)
    keys: list[dict[str, str]] = []
    kwargs: dict = {"Bucket": settings.b2_bucket_name, "Prefix": prefix}
    try:
        while True:
            resp = client.list_objects_v2(**kwargs)
            for obj in resp.get("Contents", []):
                keys.append({"Key": obj["Key"]})
            if not resp.get("IsTruncated"):
                break
            kwargs["ContinuationToken"] = resp["NextContinuationToken"]
        if not keys:
            return 0
        # delete_objects caps at 1000 keys per request.
        for i in range(0, len(keys), 1000):
            client.delete_objects(
                Bucket=settings.b2_bucket_name,
                Delete={"Objects": keys[i : i + 1000]},
            )
    except ClientError as e:
        raise RuntimeError(f"B2 delete_session failed for '{session_id}': {e}") from e
    return len(keys)


def get_glossary() -> dict[str, Any] | None:
    return _get_json(GLOSSARY_KEY)


def put_glossary(payload: dict[str, Any]) -> None:
    _put_json(GLOSSARY_KEY, payload)
