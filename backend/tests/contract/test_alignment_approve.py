"""Contract tests for POST /sessions/{id}/alignment/approve (T047)."""

import io
import struct

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from backend.src.main import app


def _make_minimal_stl() -> bytes:
    header = b"\x00" * 80
    num_triangles = struct.pack("<I", 1)
    triangle = struct.pack("<fff", 0, 0, 1)
    triangle += struct.pack("<fff", 0, 0, 0)
    triangle += struct.pack("<fff", 1, 0, 0)
    triangle += struct.pack("<fff", 0, 1, 0)
    triangle += struct.pack("<H", 0)
    return header + num_triangles + triangle


async def _create_aligned_session(ac: AsyncClient) -> tuple[str, str]:
    """Create a session with alignment complete."""
    import asyncio

    resp = await ac.post("/api/v1/sessions")
    session_id = resp.json()["session_id"]
    token = resp.cookies.get("session_token")

    for photo_type in ["frontal", "side"]:
        buf = io.BytesIO()
        Image.new("RGB", (640, 480), color="white").save(buf, format="JPEG")
        buf.seek(0)
        await ac.post(
            f"/api/v1/sessions/{session_id}/photos",
            files={"file": (f"{photo_type}.jpg", buf, "image/jpeg")},
            data={"photo_type": photo_type},
            cookies={"session_token": token},
        )

    await ac.post(f"/api/v1/sessions/{session_id}/analyze", cookies={"session_token": token})
    for _ in range(30):
        status_resp = await ac.get(
            f"/api/v1/sessions/{session_id}/analyze/status",
            cookies={"session_token": token},
        )
        if status_resp.json().get("status") == "analysis_complete":
            break
        await asyncio.sleep(0.2)

    stl_data = _make_minimal_stl()
    await ac.post(
        f"/api/v1/sessions/{session_id}/scan",
        files={"file": ("scan.stl", io.BytesIO(stl_data), "application/octet-stream")},
        cookies={"session_token": token},
    )

    await ac.post(f"/api/v1/sessions/{session_id}/align", cookies={"session_token": token})

    return session_id, token


@pytest.mark.asyncio
async def test_approve_alignment_returns_200():
    """Approving a computed alignment returns 200 with export_ready status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        session_id, token = await _create_aligned_session(ac)

        resp = await ac.post(
            f"/api/v1/sessions/{session_id}/alignment/approve",
            cookies={"session_token": token},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "export_ready"


@pytest.mark.asyncio
async def test_approve_without_alignment_returns_400():
    """Approving when no alignment exists returns 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/v1/sessions")
        session_id = resp.json()["session_id"]
        token = resp.cookies.get("session_token")

        resp = await ac.post(
            f"/api/v1/sessions/{session_id}/alignment/approve",
            cookies={"session_token": token},
        )

        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "ALIGNMENT_NOT_READY"
