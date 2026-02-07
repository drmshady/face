# Data Model: Face-to-Scan Dental Alignment

**Feature Branch**: `001-face-scan-alignment`
**Date**: 2026-02-06
**Input**: spec.md (Key Entities), plan.md (Technical Context)

## Overview

All entities are in-memory Pydantic models — no database persistence.
Data lives only for the duration of a session (constitution: Privacy-First).
Backend models are in `backend/src/models/`. Frontend mirrors these as
TypeScript types in `frontend/src/types/index.ts`.

---

## Entity: FaceAnalysisSession

**File**: `backend/src/models/session.py`
**Purpose**: Root entity representing one complete workflow from photo
upload through export.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `session_id` | `str (UUID4)` | Required, auto-generated | Unique session identifier |
| `created_at` | `datetime` | Required, auto-generated | Session creation timestamp (UTC) |
| `status` | `SessionStatus` | Required, enum | Current workflow state |
| `frontal_photo` | `UploadedPhoto \| None` | Required for analysis | Frontal face photo |
| `side_photos` | `list[UploadedPhoto]` | Min 1 for analysis | Side/profile photos |
| `landmark_results` | `dict[str, FacialLandmarkSet]` | Keyed by photo ID | Detection results per photo |
| `external_markers` | `dict[str, ExternalMarkerSet]` | Keyed by photo ID | Marker detection per photo |
| `reference_lines` | `ReferenceLinesResult \| None` | Computed after analysis | All four reference lines |
| `scan` | `IntraOralScan \| None` | Optional until step 3 | Uploaded STL scan |
| `intra_oral_markers` | `IntraOralMarkerSet \| None` | Detected from scan | Markers found in STL |
| `alignment` | `AlignmentResult \| None` | Computed after alignment | Alignment transformation |
| `device_info` | `DeviceInfo \| None` | Optional | Browser/device metadata |

**SessionStatus enum**: `created`, `photos_uploaded`, `analyzing`,
`analysis_complete`, `scan_uploaded`, `aligning`, `alignment_complete`,
`export_ready`

---

## Entity: UploadedPhoto

**File**: `backend/src/models/session.py`
**Purpose**: Metadata for an uploaded photo (image bytes held in memory).

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `photo_id` | `str (UUID4)` | Required, auto-generated | Unique photo identifier |
| `photo_type` | `PhotoType` | Required, enum | `frontal` or `side` |
| `original_filename` | `str` | Required | Original upload filename |
| `mime_type` | `str` | `image/jpeg`, `image/png`, `image/webp` | Validated MIME type |
| `width` | `int` | > 0 | Image width in pixels |
| `height` | `int` | > 0 | Image height in pixels |
| `file_size_bytes` | `int` | <= 10_485_760 (10 MB) | File size |
| `exif_focal_length_mm` | `float \| None` | Optional | Focal length from EXIF if available |
| `image_data` | `bytes` | Not serialized in API responses | Raw image bytes (EXIF-stripped) |

---

## Entity: FacialLandmarkSet

**File**: `backend/src/models/landmarks.py`
**Purpose**: Collection of detected facial landmarks for a single photo.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `photo_id` | `str` | Required | Photo this detection belongs to |
| `detection_method` | `str` | Default `"mediapipe"` | Detection algorithm used |
| `landmarks` | `dict[LandmarkType, LandmarkPoint]` | At least 1 entry | Detected landmarks by type |
| `overall_confidence` | `float` | 0.0-1.0 | Aggregate detection confidence |

**LandmarkType enum**: `left_pupil`, `right_pupil`, `left_outer_canthus`,
`right_outer_canthus`, `left_ala`, `right_ala`, `left_tragus`,
`right_tragus`, `left_porion`, `right_porion`, `left_orbitale`,
`right_orbitale`

**LandmarkPoint**:

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `x` | `float` | Required | X position in image pixels |
| `y` | `float` | Required | Y position in image pixels |
| `z` | `float \| None` | Optional | Depth estimate (from MediaPipe 3D) |
| `confidence` | `float` | 0.0-1.0 | Detection confidence for this landmark |
| `is_manual` | `bool` | Default `False` | True if manually placed/adjusted by user |
| `mediapipe_index` | `int \| None` | Optional | Source MediaPipe landmark index |

