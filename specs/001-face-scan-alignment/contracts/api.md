# API Contracts: Face-to-Scan Dental Alignment

**Feature Branch**: `001-face-scan-alignment`
**Date**: 2026-02-06
**Base URL**: `/api/v1`
**Protocol**: REST over HTTPS
**Content Types**: `application/json` (responses), `multipart/form-data` (uploads)

---

## Session Management

### POST /sessions

Create a new analysis session.

**Request**: Empty body (no input required)

**Response** `201 Created`:
```json
{
  "session_id": "uuid-string",
  "status": "created",
  "created_at": "2026-02-06T10:00:00Z"
}
```

### GET /sessions/{session_id}

Get current session state.

**Response** `200 OK`:
```json
{
  "session_id": "uuid-string",
  "status": "analysis_complete",
  "created_at": "2026-02-06T10:00:00Z",
  "photos": [
    {
      "photo_id": "uuid-string",
      "photo_type": "frontal",
      "original_filename": "front.jpg",
      "width": 1920,
      "height": 1080
    }
  ],
  "has_scan": false,
  "has_alignment": false,
  "has_export": false
}
```

**Errors**: `404` session not found

---

## Photo Upload & Analysis (User Story 1)

### POST /sessions/{session_id}/photos

Upload a face photo (frontal or side).

**Request** `multipart/form-data`:
| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `file` | file | Yes | JPEG/PNG/WebP, max 10 MB |
| `photo_type` | string | Yes | `"frontal"` or `"side"` |

**Response** `201 Created`:
```json
{
  "photo_id": "uuid-string",
  "photo_type": "frontal",
  "original_filename": "front.jpg",
  "mime_type": "image/jpeg",
  "width": 1920,
  "height": 1080,
  "file_size_bytes": 2456789
}
```

**Errors**:
- `400` invalid file type or exceeds size limit
- `404` session not found
- `422` missing required field

### POST /sessions/{session_id}/analyze

Trigger face analysis on all uploaded photos. Analysis runs
asynchronously; poll GET /analyze/status for progress and results.

**Request**: Empty body

**Preconditions**: Session must have at least 1 frontal + 1 side photo.

**Response** `202 Accepted`:
```json
{
  "session_id": "uuid-string",
  "status": "analyzing"
}
```

**Errors**:
- `400` insufficient photos (need frontal + side)
- `404` session not found
- `409` analysis already in progress

### GET /sessions/{session_id}/analyze/status

Poll analysis progress. Returns full results when complete.

**Response** `200 OK` (in progress):
```json
{
  "session_id": "uuid-string",
  "status": "analyzing",
  "progress_pct": 45,
  "current_step": "detecting_markers",
  "warnings": []
}
```

**Response** `200 OK` (complete):
```json
{
  "session_id": "uuid-string",
  "status": "analysis_complete",
  "progress_pct": 100,
  "current_step": "done",
  "results": {
    "photos": {
      "photo-uuid-1": {
        "photo_type": "frontal",
        "landmarks": {
          "left_pupil": {
            "x": 580.2,
            "y": 340.5,
            "z": null,
            "confidence": 0.97,
            "is_manual": false,
            "mediapipe_index": 468
          },
          "right_pupil": {
            "x": 820.1,
            "y": 342.0,
            "z": null,
            "confidence": 0.96,
            "is_manual": false,
            "mediapipe_index": 473
          }
        },
        "external_markers": {
          "both_detected": true,
          "markers": [
            {
              "marker_id": 0,
              "center": {"x": 650.0, "y": 580.0},
              "corners": [
                {"x": 630.0, "y": 560.0},
                {"x": 670.0, "y": 560.0},
                {"x": 670.0, "y": 600.0},
                {"x": 630.0, "y": 600.0}
              ],
              "confidence": 0.99
            }
          ]
        },
        "warnings": []
      }
    },
    "reference_lines": {
      "interpupillary": {
        "start_landmark": "left_pupil",
        "end_landmark": "right_pupil",
        "start_point": {"x": 580.2, "y": 340.5},
        "end_point": {"x": 820.1, "y": 342.0},
        "angle_degrees": 0.36,
        "confidence": 0.96,
        "warnings": []
      },
      "frankfort_plane": null,
      "ala_tragus": null,
      "canthus_tragus": null
    },
    "overall_confidence": 0.94,
    "warnings": [
      "Tragus landmarks require manual placement on side photos"
    ]
  }
}
```

**Errors**:
- `404` session not found

### PUT /sessions/{session_id}/photos/{photo_id}/landmarks

Manually adjust landmark positions for a photo.

**Request** `application/json`:
```json
{
  "landmarks": {
    "left_tragus": {
      "x": 120.5,
      "y": 380.2
    },
    "right_orbitale": {
      "x": 450.0,
      "y": 290.0
    }
  }
}
```

**Response** `200 OK`:
```json
{
  "photo_id": "uuid-string",
  "updated_landmarks": ["left_tragus", "right_orbitale"],
  "reference_lines": {
    "interpupillary": { "...": "recalculated" },
    "frankfort_plane": { "...": "recalculated" },
    "ala_tragus": { "...": "recalculated" },
    "canthus_tragus": { "...": "recalculated" }
  }
}
```

**Errors**:
- `400` invalid landmark type or coordinates
- `404` session or photo not found

### GET /sessions/{session_id}/photos/{photo_id}/annotated

Get the photo with detected landmarks and reference lines overlaid.

**Response** `200 OK`: Binary image (`image/png`)

**Errors**: `404` session or photo not found

---

## Scan Upload & Marker Detection (User Story 2)

