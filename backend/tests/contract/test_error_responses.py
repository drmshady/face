"""Contract tests for error response format per contracts/api.md."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_404_error_has_standard_format(client: AsyncClient):
    """All error responses must match {"error": {"code", "message", "details"}}."""
    # Create session to get a valid cookie
    create_resp = await client.post("/api/v1/sessions")
    token = create_resp.cookies["session_token"]

    response = await client.get(
        "/api/v1/sessions/nonexistent-id",
        cookies={"session_token": token},
    )
    assert response.status_code == 404

    body = response.json()
    assert "error" in body
    error = body["error"]
    assert "code" in error
    assert "message" in error
    assert "details" in error
    assert error["code"] == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_401_error_has_standard_format(client: AsyncClient):
    """401 responses also follow the standard error format."""
    response = await client.get("/api/v1/sessions/any-id")
    assert response.status_code == 401

    body = response.json()
    assert "error" in body
    error = body["error"]
    assert "code" in error
    assert "message" in error
    assert "details" in error
