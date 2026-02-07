"""Alignment result models per data-model.md (T052)."""

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


class AlignmentResult(BaseModel):
    session_id: str
    t1_fork_to_camera: TransformMatrix
    t2_fork_to_scan: TransformMatrix
    t_face_to_scan: TransformMatrix
    reprojection_error_px: float = Field(ge=0)
    registration_rmsd_mm: float = Field(ge=0)
    quality: AlignmentQuality
    reference_planes_in_scan: ReferencePlanesInScan
    landmarks_3d_in_scan: list[Landmark3DInScan] = Field(default_factory=list)
