"""Contract tests for POST /sessions/{id}/scan (T045)."""

import io

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from backend.src.main import app


async def _create_session_with_analysis(ac: AsyncClient) -> tuple[str, str]:
    """Create a session and run through analysis so we can upload a scan."""
    # Create session
    resp = await ac.post("/api/v1/sessions")
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]
    token = resp.cookies.get("session_token")

    # Upload frontal photo
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), color="white").save(buf, format="JPEG")
    buf.seek(0)
    await ac.post(
        f"/api/v1/sessions/{session_id}/photos",
        files={"file": ("front.jpg", buf, "image/jpeg")},
        data={"photo_type": "frontal"},
        cookies={"session_token": token},
    )

    # Upload side photo
    buf2 = io.BytesIO()
    Image.new("RGB", (640, 480), color="white").save(buf2, format="JPEG")
    buf2.seek(0)
    await ac.post(
        f"/api/v1/sessions/{session_id}/photos",
        files={"file": ("side.jpg", buf2, "image/jpeg")},
        data={"photo_type": "side"},
        cookies={"session_token": token},
    )

    # Trigger and wait for analysis
    await ac.post(
        f"/api/v1/sessions/{session_id}/analyze",
        cookies={"session_token": token},
    )
    # Poll until complete
    import asyncio
    for _ in range(30):
        status_resp = await ac.get(
            f"/api/v1/sessions/{session_id}/analyze/status",
            cookies={"session_token": token},
        )
        if status_resp.json().get("status") == "analysis_complete":
            break
        await asyncio.sleep(0.2)

    return session_id, token


def _make_minimal_stl() -> bytes:
    """Create a minimal valid binary STL file with 1 triangle."""
    import struct
    header = b"\x00" * 80
    num_triangles = struct.pack("<I", 1)
    # normal (0,0,1), 3 vertices, attribute byte count 0
    triangle = struct.pack("<fff", 0, 0, 1)  # normal
    triangle += struct.pack("<fff", 0, 0, 0)  # vertex 1
    triangle += struct.pack("<fff", 1, 0, 0)  # vertex 2
    triangle += struct.pack("<fff", 0, 1, 0)  # vertex 3
    triangle += struct.pack("<H", 0)  # attribute byte count
    return header + num_triangles + triangle


@pytest.mark.asyncio
async def test_upload_scan_returns_201():
    """Upload valid STL returns 201 with scan metadata."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        session_id, token = await _create_session_with_analysis(ac)

        stl_data = _make_minimal_stl()
        resp = await ac.post(
            f"/api/v1/sessions/{session_id}/scan",
            files={"file": ("scan.stl", io.BytesIO(stl_data), "application/octet-stream")},
            cookies={"session_token": token},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert "scan_id" in body
        assert body["vertex_count"] > 0
        assert body["face_count"] > 0
        assert "bounding_box" in body
        assert "intra_oral_markers" in body


@pytest.mark.asyncio
async def test_upload_non_stl_returns_400():
    """Upload non-STL file returns 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        session_id, token = await _create_session_with_analysis(ac)

        resp = await ac.post(
            f"/api/v1/sessions/{session_id}/scan",
            files={"file": ("scan.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
            cookies={"session_token": token},
        )

        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_FILE_TYPE"


@pytest.mark.asyncio
async def test_upload_oversized_stl_returns_400():
    """Upload STL > 100 MB returns 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        session_id, token = await _create_session_with_analysis(ac)

        # Create an oversized payload (just over 100 MB)
        big_data = b"\x00" * (100 * 1024 * 1024 + 1)
        resp = await ac.post(
            f"/api/v1/sessions/{session_id}/scan",
            files={"file": ("scan.stl", io.BytesIO(big_data), "application/octet-stream")},
            cookies={"session_token": token},
        )

        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_upload_corrupted_stl_returns_422():
    """Upload corrupted STL returns 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        session_id, token = await _create_session_with_analysis(ac)

        resp = await ac.post(
            f"/api/v1/sessions/{session_id}/scan",
            files={"file": ("scan.stl", io.BytesIO(b"not a real stl file"), "application/octet-stream")},
            cookies={"session_token": token},
        )

        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "SCAN_PARSE_ERROR"
