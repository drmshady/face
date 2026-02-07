"""Fork geometry models for calibration (fork calibration page)."""

from pydantic import BaseModel

from backend.src.models import Point3D


class HexPostMarker(BaseModel):
    """A detected hexagonal post marker on the fork."""

    marker_id: int
    center: Point3D
    top_face_normal: Point3D
    radius_mm: float
    height_mm: float
    confidence: float


class AprilTagOnFork(BaseModel):
    """An AprilTag position on the fork, placed by user."""

    tag_id: int
    center_mm: Point3D
    size_mm: float = 7.0
    normal: Point3D
    corners_mm: list[list[float]]


class ForkGeometry(BaseModel):
    """Complete fork geometry configuration."""

    apriltags: list[AprilTagOnFork]
    intraoral_markers: list[HexPostMarker]
    plate_normal: list[float]
    created_at: str


class ForkCalibrationRequest(BaseModel):
    """Request body for saving fork configuration."""

    apriltags: list[dict]
    tag_size_mm: float = 7.0
