"""Image utility service: validation, EXIF stripping, annotation overlay (T029)."""

import io
import math

from PIL import Image, ImageDraw, ImageFont

from backend.src.api.middleware import ALLOWED_IMAGE_TYPES
from backend.src.config import MAX_IMAGE_SIZE_BYTES
from backend.src.models import Point2D
from backend.src.models.landmarks import (
    FacialLandmarkSet,
    LandmarkType,
    ReferenceLinesResult,
)
from backend.src.models.markers import ExternalMarkerSet


def validate_image(content_type: str, size: int) -> str | None:
    """Returns error message if invalid, None if OK."""
    if content_type not in ALLOWED_IMAGE_TYPES:
        return f"File must be JPEG, PNG, or WebP format. Received: {content_type}"
    if size > MAX_IMAGE_SIZE_BYTES:
        return f"File exceeds {MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB limit"
    return None


def strip_exif(image_bytes: bytes) -> bytes:
    """Remove all EXIF metadata from image, preserving pixel data."""
    img = Image.open(io.BytesIO(image_bytes))
    clean = Image.new(img.mode, img.size)
    clean.putdata(list(img.getdata()))

    buf = io.BytesIO()
    fmt = img.format or "JPEG"
    clean.save(buf, format=fmt)
    return buf.getvalue()


def extract_focal_length(image_bytes: bytes) -> float | None:
    """Extract focal length from EXIF data before stripping."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        exif = img.getexif()
        # EXIF tag 37386 = FocalLength
        focal = exif.get(37386)
        if focal is not None:
            return float(focal)
    except Exception:
        pass
    return None


def get_image_dimensions(image_bytes: bytes) -> tuple[int, int]:
    """Return (width, height) of image."""
    img = Image.open(io.BytesIO(image_bytes))
    return img.size


# Landmark colors for annotation
_LANDMARK_COLORS = {
    LandmarkType.left_pupil: "#00ff00",
    LandmarkType.right_pupil: "#00ff00",
    LandmarkType.left_outer_canthus: "#00ccff",
    LandmarkType.right_outer_canthus: "#00ccff",
    LandmarkType.left_ala: "#ffcc00",
    LandmarkType.right_ala: "#ffcc00",
    LandmarkType.left_tragus: "#ff6600",
    LandmarkType.right_tragus: "#ff6600",
    LandmarkType.left_porion: "#ff00ff",
    LandmarkType.right_porion: "#ff00ff",
    LandmarkType.left_orbitale: "#cc00ff",
    LandmarkType.right_orbitale: "#cc00ff",
}

_LINE_COLORS = {
    "interpupillary": "#00ff00",
    "midline": "#ff3333",
    "frankfort_plane": "#ff00ff",
    "ala_tragus": "#ffcc00",
    "canthus_tragus": "#00ccff",
}


def draw_annotation_overlay(
    image_bytes: bytes,
    landmarks: FacialLandmarkSet | None = None,
    markers: ExternalMarkerSet | None = None,
    reference_lines: ReferenceLinesResult | None = None,
) -> bytes:
    """Draw landmarks, markers, and reference lines on a copy of the image. Returns PNG bytes."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Draw landmarks
    if landmarks:
        r = 5
        for lm_type, lm_point in landmarks.landmarks.items():
            color = _LANDMARK_COLORS.get(lm_type, "#ffffff")
            x, y = lm_point.x, lm_point.y
            draw.ellipse(
                [x - r, y - r, x + r, y + r],
                fill=color,
                outline="white",
            )
            draw.text(
                (x + r + 2, y - r),
                lm_type.value.replace("_", " "),
                fill="white",
            )

    # Draw external markers
    if markers:
        for marker in markers.markers:
            corners = [(c.x, c.y) for c in marker.corners]
            if len(corners) == 4:
                draw.polygon(corners, outline="#00ff00", width=2)
            cx, cy = marker.center.x, marker.center.y
            draw.ellipse(
                [cx - 3, cy - 3, cx + 3, cy + 3],
                fill="#00ff00",
            )
            draw.text(
                (cx + 5, cy - 10),
                f"M{marker.marker_id}",
                fill="#00ff00",
            )

    # Draw reference lines
    if reference_lines:
        for name in ("interpupillary", "midline", "frankfort_plane", "ala_tragus", "canthus_tragus"):
            line = getattr(reference_lines, name, None)
            if line is None:
                continue
            color = _LINE_COLORS.get(name, "#ffffff")
            # Extend line across the image width
            sp = line.start_point
            ep = line.end_point
            draw.line(
                [(sp.x, sp.y), (ep.x, ep.y)],
                fill=color,
                width=2,
            )
            # Label
            mx = (sp.x + ep.x) / 2
            my = (sp.y + ep.y) / 2
            label = name.replace("_", " ").title()
            draw.text(
                (mx, my - 15),
                f"{label} ({line.confidence:.0%})",
                fill=color,
            )

    result = Image.alpha_composite(img, overlay).convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()
