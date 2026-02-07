"""Intra-oral scan model per data-model.md (T050)."""

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from backend.src.models import BoundingBox3D


class IntraOralScan(BaseModel):
    scan_id: str = Field(default_factory=lambda: str(uuid4()))
    original_filename: str
    file_size_bytes: int = Field(le=104_857_600)
    format: str = "stl"
    vertex_count: int = Field(gt=0)
    face_count: int = Field(gt=0)
    bounding_box: BoundingBox3D
    mesh_data: Any = Field(default=None, exclude=True)
