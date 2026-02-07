"""Face analysis service: MediaPipe landmark detection + reference lines (T030)."""

import io
import logging

import numpy as np
from PIL import Image

from backend.src.models.landmarks import (
    FacialLandmarkSet,
    LandmarkPoint,
    LandmarkType,
    ReferenceLinesResult,
    compute_midline,
    compute_reference_line,
)

logger = logging.getLogger(__name__)

# MediaPipe index → LandmarkType mapping per research.md
_MEDIAPIPE_MAPPING: dict[int, LandmarkType] = {
    468: LandmarkType.left_pupil,
    473: LandmarkType.right_pupil,
    33: LandmarkType.right_outer_canthus,
    263: LandmarkType.left_outer_canthus,
    219: LandmarkType.right_ala,
    439: LandmarkType.left_ala,
    111: LandmarkType.right_orbitale,
    340: LandmarkType.left_orbitale,
}

# Lazy-initialized detector
_face_landmarker = None


def _get_landmarker():
    """Lazy-initialize MediaPipe FaceLandmarker."""
    global _face_landmarker
    if _face_landmarker is not None:
        return _face_landmarker

    try:
        import mediapipe as mp

        BaseOptions = mp.tasks.BaseOptions
        FaceLandmarker = mp.tasks.vision.FaceLandmarker
        FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode

        # Download model if not present
        import urllib.request
        import os
        import tempfile

        model_path = os.path.join(
            tempfile.gettempdir(), "face_landmarker_v2_with_blendshapes.task"
        )
        if not os.path.exists(model_path):
            logger.info("Downloading MediaPipe face landmarker model...")
            urllib.request.urlretrieve(
                "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
                model_path,
            )

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=VisionRunningMode.IMAGE,
            num_faces=1,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        _face_landmarker = FaceLandmarker.create_from_options(options)
        return _face_landmarker
    except Exception as e:
        logger.warning(f"Failed to initialize MediaPipe: {e}")
        return None


def detect_landmarks(image_bytes: bytes, photo_id: str = "") -> FacialLandmarkSet:
    """Detect facial landmarks using MediaPipe. Returns FacialLandmarkSet."""
    landmarks_dict: dict[LandmarkType, LandmarkPoint] = {}

    try:
        import mediapipe as mp

        landmarker = _get_landmarker()
        if landmarker is None:
            return FacialLandmarkSet(
                photo_id=photo_id,
                landmarks={},
                overall_confidence=0.0,
            )

        # Convert image bytes to MediaPipe Image
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_array = np.array(img)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_array)

        result = landmarker.detect(mp_image)

        if not result.face_landmarks:
            return FacialLandmarkSet(
                photo_id=photo_id,
                landmarks={},
                overall_confidence=0.0,
            )

        face = result.face_landmarks[0]
        h, w = img_array.shape[:2]

        for mp_idx, lm_type in _MEDIAPIPE_MAPPING.items():
            if mp_idx < len(face):
                lm = face[mp_idx]
                landmarks_dict[lm_type] = LandmarkPoint(
                    x=lm.x * w,
                    y=lm.y * h,
                    z=lm.z if hasattr(lm, "z") else None,
                    confidence=lm.visibility if hasattr(lm, "visibility") and lm.visibility else 0.8,
                    is_manual=False,
                    mediapipe_index=mp_idx,
                )

    except Exception as e:
        logger.warning(f"Landmark detection failed: {e}")

    # Compute overall confidence
    if landmarks_dict:
        overall = sum(lm.confidence for lm in landmarks_dict.values()) / len(
            landmarks_dict
        )
    else:
        overall = 0.0

    return FacialLandmarkSet(
        photo_id=photo_id,
        landmarks=landmarks_dict,
        overall_confidence=overall,
    )


def compute_all_reference_lines(
    all_landmarks: dict[str, FacialLandmarkSet],
) -> ReferenceLinesResult:
    """Compute all reference lines from landmarks across all photos."""
    # Merge landmarks from all photos (frontal + side)
    merged: dict[LandmarkType, LandmarkPoint] = {}
    for lm_set in all_landmarks.values():
        for lm_type, lm_point in lm_set.landmarks.items():
            # Keep the one with higher confidence
            existing = merged.get(lm_type)
            if existing is None or lm_point.confidence > existing.confidence:
                merged[lm_type] = lm_point

    return ReferenceLinesResult(
        interpupillary=compute_reference_line(
            LandmarkType.left_pupil,
            LandmarkType.right_pupil,
            merged,
        ),
        midline=compute_midline(merged),
        frankfort_plane=compute_reference_line(
            LandmarkType.left_porion,
            LandmarkType.left_orbitale,
            merged,
            warnings=["Soft-tissue approximation for orbitale"],
        ),
        ala_tragus=compute_reference_line(
            LandmarkType.left_ala,
            LandmarkType.left_tragus,
            merged,
        ),
        canthus_tragus=compute_reference_line(
            LandmarkType.left_outer_canthus,
            LandmarkType.left_tragus,
            merged,
        ),
    )
