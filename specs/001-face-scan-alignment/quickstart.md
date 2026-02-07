# Quickstart: Face-to-Scan Dental Alignment

**Feature Branch**: `001-face-scan-alignment`
**Date**: 2026-02-06

## Prerequisites

- Python 3.12+
- Node.js 20+ and npm 10+
- Git

## Backend Setup

```bash
# Clone and enter the project
git clone <repo-url> face
cd face

# Create Python virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate
# Activate (macOS/Linux)
# source .venv/bin/activate

# Install backend dependencies
pip install -r backend/requirements.txt

# Run backend server
uvicorn backend.src.main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

## Frontend Setup

```bash
# In a separate terminal, from project root
cd frontend

# Install dependencies
npm install

# Run dev server (HTTPS enabled by default for camera access)
npm run dev
```

Frontend runs at `https://localhost:5173`. Accept the self-signed certificate warning in your browser.

## Run Tests

```bash
# Backend tests
pytest backend/tests/ -v

# Frontend tests
cd frontend && npm test
```

## Access from Phone (Camera Testing)

To test camera capture from a mobile device on the same Wi-Fi network:

```bash
# 1. Find your PC's local IP
ipconfig   # Windows — look for IPv4 Address (e.g., 192.168.1.105)

# 2. Start backend on all interfaces
uvicorn backend.src.main:app --reload --host 0.0.0.0 --port 8000

# 3. Start frontend on all interfaces (HTTPS already enabled via basicSsl plugin)
cd frontend && npm run dev -- --host 0.0.0.0
```

On your phone, open `https://192.168.1.105:5173` and accept the self-signed
certificate warning. Camera access (`getUserMedia`) requires HTTPS, which is
why the Vite dev server uses `@vitejs/plugin-basic-ssl` by default.

Update `backend/.env` to allow your LAN IP as a CORS origin:
```bash
CORS_ORIGINS=https://localhost:5173,https://192.168.1.105:5173
```

## Verify Installation

1. Open `https://localhost:5173` in a browser
2. The app should display the photo capture/upload step
3. Upload a face photo (JPEG/PNG/WebP, max 10 MB)
4. Verify the analysis runs and landmarks are displayed

## Key Dependencies

### Backend (Python)

| Package | Purpose |
|---------|---------|
| fastapi | REST API framework |
| uvicorn | ASGI server |
| mediapipe | Face landmark detection (478 landmarks) |
| opencv-python | ArUco marker detection, PnP solving, image processing |
| trimesh | STL file loading and mesh analysis |
| open3d | RANSAC sphere fitting, point cloud processing |
| numpy | Numerical computation |
| scipy | Spatial transforms, rotation utilities |
| scikit-learn | DBSCAN clustering for marker detection |
| Pillow | Image annotation and overlay generation |
| python-multipart | Multipart file upload support |
| pydantic | Data model validation |

### Frontend (TypeScript/React)

| Package | Purpose |
|---------|---------|
| react | UI framework |
| react-dom | React DOM rendering |
| @react-three/fiber | Three.js React bindings for 3D STL viewer |
| @react-three/drei | Three.js helpers (OrbitControls, loaders) |
| three | 3D rendering engine |
| @mediapipe/tasks-vision | Client-side face detection (optional) |
| axios | HTTP client for API calls |
| react-router-dom | Client-side routing between workflow steps |
| @vitejs/plugin-basic-ssl | Self-signed HTTPS for dev (camera access on LAN) |

## Environment Variables

```bash
# backend/.env
CORS_ORIGINS=https://localhost:5173
MAX_IMAGE_SIZE_MB=10
MAX_STL_SIZE_MB=100
RATE_LIMIT_PER_MINUTE=20
```

## Project Structure

```
face/
├── backend/
│   ├── src/
│   │   ├── main.py          # FastAPI app
│   │   ├── models/          # Pydantic data models
│   │   ├── services/        # Business logic
│   │   └── api/             # Routes, schemas, middleware
│   ├── tests/               # pytest tests
│   ├── requirements.txt
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/      # React components
│   │   ├── pages/           # Workflow step pages
│   │   ├── services/        # API client
│   │   └── types/           # TypeScript types
│   ├── tests/               # Vitest tests
│   ├── package.json
│   └── vite.config.ts
└── specs/                   # Feature specifications
```
