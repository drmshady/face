"""Marker models per data-model.md (T028, T051)."""

from pydantic import BaseModel, Field

from backend.src.models import Point2D, Point3D


class ExternalMarker(BaseModel):
    marker_id: int
    center: Point2D
    corners: list[Point2D] = Field(min_length=4, max_length=4)
    confidence: float = Field(ge=0.0, le=1.0)
    size_pixels: float = Field(gt=0)


class ExternalMarkerSet(BaseModel):
    photo_id: str
    markers: list[ExternalMarker] = Field(default_factory=list)
    detection_method: str = "apriltag"

    @property
    def both_detected(self) -> bool:
        return len(self.markers) >= 2


# ---------------------------------------------------------------------------
# Intra-oral markers (T051) — detected from STL scan
# ---------------------------------------------------------------------------


class IntraOralMarker(BaseModel):
    marker_id: int
    position: Point3D
    fitted_radius: float = Field(gt=0)
    confidence: float = Field(ge=0.0, le=1.0)
    residual: float = Field(ge=0)


class IntraOralMarkerSet(BaseModel):
    scan_id: str = ""
    markers: list[IntraOralMarker] = Field(default_factory=list)
    detection_method: str = "curvature_ransac"

    @property
    def markers_found(self) -> int:
        return len(self.markers)

    @property
    def sufficient(self) -> bool:
        return len(self.markers) >= 3
