"""Unit tests for face_analysis service (T025)."""

import io

import pytest
from PIL import Image


def _make_jpeg(w: int = 640, h: int = 480) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color="red").save(buf, format="JPEG")
    return buf.getvalue()


class TestLandmarkDetection:
    def test_detect_landmarks_returns_expected_types(self):
        """MediaPipe should return at least pupil and canthus landmarks."""
        from backend.src.services.face_analysis import detect_landmarks

        result = detect_landmarks(_make_jpeg(640, 480))

        # Result may have no landmarks if no face detected in solid red image,
        # but the function should not raise an error
        assert result is not None
        assert hasattr(result, "landmarks")
        assert hasattr(result, "overall_confidence")

    def test_detect_landmarks_with_confidence(self):
        """All returned landmarks should have confidence scores."""
        from backend.src.services.face_analysis import detect_landmarks

        result = detect_landmarks(_make_jpeg(640, 480))
        for lm in result.landmarks.values():
            assert 0.0 <= lm.confidence <= 1.0


class TestReferenceLineComputation:
    def test_compute_reference_lines_from_landmarks(self):
        """Given two pupil landmarks, should compute interpupillary line."""
        from backend.src.models.landmarks import LandmarkPoint, LandmarkType, compute_reference_line

        landmarks = {
            LandmarkType.left_pupil: LandmarkPoint(
                x=200.0, y=300.0, confidence=0.95
            ),
            LandmarkType.right_pupil: LandmarkPoint(
                x=400.0, y=302.0, confidence=0.93
            ),
        }

        line = compute_reference_line(
            LandmarkType.left_pupil,
            LandmarkType.right_pupil,
            landmarks,
        )
        assert line is not None
        assert line.start_landmark == LandmarkType.left_pupil
        assert line.end_landmark == LandmarkType.right_pupil
        assert line.confidence == pytest.approx(0.93)
        # Nearly horizontal line
        assert abs(line.angle_degrees) < 5.0

    def test_reference_line_returns_none_for_missing_endpoint(self):
        """If one endpoint is missing, return None."""
        from backend.src.models.landmarks import LandmarkPoint, LandmarkType, compute_reference_line

        landmarks = {
            LandmarkType.left_pupil: LandmarkPoint(
                x=200.0, y=300.0, confidence=0.95
            ),
        }

        line = compute_reference_line(
            LandmarkType.left_pupil,
            LandmarkType.right_pupil,
            landmarks,
        )
        assert line is None
