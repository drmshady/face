"""Contract tests for photo upload endpoint per contracts/api.md (T020)."""

import io

import pytest
from httpx import AsyncClient


def _make_jpeg(width: int = 100, height: int = 100) -> bytes:
    """Create a minimal valid JPEG image."""
    from PIL import Image

    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color="red")
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_large_file(size_mb: int = 11) -> bytes:
    """Create a file exceeding the 10 MB limit."""
    return b"\x00" * (size_mb * 1024 * 1024)


async def _create_session(client: AsyncClient) -> tuple[str, str]:
    """Helper to create a session and return (session_id, token)."""
    resp = await client.post("/api/v1/sessions")
    return resp.json()["session_id"], resp.cookies["session_token"]


@pytest.mark.asyncio
async def test_upload_photo_returns_201(client: AsyncClient):
    """POST /sessions/{id}/photos returns 201 with photo metadata."""
    session_id, token = await _create_session(client)
    jpeg_data = _make_jpeg(1920, 1080)

    response = await client.post(
        f"/api/v1/sessions/{session_id}/photos",
        files={"file": ("front.jpg", jpeg_data, "image/jpeg")},
        data={"photo_type": "frontal"},
        cookies={"session_token": token},
    )
    assert response.status_code == 201

    body = response.json()
    assert "photo_id" in body
    assert body["photo_type"] == "frontal"
    assert body["original_filename"] == "front.jpg"
    assert body["mime_type"] == "image/jpeg"
    assert body["width"] == 1920
    assert body["height"] == 1080
    assert "file_size_bytes" in body


@pytest.mark.asyncio
async def test_upload_invalid_file_type_returns_400(client: AsyncClient):
    """POST /sessions/{id}/photos returns 400 for PDF."""
    session_id, token = await _create_session(client)

    response = await client.post(
        f"/api/v1/sessions/{session_id}/photos",
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
        data={"photo_type": "frontal"},
        cookies={"session_token": token},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILE_TYPE"


@pytest.mark.asyncio
async def test_upload_oversized_file_returns_400(client: AsyncClient):
    """POST /sessions/{id}/photos returns 400 for file > 10 MB."""
    session_id, token = await _create_session(client)
    big = _make_large_file(11)

    response = await client.post(
        f"/api/v1/sessions/{session_id}/photos",
        files={"file": ("big.jpg", big, "image/jpeg")},
        data={"photo_type": "frontal"},
        cookies={"session_token": token},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_upload_photo_unknown_session_returns_404(client: AsyncClient):
    """POST /sessions/{id}/photos returns 404 for unknown session."""
    _, token = await _create_session(client)

    response = await client.post(
        "/api/v1/sessions/nonexistent/photos",
        files={"file": ("f.jpg", _make_jpeg(), "image/jpeg")},
        data={"photo_type": "frontal"},
        cookies={"session_token": token},
    )
    assert response.status_code == 404
