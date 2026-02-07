"""Contract tests for annotated photo endpoint per contracts/api.md (T023)."""

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
    """Create session with completed analysis."""
    resp = await client.post("/api/v1/sessions")
    session_id = resp.json()["session_id"]
    token = resp.cookies["session_token"]

    r = await client.post(
        f"/api/v1/sessions/{session_id}/photos",
        files={"file": ("front.jpg", _make_jpeg(), "image/jpeg")},
        data={"photo_type": "frontal"},
        cookies={"session_token": token},
    )
    photo_id = r.json()["photo_id"]

    await client.post(
        f"/api/v1/sessions/{session_id}/photos",
        files={"file": ("side.jpg", _make_jpeg(), "image/jpeg")},
        data={"photo_type": "side"},
        cookies={"session_token": token},
    )

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
async def test_annotated_photo_returns_png(client: AsyncClient):
    """GET /sessions/{id}/photos/{pid}/annotated returns image/png."""
    session_id, token, photo_id = await _create_analyzed_session(client)

    response = await client.get(
        f"/api/v1/sessions/{session_id}/photos/{photo_id}/annotated",
        cookies={"session_token": token},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    # PNG files start with \x89PNG
    assert response.content[:4] == b"\x89PNG"
