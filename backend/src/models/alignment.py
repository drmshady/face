"""Alignment result models per data-model.md (T052, T002)."""

from enum import Enum

from pydantic import BaseModel, Field

from backend.src.models import Plane3D, Point3D


class AlignmentQuality(str, Enum):
    good = "good"
    acceptable = "acceptable"
    poor = "poor"


class TransformMatrix(BaseModel):
    matrix: list[list[float]] = Field(min_length=4, max_length=4)
    rotation_euler_deg: list[float] = Field(min_length=3, max_length=3)
    translation_mm: list[float] = Field(min_length=3, max_length=3)


class ReferencePlanesInScan(BaseModel):
    interpupillary_plane: Plane3D | None = None
    frankfort_plane: Plane3D | None = None
    ala_tragus_plane: Plane3D | None = None
    canthus_tragus_plane: Plane3D | None = None


class Landmark3DInScan(BaseModel):
    name: str
    point: Point3D
    confidence: float


# --- New models for 002-3d-landmark-registration ---


class Landmark3DInFork(BaseModel):
    """3D landmark positioned in fork coordinate space."""
    name: str
    point: Point3D
    confidence: float
    depth_method: str = "constant"
    depth_confidence: float = 0.0
    triangulation_residual_px: float | None = None


class CameraPose(BaseModel):
    """Per-photo camera pose from AprilTag PnP."""
    photo_id: str
    rvec: list[float] = Field(min_length=3, max_length=3)
    tvec: list[float] = Field(min_length=3, max_length=3)
    reprojection_error_px: float
    image_width: int
    image_height: int
    focal_length_mm: float | None = None


class ReferenceLine3D(BaseModel):
    """3D line segment (e.g., interpupillary line) in fork coordinates."""
    start_point: Point3D
    end_point: Point3D
    start_landmark: str
    end_landmark: str
    length_mm: float
    confidence: float
    depth_method: str


class ReferencePlane3D(BaseModel):
    """3D plane (e.g., midline) in fork coordinates."""
    point: Point3D
    normal: Point3D
    up_vector: Point3D
    confidence: float
    source_line: str


class AprilTagInFork(BaseModel):
    """AprilTag marker position in fork coordinates (from fork geometry calibration)."""
    tag_id: int
    center: Point3D
    corners: list[Point3D]
    normal: Point3D
    size_mm: float


class LandmarkToTagRelation(BaseModel):
    """Spatial relationship between a landmark and an AprilTag."""
    landmark_name: str
    tag_id: int
    distance_mm: float
    direction: Point3D
    angle_from_tag_normal_deg: float


class AlignmentResult(BaseModel):
    session_id: str
    t1_fork_to_camera: TransformMatrix
    t2_fork_to_scan: TransformMatrix | None = None
    t_face_to_scan: TransformMatrix | None = None
    reprojection_error_px: float = Field(ge=0)
    registration_rmsd_mm: float | None = None
    quality: AlignmentQuality
    reference_planes_in_scan: ReferencePlanesInScan | None = None
    landmarks_3d_in_scan: list[Landmark3DInScan] = Field(default_factory=list)
    # New fields for 002-3d-landmark-registration
    landmarks_3d_in_fork: list[Landmark3DInFork] = Field(default_factory=list)
    camera_poses: list[CameraPose] = Field(default_factory=list)
    interpupillary_line_3d: ReferenceLine3D | None = None
    midline_plane_3d: ReferencePlane3D | None = None
    apriltags_in_fork: list[AprilTagInFork] = Field(default_factory=list)
    landmark_to_tag_relations: list[LandmarkToTagRelation] = Field(default_factory=list)
    triangulation_method: str = "constant"
    scale_deviation_pct: float | None = None
    bundle_adjustment_residual: float | None = None
