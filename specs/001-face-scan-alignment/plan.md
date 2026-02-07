# Implementation Plan: Face-to-Scan Dental Alignment

**Branch**: `001-face-scan-alignment` | **Date**: 2026-02-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-face-scan-alignment/spec.md`

## Summary

A cross-platform web application that enables dental professionals to
capture/upload face photos (frontal + side), detect facial reference
lines (interpupillary, Frankfort plane, ala-tragus, canthus-tragus),
detect bite fork markers, align the facial analysis to an intra-oral
STL scan via a dual-marker chain (2 external + 4 intra-oral), and
export a neutral CAD-agnostic package (aligned STL + JSON metadata +
annotated photo). Uses MediaPipe for automated landmark detection with
guided manual placement for ear landmarks (tragus, porion), OpenCV for
ArUco marker detection and PnP solving, trimesh+Open3D for STL marker
detection via curvature-based RANSAC sphere fitting, and Three.js for
3D scan preview.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**:
- Backend: FastAPI, mediapipe, opencv-python (with ArUco), trimesh, open3d, numpy, scipy, scikit-learn, Pillow, python-multipart, uvicorn
- Frontend: React 18, TypeScript, Vite, Three.js (@react-three/fiber), @mediapipe/tasks-vision, Axios

**Storage**: Ephemeral only — in-memory session storage (no database). Files processed in memory and discarded after session. Optional session persistence via browser IndexedDB on frontend.
**Testing**: pytest + httpx (backend contract/integration), Vitest + React Testing Library (frontend)
**Target Platform**: Web — responsive SPA on Android Chrome, iOS Safari, Windows Chrome/Edge
**Project Type**: Web application (frontend + backend)
**Performance Goals**: Face analysis < 10 seconds (SC-007), full workflow < 5 minutes (SC-001), STL rendering at 30+ FPS
**Constraints**: Max 10 MB per image upload, STL up to 100 MB, 10 concurrent users (SC-008), no persistent storage by default (constitution Privacy-First)
**Scale/Scope**: Small clinic, 1-10 concurrent users, single-patient sessions

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Compliance | Notes |
|---|-----------|------------|-------|
| I | Privacy-First | PASS | Ephemeral in-memory processing; no disk/DB persistence; EXIF stripping on upload; session-scoped data only |
| II | User Consent & Transparency | PASS | Explicit "Analyze" button before processing; confidence scores on all landmarks (FR-012); no auto-processing on load |
| III | Web-First Architecture | PASS | React SPA frontend + FastAPI REST backend; HTTPS; async upload with progress feedback |
| IV | Test-First Development | PASS | pytest + Vitest planned; contract tests for API endpoints; unit tests for image processing with reference images |
| V | Simplicity | PASS | MediaPipe (established library) over custom ML; semi-automatic ear landmarks over custom model training; single core flow for MVP |

**Privacy & Security Requirements compliance:**
- Image size/type validation on client + server (FR-001) ✓
- File sanitization on upload ✓
- Rate limiting on analysis endpoints ✓
- CORS restricted to app domain ✓
- No third-party data sharing ✓
- Dependency audit before adoption ✓

**No violations — Complexity Tracking table not required.**

## Project Structure

### Documentation (this feature)

```text
specs/001-face-scan-alignment/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api.md           # REST API endpoint definitions
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── main.py                  # FastAPI app entry point, CORS, middleware
│   ├── config.py                # Environment configuration
│   ├── models/
│   │   ├── session.py           # FaceAnalysisSession model
│   │   ├── landmarks.py         # FacialLandmarkSet, landmark types
│   │   ├── markers.py           # ExternalMarkerSet, IntraOralMarkerSet
│   │   ├── scan.py              # IntraOralScan model
│   │   ├── alignment.py         # AlignmentResult, transformation matrices
│   │   └── export.py            # ExportFile model
│   ├── services/
│   │   ├── face_analysis.py     # MediaPipe landmark detection, line computation
│   │   ├── marker_detection.py  # ArUco detection in photos (OpenCV)
│   │   ├── stl_processing.py    # STL loading, intra-oral marker detection (trimesh+Open3D)
│   │   ├── alignment.py         # PnP solving, SVD registration, transform composition
│   │   ├── export.py            # Package generation (aligned STL + JSON + annotated photo)
│   │   └── image_utils.py       # EXIF stripping, validation, annotation overlay
│   └── api/
│       ├── routes.py            # API route definitions
│       ├── schemas.py           # Pydantic request/response schemas
│       └── middleware.py        # Rate limiting, file validation, error handling
├── tests/
│   ├── conftest.py              # Shared fixtures, test client
│   ├── contract/                # API schema validation tests
│   ├── integration/             # End-to-end workflow tests
│   └── unit/                    # Service-level unit tests
├── requirements.txt
└── pyproject.toml

frontend/
├── src/
│   ├── main.tsx                 # React entry point
│   ├── App.tsx                  # Main app shell, routing
│   ├── components/
│   │   ├── PhotoCapture.tsx     # Camera capture with guidance overlay
│   │   ├── PhotoUpload.tsx      # File upload with drag-and-drop
│   │   ├── LandmarkOverlay.tsx  # Detected landmarks + reference lines on photo
│   │   ├── LandmarkEditor.tsx   # Manual landmark adjustment (draggable points)
│   │   ├── StlViewer.tsx        # Three.js 3D scan viewer with marker/plane overlay
│   │   ├── AlignmentPreview.tsx # Alignment result visualization
│   │   ├── ExportPanel.tsx      # Export controls and download
│   │   └── ConfidenceBadge.tsx  # Confidence score display
│   ├── pages/
│   │   ├── CaptureStep.tsx      # Step 1: Photo capture/upload
│   │   ├── AnalysisStep.tsx     # Step 2: Face analysis + manual adjustment
│   │   ├── ScanStep.tsx         # Step 3: STL upload + marker detection
│   │   ├── AlignStep.tsx        # Step 4: Alignment preview
│   │   └── ExportStep.tsx       # Step 5: Export download
│   ├── services/
│   │   ├── api.ts               # Backend API client (Axios)
│   │   └── mediapipe.ts         # Client-side MediaPipe face detection (optional)
│   ├── hooks/
│   │   └── useSession.ts        # Session state management
│   └── types/
│       └── index.ts             # TypeScript type definitions
├── tests/
│   └── components/              # Component unit tests
├── index.html
├── vite.config.ts
├── tsconfig.json
└── package.json
```

**Structure Decision**: Web application layout (frontend + backend) per
constitution principle III (Web-First Architecture). Backend handles
all computation (face analysis, STL processing, alignment math, export
generation). Frontend handles UI, camera capture, photo display with
overlays, 3D STL viewer, and optionally client-side MediaPipe for
privacy-optimal landmark detection.

## Complexity Tracking

> No constitution violations — table not required.