---

## Entity: ReferenceLinesResult

**File**: `backend/src/models/landmarks.py`
**Purpose**: Computed facial reference lines from detected landmarks.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `interpupillary` | `ReferenceLine \| None` | From frontal | Line connecting both pupil centers |
| `frankfort_plane` | `ReferenceLine \| None` | From side | Porion to orbitale (soft-tissue approx.) |
| `ala_tragus` | `ReferenceLine \| None` | From side | Ala of nose to tragus (Camper's plane) |
| `canthus_tragus` | `ReferenceLine \| None` | From side | Outer canthus to tragus |

**ReferenceLine**:

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `start_landmark` | `LandmarkType` | Required | Starting landmark type |
| `end_landmark` | `LandmarkType` | Required | Ending landmark type |
| `start_point` | `Point2D` | Required | Start position in image coords |
| `end_point` | `Point2D` | Required | End position in image coords |
| `angle_degrees` | `float` | Required | Line angle relative to horizontal |
| `confidence` | `float` | 0.0-1.0 | Min confidence of the two endpoints |
| `warnings` | `list[str]` | Optional | Warnings (e.g., "soft-tissue approximation") |

---

## Entity: ExternalMarkerSet

**File**: `backend/src/models/markers.py`
**Purpose**: The 2 fiducial markers on the bite fork visible in face photos.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `photo_id` | `str` | Required | Photo this detection belongs to |
| `markers` | `list[ExternalMarker]` | Exactly 2 for valid detection | Detected external markers |
| `detection_method` | `str` | Default `"aruco"` | Detection algorithm |
| `both_detected` | `bool` | Computed | True if both markers found |

**ExternalMarker**:

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `marker_id` | `int` | Required | ArUco marker ID or sequential index |
| `center` | `Point2D` | Required | Center position in image pixels |
| `corners` | `list[Point2D]` | 4 corners for ArUco | Corner positions (for PnP) |
| `confidence` | `float` | 0.0-1.0 | Detection confidence |
| `size_pixels` | `float` | > 0 | Detected marker size in pixels |

---

## Entity: IntraOralMarkerSet

**File**: `backend/src/models/markers.py`
**Purpose**: The 4 fiducial markers on the bite fork detected in the STL scan.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `scan_id` | `str` | Required | Scan this detection belongs to |
| `markers` | `list[IntraOralMarker]` | 3-4 for valid detection | Detected intra-oral markers |
| `detection_method` | `str` | Default `"curvature_ransac"` | Detection algorithm |
| `markers_found` | `int` | Computed | Number of markers detected |
| `sufficient` | `bool` | Computed | True if >= 3 markers |

**IntraOralMarker**:

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `marker_id` | `int` | Required | Sequential marker ID (1-4) |
| `position` | `Point3D` | Required | 3D position in scan coordinates (mm) |
| `fitted_radius` | `float` | > 0 | Sphere fit radius (mm) |
| `confidence` | `float` | 0.0-1.0 | Detection confidence |
| `residual` | `float` | >= 0 | Sphere fit residual (mm) |

---

## Entity: IntraOralScan

**File**: `backend/src/models/scan.py`
**Purpose**: Metadata for an uploaded 3D dental scan.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `scan_id` | `str (UUID4)` | Required, auto-generated | Unique scan identifier |
| `original_filename` | `str` | Required | Original upload filename |
| `file_size_bytes` | `int` | <= 104_857_600 (100 MB) | File size |
| `format` | `str` | `"stl"` | Scan format (STL only for MVP) |
| `vertex_count` | `int` | > 0 | Number of mesh vertices |
| `face_count` | `int` | > 0 | Number of mesh faces/triangles |
| `bounding_box` | `BoundingBox3D` | Required | Axis-aligned bounding box (mm) |
| `mesh_data` | `Any` | Not serialized | trimesh.Trimesh object in memory |

---

## Entity: AlignmentResult

**File**: `backend/src/models/alignment.py`
**Purpose**: Computed spatial transformation from face to scan coordinates.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `session_id` | `str` | Required | Parent session |
| `t1_fork_to_camera` | `TransformMatrix` | Required | Fork→camera transform from PnP |
| `t2_fork_to_scan` | `TransformMatrix` | Required | Fork→scan transform from registration |
| `t_face_to_scan` | `TransformMatrix` | Computed: T2 * T1⁻¹ | Full chain: face→scan transform |
| `reprojection_error_px` | `float` | >= 0 | PnP reprojection error (pixels) |
| `registration_rmsd_mm` | `float` | >= 0 | Fork-to-scan registration RMSD (mm) |
| `quality` | `AlignmentQuality` | Enum | `good`, `acceptable`, `poor` |
| `reference_planes_in_scan` | `ReferencePlanesInScan` | Required | Facial planes in scan coordinates |

**TransformMatrix**:

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `matrix` | `list[list[float]]` | 4x4 | Homogeneous transformation matrix |
| `rotation_euler_deg` | `list[float]` | 3 values (XYZ) | Rotation in Euler angles for display |
| `translation_mm` | `list[float]` | 3 values | Translation vector (mm) |

**AlignmentQuality thresholds**:
- `good`: reprojection < 2px AND RMSD < 0.3mm
- `acceptable`: reprojection < 5px AND RMSD < 0.5mm
- `poor`: above acceptable thresholds

**ReferencePlanesInScan**:

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `interpupillary_plane` | `Plane3D` | Optional | Interpupillary line as 3D plane in scan coords |
| `frankfort_plane` | `Plane3D` | Optional | Frankfort horizontal plane in scan coords |
| `ala_tragus_plane` | `Plane3D` | Optional | Ala-tragus (Camper's) plane in scan coords |
| `canthus_tragus_plane` | `Plane3D` | Optional | Canthus-tragus plane in scan coords |

---

## Entity: ExportFile

**File**: `backend/src/models/export.py`
**Purpose**: The downloadable export package.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `session_id` | `str` | Required | Parent session |
| `created_at` | `datetime` | Required | Export generation timestamp |
| `aligned_stl` | `bytes` | Required | STL with reference planes applied |
| `metadata_json` | `dict` | Required | JSON with transforms, landmarks, markers, confidence |
| `annotated_photo` | `bytes` | Required | Face photo with analysis overlay |
| `package_zip` | `bytes` | Computed | ZIP containing all three artifacts |
| `package_size_bytes` | `int` | Computed | Total package size |

---

## Shared Types

**File**: `backend/src/models/` (shared across entities)

| Type | Fields | Description |
|------|--------|-------------|
| `Point2D` | `x: float, y: float` | 2D image coordinate (pixels) |
| `Point3D` | `x: float, y: float, z: float` | 3D coordinate (mm) |
| `BoundingBox3D` | `min: Point3D, max: Point3D` | Axis-aligned bounding box |
| `Plane3D` | `point: Point3D, normal: Point3D` | 3D plane defined by point + normal |
| `DeviceInfo` | `user_agent: str, platform: str, screen_width: int, screen_height: int` | Browser/device info |

---

## Entity Relationships

```
FaceAnalysisSession (root)
├── UploadedPhoto (1 frontal + N side)
│   ├── FacialLandmarkSet (1 per photo)
│   └── ExternalMarkerSet (1 per photo)
├── ReferenceLinesResult (1, computed from landmarks)
├── IntraOralScan (0-1)
│   └── IntraOralMarkerSet (0-1, detected from scan)
├── AlignmentResult (0-1, computed from markers)
└── ExportFile (0-1, generated from alignment)
```

## Validation Rules

1. **Photo upload**: MIME type must be `image/jpeg`, `image/png`, or
   `image/webp`. Size <= 10 MB. At least 1 frontal + 1 side photo
   required before analysis.
2. **External markers**: Both markers (exactly 2) must be detected for
   alignment to proceed. Individual photos may have warnings if < 2
   detected.
3. **Intra-oral markers**: At least 3 of 4 markers must be detected in
   STL. If only 3 found, warn about reduced accuracy.
4. **STL upload**: Must be valid binary or ASCII STL. Size <= 100 MB.
   Must contain detectable geometry (vertex_count > 0).
5. **Alignment**: Cannot proceed until both external markers (from
   photos) and >= 3 intra-oral markers (from scan) are available.
6. **Export**: Cannot proceed until alignment is approved (status =
   `alignment_complete`).
