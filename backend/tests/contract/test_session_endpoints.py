"""Contract tests for session management endpoints per contracts/api.md."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_session_returns_201(client: AsyncClient):
    """POST /api/v1/sessions returns 201 with session_id, status, created_at."""
    response = await client.post("/api/v1/sessions")
    assert response.status_code == 201

    body = response.json()
    assert "session_id" in body
    assert body["status"] == "created"
    assert "created_at" in body


@pytest.mark.asyncio
async def test_create_session_sets_cookie(client: AsyncClient):
    """POST /api/v1/sessions sets an HTTP-only session cookie."""
    response = await client.post("/api/v1/sessions")
    assert response.status_code == 201

    cookies = response.cookies
    assert "session_token" in cookies


@pytest.mark.asyncio
async def test_get_session_returns_200(client: AsyncClient):
    """GET /api/v1/sessions/{session_id} returns session state."""
    create_resp = await client.post("/api/v1/sessions")
    session_id = create_resp.json()["session_id"]
    token = create_resp.cookies["session_token"]

    response = await client.get(
        f"/api/v1/sessions/{session_id}",
        cookies={"session_token": token},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] == "created"
    assert "created_at" in body
    assert body["photos"] == []
    assert body["has_scan"] is False
    assert body["has_alignment"] is False
    assert body["has_export"] is False


@pytest.mark.asyncio
async def test_get_session_404_unknown_id(client: AsyncClient):
    """GET /api/v1/sessions/{session_id} returns 404 for unknown ID."""
    # Need a valid session cookie first
    create_resp = await client.post("/api/v1/sessions")
    token = create_resp.cookies["session_token"]

    response = await client.get(
        "/api/v1/sessions/nonexistent-id",
        cookies={"session_token": token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_session_401_no_cookie(client: AsyncClient):
    """GET /api/v1/sessions/{id} returns 401 without session cookie."""
    response = await client.get("/api/v1/sessions/any-id")
    assert response.status_code == 401
