"""Contract tests for analyze endpoint per contracts/api.md (T021)."""

import io

import pytest
from httpx import AsyncClient


def _make_jpeg(width: int = 100, height: int = 100) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color="red")
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def _create_session_with_photos(client: AsyncClient) -> tuple[str, str]:
    """Create session and upload frontal + side photos."""
    resp = await client.post("/api/v1/sessions")
    session_id = resp.json()["session_id"]
    token = resp.cookies["session_token"]

    # Upload frontal
    await client.post(
        f"/api/v1/sessions/{session_id}/photos",
        files={"file": ("front.jpg", _make_jpeg(640, 480), "image/jpeg")},
        data={"photo_type": "frontal"},
        cookies={"session_token": token},
    )
    # Upload side
    await client.post(
        f"/api/v1/sessions/{session_id}/photos",
        files={"file": ("side.jpg", _make_jpeg(640, 480), "image/jpeg")},
        data={"photo_type": "side"},
        cookies={"session_token": token},
    )
    return session_id, token


@pytest.mark.asyncio
async def test_analyze_returns_202(client: AsyncClient):
    """POST /sessions/{id}/analyze returns 202 Accepted."""
    session_id, token = await _create_session_with_photos(client)

    response = await client.post(
        f"/api/v1/sessions/{session_id}/analyze",
        cookies={"session_token": token},
    )
    assert response.status_code == 202

    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] == "analyzing"


@pytest.mark.asyncio
async def test_analyze_insufficient_photos_returns_400(client: AsyncClient):
    """POST /sessions/{id}/analyze returns 400 when no photos uploaded."""
    resp = await client.post("/api/v1/sessions")
    session_id = resp.json()["session_id"]
    token = resp.cookies["session_token"]

    response = await client.post(
        f"/api/v1/sessions/{session_id}/analyze",
        cookies={"session_token": token},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INSUFFICIENT_PHOTOS"


@pytest.mark.asyncio
async def test_analyze_status_returns_200(client: AsyncClient):
    """GET /sessions/{id}/analyze/status returns progress info."""
    session_id, token = await _create_session_with_photos(client)

    # Trigger analysis
    await client.post(
        f"/api/v1/sessions/{session_id}/analyze",
        cookies={"session_token": token},
    )

    # Poll status — should return 200 with status fields
    import asyncio
    await asyncio.sleep(0.1)  # Give background task a moment

    response = await client.get(
        f"/api/v1/sessions/{session_id}/analyze/status",
        cookies={"session_token": token},
    )
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "progress_pct" in body
    assert "current_step" in body


@pytest.mark.asyncio
async def test_analyze_status_complete_has_results(client: AsyncClient):
    """GET /analyze/status returns full results when analysis_complete."""
    session_id, token = await _create_session_with_photos(client)

    # Trigger analysis
    await client.post(
        f"/api/v1/sessions/{session_id}/analyze",
        cookies={"session_token": token},
    )

    # Wait for analysis to complete
    import asyncio
    for _ in range(50):
        await asyncio.sleep(0.2)
        resp = await client.get(
            f"/api/v1/sessions/{session_id}/analyze/status",
            cookies={"session_token": token},
        )
        body = resp.json()
        if body.get("status") == "analysis_complete":
            break

    assert body["status"] == "analysis_complete"
    assert body["progress_pct"] == 100
    assert "results" in body
    results = body["results"]
    assert "photos" in results
    assert "reference_lines" in results
    assert "overall_confidence" in results
