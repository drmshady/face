"""Facial landmark and reference line models per data-model.md (T027)."""

import math
from enum import Enum

from pydantic import BaseModel, Field

from backend.src.models import Point2D


class LandmarkType(str, Enum):
    left_pupil = "left_pupil"
    right_pupil = "right_pupil"
    left_outer_canthus = "left_outer_canthus"
    right_outer_canthus = "right_outer_canthus"
    left_ala = "left_ala"
    right_ala = "right_ala"
    left_tragus = "left_tragus"
    right_tragus = "right_tragus"
    left_porion = "left_porion"
    right_porion = "right_porion"
    left_orbitale = "left_orbitale"
    right_orbitale = "right_orbitale"


class LandmarkPoint(BaseModel):
    x: float
    y: float
    z: float | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    is_manual: bool = False
    mediapipe_index: int | None = None


class FacialLandmarkSet(BaseModel):
    photo_id: str
    detection_method: str = "mediapipe"
    landmarks: dict[LandmarkType, LandmarkPoint]
    overall_confidence: float = Field(ge=0.0, le=1.0)


class ReferenceLine(BaseModel):
    start_landmark: LandmarkType
    end_landmark: LandmarkType
    start_point: Point2D
    end_point: Point2D
    angle_degrees: float
    confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)


class ReferenceLinesResult(BaseModel):
    interpupillary: ReferenceLine | None = None
    midline: ReferenceLine | None = None
    frankfort_plane: ReferenceLine | None = None
    ala_tragus: ReferenceLine | None = None
    canthus_tragus: ReferenceLine | None = None


def compute_midline(
    landmarks: dict[LandmarkType, LandmarkPoint],
    image_height: float = 4000,
) -> ReferenceLine | None:
    """Compute facial midline as the perpendicular bisector of the interpupillary line."""
    left = landmarks.get(LandmarkType.left_pupil)
    right = landmarks.get(LandmarkType.right_pupil)
    if left is None or right is None:
        return None

    mx = (left.x + right.x) / 2
    my = (left.y + right.y) / 2
    dx = right.x - left.x
    dy = right.y - left.y
    # Perpendicular direction (rotated 90 degrees)
    px, py = -dy, dx
    length = math.hypot(px, py)
    if length < 1e-6:
        px, py = 0.0, 1.0
    else:
        px, py = px / length, py / length

    # Extend the midline vertically across the image
    extent = image_height * 0.6
    confidence = min(left.confidence, right.confidence)

    return ReferenceLine(
        start_landmark=LandmarkType.left_pupil,
        end_landmark=LandmarkType.right_pupil,
        start_point=Point2D(x=mx - px * extent, y=my - py * extent),
        end_point=Point2D(x=mx + px * extent, y=my + py * extent),
        angle_degrees=math.degrees(math.atan2(py, px)),
        confidence=confidence,
        warnings=[],
    )


def compute_reference_line(
    start_type: LandmarkType,
    end_type: LandmarkType,
    landmarks: dict[LandmarkType, LandmarkPoint],
    warnings: list[str] | None = None,
) -> ReferenceLine | None:
    """Compute a reference line between two landmarks. Returns None if either is missing."""
    start = landmarks.get(start_type)
    end = landmarks.get(end_type)
    if start is None or end is None:
        return None

    dx = end.x - start.x
    dy = end.y - start.y
    angle = math.degrees(math.atan2(dy, dx))
    confidence = min(start.confidence, end.confidence)

    return ReferenceLine(
        start_landmark=start_type,
        end_landmark=end_type,
        start_point=Point2D(x=start.x, y=start.y),
        end_point=Point2D(x=end.x, y=end.y),
        angle_degrees=angle,
        confidence=confidence,
        warnings=warnings or [],
    )
