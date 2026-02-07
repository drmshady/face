"""Contract tests for landmark update endpoint per contracts/api.md (T022)."""

import asyncio
import io

import pytest
from httpx import AsyncClient


def _make_jpeg(w: int = 640, h: int = 480) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), color="red").save(buf, format="JPEG")
    return buf.getvalue()


async def _create_analyzed_session(client: AsyncClient) -> tuple[str, str, str]:
    """Create session, upload photos, run analysis, return (session_id, token, photo_id)."""
    resp = await client.post("/api/v1/sessions")
    session_id = resp.json()["session_id"]
    token = resp.cookies["session_token"]

    # Upload frontal
    r = await client.post(
        f"/api/v1/sessions/{session_id}/photos",
        files={"file": ("front.jpg", _make_jpeg(), "image/jpeg")},
        data={"photo_type": "frontal"},
        cookies={"session_token": token},
    )
    photo_id = r.json()["photo_id"]

    # Upload side
    await client.post(
        f"/api/v1/sessions/{session_id}/photos",
        files={"file": ("side.jpg", _make_jpeg(), "image/jpeg")},
        data={"photo_type": "side"},
        cookies={"session_token": token},
    )

    # Trigger and wait for analysis
    await client.post(
        f"/api/v1/sessions/{session_id}/analyze",
        cookies={"session_token": token},
    )
    for _ in range(50):
        await asyncio.sleep(0.2)
        r2 = await client.get(
            f"/api/v1/sessions/{session_id}/analyze/status",
            cookies={"session_token": token},
        )
        if r2.json().get("status") == "analysis_complete":
            break

    return session_id, token, photo_id


@pytest.mark.asyncio
async def test_update_landmarks_returns_200(client: AsyncClient):
    """PUT /sessions/{id}/photos/{pid}/landmarks returns 200 with updated data."""
    session_id, token, photo_id = await _create_analyzed_session(client)

    response = await client.put(
        f"/api/v1/sessions/{session_id}/photos/{photo_id}/landmarks",
        json={
            "landmarks": {
                "left_tragus": {"x": 120.5, "y": 380.2},
            }
        },
        cookies={"session_token": token},
    )
    assert response.status_code == 200
    body = response.json()
    assert "updated_landmarks" in body
    assert "left_tragus" in body["updated_landmarks"]
    assert "reference_lines" in body


@pytest.mark.asyncio
async def test_update_landmarks_invalid_type_returns_400(client: AsyncClient):
    """PUT /sessions/{id}/photos/{pid}/landmarks returns 400 for invalid landmark type."""
    session_id, token, photo_id = await _create_analyzed_session(client)

    response = await client.put(
        f"/api/v1/sessions/{session_id}/photos/{photo_id}/landmarks",
        json={
            "landmarks": {
                "invalid_landmark": {"x": 100.0, "y": 200.0},
            }
        },
        cookies={"session_token": token},
    )
    assert response.status_code == 400
