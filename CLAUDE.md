# FaceAnalyzer Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-02-08

## Active Technologies
- Python 3.12 (backend), TypeScript 5.x (frontend) + FastAPI, OpenCV (cv2.triangulatePoints, cv2.solvePnP), SciPy (scipy.optimize.least_squares), NumPy, trimesh, Three.js (@react-three/fiber) (002-3d-landmark-registration)
- Ephemeral in-memory session data + fork_geometry.json (persisted) (002-3d-landmark-registration)

- **Backend**: Python 3.12, FastAPI, MediaPipe, OpenCV, pupil-apriltags, trimesh, Open3D, NumPy, SciPy, Pillow
- **Frontend**: TypeScript 5.x, React 18, Vite, Three.js (@react-three/fiber), @mediapipe/tasks-vision, Axios
- **Testing**: pytest + httpx (backend), Vitest + React Testing Library (frontend)

## Project Structure

```text
backend/
├── src/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Environment configuration
│   ├── models/              # Pydantic data models (session, landmarks, markers, scan, alignment, fork, export)
│   ├── services/            # Business logic (face_analysis, marker_detection, stl_processing, fork_processing, alignment, export, image_utils)
│   └── api/                 # Routes, schemas, middleware
├── data/                    # Persistent config files (fork_geometry.json)
├── tests/                   # pytest (contract/, integration/, unit/)
├── requirements.txt
└── pyproject.toml

frontend/
├── src/
│   ├── components/          # React components (PhotoCapture, LandmarkOverlay, LandmarkEditor, StlViewer, ForkStlViewer, etc.)
│   ├── pages/               # Workflow steps (Capture, Analysis, Scan, Align, Export) + ForkCalibration
│   ├── services/            # API client, MediaPipe wrapper
│   ├── hooks/               # Custom hooks (useSession)
│   └── types/               # TypeScript type definitions
├── tests/                   # Vitest component tests
├── package.json
└── vite.config.ts
```

## Commands

```bash
# Backend
pip install -r backend/requirements.txt
uvicorn backend.src.main:app --reload --port 8000
pytest backend/tests/ -v

# Frontend
cd frontend && npm install
npm run dev
npm test
```

## Code Style

### Python (Backend)
- Pydantic models for all data structures
- Type hints on all function signatures
- FastAPI dependency injection for services
- Async endpoints for file uploads and processing
- No persistent storage for session data — all ephemeral in memory
- Fork geometry config persisted to `backend/data/fork_geometry.json`

### TypeScript (Frontend)
- Functional components with hooks
- Strict TypeScript (no `any` except trimesh mesh objects)
- @react-three/fiber for 3D rendering
- Axios for API communication

## Constitution Principles (MUST follow)

1. **Privacy-First**: No face data persisted beyond session; ephemeral processing; strip EXIF
2. **User Consent**: Explicit action before analysis; confidence scores displayed; no auto-processing
3. **Web-First**: React SPA + FastAPI REST backend; HTTPS; async with progress
4. **Test-First**: Tests before implementation; contract tests for API; unit tests for image processing
5. **Simplicity**: Use established libraries (MediaPipe, OpenCV); YAGNI; minimal viable flow

## Recent Changes
- 002-3d-landmark-registration: Added Python 3.12 (backend), TypeScript 5.x (frontend) + FastAPI, OpenCV (cv2.triangulatePoints, cv2.solvePnP), SciPy (scipy.optimize.least_squares), NumPy, trimesh, Three.js (@react-three/fiber)

### 001-face-scan-alignment (active)
- Face photo analysis with dental landmark detection
- Manual landmark placement for undetected points (tragus, porion)

### API Endpoints

Session-scoped (require session cookie):

Session-independent (no cookie required):

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
