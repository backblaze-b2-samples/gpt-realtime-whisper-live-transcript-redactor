"""Unit tests for the session orchestration service."""

import re

import pytest

from app.service.sessions import (
    SessionError,
    generate_session_id,
    validate_session_id,
)
from app.types.sessions import SESSION_ID_REGEX


def test_session_id_matches_regex():
    sid = generate_session_id()
    assert re.fullmatch(SESSION_ID_REGEX, sid), f"bad id: {sid}"


def test_validate_accepts_well_formed():
    validate_session_id("20260528103045-abc12345")


def test_validate_rejects_garbage():
    for bad in ["", "abc", "20260528103045", "20260528103045-???"]:
        with pytest.raises(SessionError):
            validate_session_id(bad)
