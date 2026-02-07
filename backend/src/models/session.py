"""Session and photo models per data-model.md."""

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.src.models import DeviceInfo
from backend.src.models.alignment import AlignmentResult
from backend.src.models.landmarks import FacialLandmarkSet, ReferenceLinesResult
from backend.src.models.markers import ExternalMarkerSet, IntraOralMarkerSet
from backend.src.models.scan import IntraOralScan


class SessionStatus(str, Enum):
    created = "created"
    photos_uploaded = "photos_uploaded"
    analyzing = "analyzing"
    analysis_complete = "analysis_complete"
    scan_uploaded = "scan_uploaded"
    aligning = "aligning"
    alignment_complete = "alignment_complete"
    export_ready = "export_ready"


class PhotoType(str, Enum):
    frontal = "frontal"
    side = "side"


class UploadedPhoto(BaseModel):
    photo_id: str = Field(default_factory=lambda: str(uuid4()))
    photo_type: PhotoType
    original_filename: str
    mime_type: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    file_size_bytes: int = Field(le=10_485_760)
    exif_focal_length_mm: float | None = None
    image_data: bytes = Field(exclude=True)


class FaceAnalysisSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    status: SessionStatus = SessionStatus.created
    frontal_photo: UploadedPhoto | None = None
    side_photos: list[UploadedPhoto] = Field(default_factory=list)
    landmark_results: dict[str, FacialLandmarkSet] = Field(default_factory=dict)
    external_markers: dict[str, ExternalMarkerSet] = Field(default_factory=dict)
    reference_lines: ReferenceLinesResult | None = None
    device_info: DeviceInfo | None = None
    # Scan & alignment (US2)
    scan: IntraOralScan | None = None
    scan_stl_data: bytes | None = Field(default=None, exclude=True)
    intra_oral_markers: IntraOralMarkerSet | None = None
    alignment: AlignmentResult | None = None
    # Analysis progress tracking
    analysis_progress_pct: int = 0
    analysis_current_step: str = ""
    analysis_warnings: list[str] = Field(default_factory=list)
