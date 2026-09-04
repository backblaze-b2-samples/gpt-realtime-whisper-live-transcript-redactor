"""Integration tests for the health endpoint."""

import httpx
import pytest

from app.config import settings
from app.repo import openai_realtime_client, openai_redactor


class _Response:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("failed")

    def json(self):
        return {"choices": [{"message": {"content": '{"entities": []}'}}]}


class _OpenAIProbeClient:
    def __init__(
        self, seen: list[tuple[str, str]], status_code: int = 200
    ) -> None:
        self.seen = seen
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def head(self, url: str, **_kwargs):
        self.seen.append(("HEAD", url))
        return _Response(self.status_code)

    async def get(self, url: str, **_kwargs):
        self.seen.append(("GET", url))
        return _Response(self.status_code)

    async def post(self, url: str, **_kwargs):
        self.seen.append(("POST", url))
        return _Response(self.status_code)


@pytest.mark.asyncio
async def test_health_returns_200(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "b2_connected" in data
    assert "openai_reachable" in data
    assert "openai_realtime_reachable" in data
    assert "openai_redaction_reachable" in data
    assert data["status"] in ("healthy", "degraded")


@pytest.mark.asyncio
async def test_health_reports_distinct_openai_dependencies(client, monkeypatch):
    async def reachable():
        return True

    async def unreachable():
        return False

    monkeypatch.setattr("app.runtime.health.check_connectivity", lambda: True)
    monkeypatch.setattr("app.runtime.health.check_realtime_reachable", reachable)
    monkeypatch.setattr("app.runtime.health.check_redaction_reachable", unreachable)

    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["openai_reachable"] is False
    assert data["openai_realtime_reachable"] is True
    assert data["openai_redaction_reachable"] is False


@pytest.mark.asyncio
async def test_openai_calls_use_configured_base(monkeypatch):
    seen: list[tuple[str, str]] = []

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_api_base", "https://proxy.example/v1/")
    monkeypatch.setattr(settings, "redaction_pii_model", "redaction-model")
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout: _OpenAIProbeClient(seen))

    assert await openai_realtime_client.check_reachable()
    assert await openai_redactor.check_reachable()
    assert await openai_redactor.detect_pii_entities("plain transcript") == []
    assert seen == [
        ("HEAD", "https://proxy.example/v1/models"),
        ("GET", "https://proxy.example/v1/models/redaction-model"),
        ("POST", "https://proxy.example/v1/chat/completions"),
    ]


@pytest.mark.asyncio
async def test_realtime_reachability_requires_successful_status(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda timeout: _OpenAIProbeClient([], status_code=401),
    )

    assert not await openai_realtime_client.check_reachable()


@pytest.mark.asyncio
async def test_metrics_returns_200(client):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
    assert "uploads_total" in response.text
