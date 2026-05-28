"""Tests for the per-session realtime state machine — especially the
`audio.received` audit-event cadence."""

from datetime import UTC, datetime

import pytest

from app.service.realtime_session import (
    AUDIO_RECEIVED_EVENT_INTERVAL_BYTES,
    RealtimeSessionState,
)
from app.types.sessions import AuditEvent, SessionManifest


def _make_manifest(sid: str = "20260528103045-abcdef12") -> SessionManifest:
    return SessionManifest(
        session_id=sid,
        created_at=datetime.now(UTC),
        storage_mode="originals_stored",
        store_original_audio=True,
        store_original_transcript=True,
        redaction_modes=["pii"],
        model="gpt-realtime-whisper",
        events=[
            AuditEvent(
                type="session.started",
                at=datetime.now(UTC),
                detail={"redaction_modes": ["pii"], "storage_mode": "originals_stored"},
            )
        ],
    )


@pytest.fixture
def state(monkeypatch) -> RealtimeSessionState:
    # Don't hit B2 — stub out get_session and finalize-time put_manifest.
    fake = _make_manifest()

    from app.service import realtime_session as mod

    monkeypatch.setattr(mod, "get_session", lambda _sid: fake)
    monkeypatch.setattr(mod.b2_sessions, "put_manifest", lambda _m: None)
    monkeypatch.setattr(
        mod.b2_sessions, "put_transcript_redacted", lambda _sid, _p: None
    )
    monkeypatch.setattr(
        mod.b2_sessions, "put_transcript_original", lambda _sid, _p: None
    )
    monkeypatch.setattr(mod.b2_sessions, "put_redactions", lambda _sid, _p: None)
    monkeypatch.setattr(
        mod.b2_sessions, "put_audio", lambda _sid, _ext, _data: "key"
    )
    return RealtimeSessionState(fake.session_id)


def _audio_received_events(state: RealtimeSessionState) -> list[AuditEvent]:
    return [e for e in state.manifest.events if e.type == "audio.received"]


def test_audio_received_event_emitted_when_interval_crossed(state):
    # One window's worth of audio in a single chunk -> exactly one event.
    chunk = b"\x00" * AUDIO_RECEIVED_EVENT_INTERVAL_BYTES
    state.append_audio_chunk(chunk)
    events = _audio_received_events(state)
    assert len(events) == 1
    detail = events[0].detail
    assert detail["bytes_received"] == AUDIO_RECEIVED_EVENT_INTERVAL_BYTES
    # 24kHz PCM16 mono: 240,000 bytes = 5,000 ms.
    assert detail["duration_ms_received"] == 5_000


def test_audio_received_event_throttled_below_threshold(state):
    state.append_audio_chunk(b"\x00" * 100)
    state.append_audio_chunk(b"\x00" * 100)
    # Below the interval — no audio.received event yet.
    assert _audio_received_events(state) == []
    # Aggregate counter still updated.
    assert state.manifest.audio_bytes_received == 200


def test_finalize_appends_tail_audio_received(state):
    # Sub-interval byte burst — without the finalize tail emission this
    # window would never appear in the audit log.
    state.append_audio_chunk(b"\x00" * 1234)
    assert _audio_received_events(state) == []
    state.finalize(audio_extension="webm")
    events = _audio_received_events(state)
    assert len(events) == 1
    assert events[0].detail["bytes_received"] == 1234


def test_finalize_does_not_double_emit_when_window_just_closed(state):
    # If the last chunk exactly crosses the threshold, finalize should
    # NOT emit a second zero-byte tail event.
    state.append_audio_chunk(b"\x00" * AUDIO_RECEIVED_EVENT_INTERVAL_BYTES)
    state.finalize(audio_extension="webm")
    events = _audio_received_events(state)
    assert len(events) == 1


def test_aggregate_counter_survives_for_rollup(state):
    chunks = 3
    chunk = b"\x00" * AUDIO_RECEIVED_EVENT_INTERVAL_BYTES
    for _ in range(chunks):
        state.append_audio_chunk(chunk)
    assert (
        state.manifest.audio_bytes_received
        == chunks * AUDIO_RECEIVED_EVENT_INTERVAL_BYTES
    )
    assert len(_audio_received_events(state)) == chunks
