"""Unit tests for image_utils service (T024)."""

import io

import pytest
from PIL import Image


def _make_jpeg_with_exif(width: int = 100, height: int = 100) -> bytes:
    """Create a JPEG with EXIF data using Pillow's built-in support."""
    from PIL.ExifTags import Base as ExifBase

    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color="blue")
    exif = img.getexif()
    exif[ExifBase.Make] = "TestCamera"
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _make_jpeg(width: int = 100, height: int = 100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="red").save(buf, format="JPEG")
    return buf.getvalue()


def _make_png(width: int = 100, height: int = 100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="green").save(buf, format="PNG")
    return buf.getvalue()


class TestExifStripping:
    def test_strip_exif_removes_metadata(self):
        from backend.src.services.image_utils import strip_exif

        jpeg_with_exif = _make_jpeg_with_exif()
        stripped = strip_exif(jpeg_with_exif)

        # Verify EXIF is gone by re-opening
        img = Image.open(io.BytesIO(stripped))
        exif = img.getexif()
        assert len(exif) == 0

    def test_strip_exif_preserves_image_data(self):
        from backend.src.services.image_utils import strip_exif

        original = _make_jpeg(200, 150)
        stripped = strip_exif(original)

        img = Image.open(io.BytesIO(stripped))
        assert img.size == (200, 150)


class TestMimeValidation:
    def test_accept_jpeg(self):
        from backend.src.services.image_utils import validate_image

        assert validate_image("image/jpeg", 1000) is None

    def test_accept_png(self):
        from backend.src.services.image_utils import validate_image

        assert validate_image("image/png", 1000) is None

    def test_accept_webp(self):
        from backend.src.services.image_utils import validate_image

        assert validate_image("image/webp", 1000) is None

    def test_reject_pdf(self):
        from backend.src.services.image_utils import validate_image

        err = validate_image("application/pdf", 1000)
        assert err is not None
        assert "JPEG" in err or "format" in err.lower()

    def test_reject_oversized(self):
        from backend.src.services.image_utils import validate_image

        err = validate_image("image/jpeg", 11 * 1024 * 1024)
        assert err is not None
        assert "limit" in err.lower() or "exceeds" in err.lower()
