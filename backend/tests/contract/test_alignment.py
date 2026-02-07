"""Contract tests for POST /sessions/{id}/align (T046)."""

import io
import struct

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from backend.src.main import app


def _make_minimal_stl() -> bytes:
    """Create a minimal valid binary STL file with 1 triangle."""
    header = b"\x00" * 80
    num_triangles = struct.pack("<I", 1)
    triangle = struct.pack("<fff", 0, 0, 1)
    triangle += struct.pack("<fff", 0, 0, 0)
    triangle += struct.pack("<fff", 1, 0, 0)
    triangle += struct.pack("<fff", 0, 1, 0)
    triangle += struct.pack("<H", 0)
    return header + num_triangles + triangle


async def _create_analyzed_session_with_scan(ac: AsyncClient) -> tuple[str, str]:
    """Create a session with analysis complete and scan uploaded."""
    import asyncio

    # Create session
    resp = await ac.post("/api/v1/sessions")
    session_id = resp.json()["session_id"]
    token = resp.cookies.get("session_token")

    # Upload frontal + side
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

    # Analyze
    await ac.post(f"/api/v1/sessions/{session_id}/analyze", cookies={"session_token": token})
    for _ in range(30):
        status_resp = await ac.get(
            f"/api/v1/sessions/{session_id}/analyze/status",
            cookies={"session_token": token},
        )
        if status_resp.json().get("status") == "analysis_complete":
            break
        await asyncio.sleep(0.2)

    # Upload scan
    stl_data = _make_minimal_stl()
    await ac.post(
        f"/api/v1/sessions/{session_id}/scan",
        files={"file": ("scan.stl", io.BytesIO(stl_data), "application/octet-stream")},
        cookies={"session_token": token},
    )

    return session_id, token


@pytest.mark.asyncio
async def test_align_returns_200():
    """Alignment with valid prerequisites returns 200 with alignment result."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        session_id, token = await _create_analyzed_session_with_scan(ac)

        resp = await ac.post(
            f"/api/v1/sessions/{session_id}/align",
            cookies={"session_token": token},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "alignment_complete"
        assert "alignment" in body
        alignment = body["alignment"]
        assert "t_face_to_scan" in alignment
        assert "reprojection_error_px" in alignment
        assert "registration_rmsd_mm" in alignment
        assert "quality" in alignment
        assert alignment["quality"] in ["good", "acceptable", "poor"]
        assert "reference_planes_in_scan" in alignment


@pytest.mark.asyncio
async def test_align_missing_prerequisites_returns_400():
    """Alignment without scan or analysis returns 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create a session without scan
        resp = await ac.post("/api/v1/sessions")
        session_id = resp.json()["session_id"]
        token = resp.cookies.get("session_token")

        resp = await ac.post(
            f"/api/v1/sessions/{session_id}/align",
            cookies={"session_token": token},
        )

        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "ALIGNMENT_NOT_READY"