### POST /sessions/{session_id}/scan

Upload an intra-oral STL scan file.

**Request** `multipart/form-data`:
| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `file` | file | Yes | STL format, max 100 MB |

**Response** `201 Created`:
```json
{
  "scan_id": "uuid-string",
  "original_filename": "scan.stl",
  "file_size_bytes": 15678901,
  "vertex_count": 456789,
  "face_count": 912345,
  "bounding_box": {
    "min": {"x": -40.2, "y": -15.3, "z": -8.1},
    "max": {"x": 42.5, "y": 18.7, "z": 12.4}
  },
  "intra_oral_markers": {
    "markers_found": 4,
    "sufficient": true,
    "markers": [
      {
        "marker_id": 1,
        "position": {"x": 10.2, "y": -5.3, "z": 2.1},
        "fitted_radius": 1.52,
        "confidence": 0.95,
        "residual": 0.08
      }
    ]
  }
}
```

**Errors**:
- `400` invalid file format or exceeds size limit
- `404` session not found
- `422` STL parsing failed

### POST /sessions/{session_id}/align

Compute alignment between face analysis and scan.

**Request**: Empty body

**Preconditions**: Session must have completed analysis (with both
external markers detected) and a scan (with >= 3 intra-oral markers).

**Response** `200 OK`:
```json
{
  "session_id": "uuid-string",
  "status": "alignment_complete",
  "alignment": {
    "t_face_to_scan": {
      "matrix": [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],
      "rotation_euler_deg": [0.5, -1.2, 0.3],
      "translation_mm": [2.1, -0.5, 15.3]
    },
    "reprojection_error_px": 1.2,
    "registration_rmsd_mm": 0.18,
    "quality": "good",
    "reference_planes_in_scan": {
      "interpupillary_plane": {
        "point": {"x": 0, "y": 0, "z": 50},
        "normal": {"x": 0, "y": 0.006, "z": 1}
      },
      "frankfort_plane": {
        "point": {"x": 0, "y": 10, "z": 30},
        "normal": {"x": 0, "y": 0.998, "z": 0.05}
      },
      "ala_tragus_plane": {
        "point": {"x": 0, "y": 5, "z": 25},
        "normal": {"x": 0, "y": 0.95, "z": 0.31}
      },
      "canthus_tragus_plane": {
        "point": {"x": 0, "y": 8, "z": 28},
        "normal": {"x": 0, "y": 0.97, "z": 0.24}
      }
    }
  }
}
```

**Errors**:
- `400` missing prerequisites (no markers or scan)
- `404` session not found
- `409` alignment already in progress

### POST /sessions/{session_id}/alignment/approve

Confirm alignment result. Enables export.

**Request**: Empty body

**Response** `200 OK`:
```json
{
  "session_id": "uuid-string",
  "status": "export_ready"
}
```

**Errors**:
- `400` no alignment to approve
- `404` session not found

---

## Export (User Story 3)

### POST /sessions/{session_id}/export

Generate the export package.

**Request** `application/json` (optional):
```json
{
  "include_aligned_stl": true,
  "include_metadata_json": true,
  "include_annotated_photo": true
}
```

All fields default to `true` if omitted.

**Preconditions**: Alignment must be approved.

**Response** `200 OK`:
```json
{
  "session_id": "uuid-string",
  "export_ready": true,
  "package_size_bytes": 18234567,
  "contents": [
    "aligned_scan.stl",
    "alignment_metadata.json",
    "annotated_face.png"
  ]
}
```

**Errors**:
- `400` alignment not approved
- `404` session not found

### GET /sessions/{session_id}/export/download

Download the export package as a ZIP file.

**Response** `200 OK`: Binary file (`application/zip`)
- Content-Disposition: `attachment; filename="face-scan-alignment-{session_id}.zip"`

**ZIP contents**:
- `aligned_scan.stl` — STL with reference planes applied
- `alignment_metadata.json` — Transformation matrices, landmarks,
  markers, confidence scores, reference plane definitions
- `annotated_face.png` — Face photo with analysis overlay

**Errors**:
- `400` export not generated yet
- `404` session not found

---

## Common Response Patterns

### Error Response Format

All errors return:
```json
{
  "error": {
    "code": "INVALID_FILE_TYPE",
    "message": "File must be JPEG, PNG, or WebP format",
    "details": {
      "received_type": "application/pdf",
      "allowed_types": ["image/jpeg", "image/png", "image/webp"]
    }
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|------------|-------------|
| `SESSION_NOT_FOUND` | 404 | Session ID does not exist |
| `PHOTO_NOT_FOUND` | 404 | Photo ID does not exist in session |
| `INVALID_FILE_TYPE` | 400 | Unsupported file format |
| `FILE_TOO_LARGE` | 400 | File exceeds size limit |
| `INSUFFICIENT_PHOTOS` | 400 | Need frontal + side photos |
| `MARKERS_NOT_DETECTED` | 400 | External markers not found |
| `SCAN_PARSE_ERROR` | 422 | STL file could not be parsed |
| `INSUFFICIENT_MARKERS` | 400 | < 3 intra-oral markers detected |
| `ALIGNMENT_NOT_READY` | 400 | Prerequisites for alignment not met |
| `EXPORT_NOT_READY` | 400 | Alignment not approved |
| `ANALYSIS_IN_PROGRESS` | 409 | Analysis already running |
| `RATE_LIMITED` | 429 | Too many requests |

### Rate Limits

- Photo upload: 20 requests/minute per session
- Analysis: 5 requests/minute per session
- Export: 10 requests/minute per session
