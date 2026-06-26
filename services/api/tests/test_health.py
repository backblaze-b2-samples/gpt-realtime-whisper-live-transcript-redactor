"""Integration tests for the health endpoint."""

import pytest


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
async def test_metrics_returns_200(client):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
    assert "uploads_total" in response.text
