"""AprilTag marker detection service (T031)."""

import io
import logging
import math

import cv2
import numpy as np
from PIL import Image
from pupil_apriltags import Detector

from backend.src.models import Point2D
from backend.src.models.markers import ExternalMarker, ExternalMarkerSet

logger = logging.getLogger(__name__)

# AprilTag configuration: tag36h11 family (robust, widely used)
_DETECTOR = Detector(families="tag36h11", nthreads=1, quad_decimate=1.0)


def detect_apriltag_markers(
    image_bytes: bytes, photo_id: str = ""
) -> ExternalMarkerSet:
    """Detect AprilTag markers in an image. Returns ExternalMarkerSet."""
    try:
        # Convert to grayscale numpy array
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_array = np.array(img)
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        detections = _DETECTOR.detect(gray)

        markers: list[ExternalMarker] = []
        for det in detections:
            corners = det.corners  # shape (4, 2) — float64
            corner_points = [Point2D(x=float(p[0]), y=float(p[1])) for p in corners]

            center_x = float(det.center[0])
            center_y = float(det.center[1])

            # Compute marker size as average side length
            side_lengths = []
            for j in range(4):
                dx = corners[(j + 1) % 4][0] - corners[j][0]
                dy = corners[(j + 1) % 4][1] - corners[j][1]
                side_lengths.append(math.sqrt(dx * dx + dy * dy))
            size_px = sum(side_lengths) / 4.0

            # decision_margin is AprilTag's confidence-like metric (higher = better)
            confidence = min(float(det.decision_margin) / 100.0, 1.0)

            markers.append(
                ExternalMarker(
                    marker_id=int(det.tag_id),
                    center=Point2D(x=center_x, y=center_y),
                    corners=corner_points,
                    confidence=confidence,
                    size_pixels=size_px,
                )
            )

        return ExternalMarkerSet(
            photo_id=photo_id,
            markers=markers,
        )

    except Exception as e:
        logger.warning(f"Marker detection failed: {e}")
        return ExternalMarkerSet(photo_id=photo_id, markers=[])
