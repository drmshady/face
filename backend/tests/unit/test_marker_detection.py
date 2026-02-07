"""Unit tests for marker_detection service (T026)."""

import io

import pytest
from PIL import Image


def _make_jpeg(w: int = 640, h: int = 480) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color="white").save(buf, format="JPEG")
    return buf.getvalue()


class TestAprilTagDetection:
    def test_detect_returns_marker_list(self):
        """AprilTag detection should return a list of markers (possibly empty)."""
        from backend.src.services.marker_detection import detect_apriltag_markers

        result = detect_apriltag_markers(_make_jpeg())
        assert result is not None
        assert hasattr(result, "markers")
        assert isinstance(result.markers, list)

    def test_detect_no_markers_on_blank_image(self):
        """Blank image should return empty marker list."""
        from backend.src.services.marker_detection import detect_apriltag_markers

        result = detect_apriltag_markers(_make_jpeg())
        assert len(result.markers) == 0
        assert result.both_detected is False

    def test_detected_marker_has_required_fields(self):
        """If a marker is detected, it should have all required fields."""
        from backend.src.models.markers import ExternalMarker
        from backend.src.models import Point2D

        # Verify the model structure
        marker = ExternalMarker(
            marker_id=0,
            center=Point2D(x=100.0, y=100.0),
            corners=[
                Point2D(x=80, y=80),
                Point2D(x=120, y=80),
                Point2D(x=120, y=120),
                Point2D(x=80, y=120),
            ],
            confidence=0.99,
            size_pixels=40.0,
        )
        assert marker.marker_id == 0
        assert marker.confidence == 0.99
        assert len(marker.corners) == 4
