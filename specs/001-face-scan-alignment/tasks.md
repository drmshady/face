# Tasks: Face-to-Scan Dental Alignment

**Input**: Design documents from `/specs/001-face-scan-alignment/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Included per constitution principle IV (Test-First Development). Tests MUST be written and verified to FAIL before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app**: `backend/src/`, `frontend/src/`
- **Backend tests**: `backend/tests/`
- **Frontend tests**: `frontend/tests/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure for both backend and frontend.

- [x] T001 Create project directory structure per plan.md: `backend/src/models/`, `backend/src/services/`, `backend/src/api/`, `backend/tests/contract/`, `backend/tests/integration/`, `backend/tests/unit/`, `frontend/src/components/`, `frontend/src/pages/`, `frontend/src/services/`, `frontend/src/hooks/`, `frontend/src/types/`, `frontend/tests/components/`
- [x] T002 [P] Initialize backend Python project with `backend/pyproject.toml` (Python 3.12, project metadata) and `backend/requirements.txt` (fastapi, uvicorn, mediapipe, opencv-python, trimesh, open3d, numpy, scipy, scikit-learn, Pillow, python-multipart, pydantic, httpx, pytest)
- [x] T003 [P] Initialize frontend React project with Vite: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html` (react, react-dom, @react-three/fiber, @react-three/drei, three, axios, react-router-dom, @mediapipe/tasks-vision, @vitejs/plugin-basic-ssl, vitest, @testing-library/react); configure vite.config.ts with basicSsl() plugin so `npm run dev` serves HTTPS (required for getUserMedia camera access from mobile devices on LAN)
- [x] T004 [P] Create backend environment configuration in `backend/src/config.py` (CORS_ORIGINS, MAX_IMAGE_SIZE_MB=10, MAX_STL_SIZE_MB=100, RATE_LIMIT_PER_MINUTE=20) loading from environment variables with defaults
- [x] T005 [P] Create shared Pydantic base types in `backend/src/models/__init__.py`: Point2D, Point3D, BoundingBox3D, Plane3D, DeviceInfo as defined in data-model.md Shared Types section

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented.

**CRITICAL**: No user story work can begin until this phase is complete.

### Tests for Foundation

- [x] T006 [P] Write contract test for POST /sessions and GET /sessions/{session_id} in `backend/tests/contract/test_session_endpoints.py`: verify 201 response with session_id/status/created_at fields, verify 404 for unknown session_id, verify response schema matches contracts/api.md
- [x] T007 [P] Write contract test for error response format in `backend/tests/contract/test_error_responses.py`: verify all error responses match the `{"error": {"code", "message", "details"}}` structure defined in contracts/api.md

### Implementation for Foundation

- [x] T008 Create FaceAnalysisSession and UploadedPhoto Pydantic models in `backend/src/models/session.py` with SessionStatus enum (created, photos_uploaded, analyzing, analysis_complete, scan_uploaded, aligning, alignment_complete, export_ready) and PhotoType enum (frontal, side) per data-model.md
- [x] T009 Create secure in-memory session store in `backend/src/services/session_store.py`: dict-based storage keyed by cryptographically random session token (secrets.token_urlsafe(32)), create_session() returns secure token, get_session(token) validates and retrieves, update_session() by token; sessions auto-expire after 1 hour; session token delivered via HTTP-only, Secure, SameSite=Strict cookie in API responses per constitution Privacy & Security Requirements
- [x] T009a Create session cookie middleware in `backend/src/api/middleware.py`: set HTTP-only, Secure, SameSite=Strict cookie on POST /sessions response, read session token from cookie on all subsequent requests, reject requests with missing or invalid session tokens with 401
- [x] T010 Create FastAPI app entry point in `backend/src/main.py`: FastAPI instance, CORS middleware (using config.py CORS_ORIGINS), include API router, lifespan event handler
- [x] T011 Create API error handling and response schemas in `backend/src/api/schemas.py`: ErrorResponse model with code/message/details fields, all error codes from contracts/api.md (SESSION_NOT_FOUND, INVALID_FILE_TYPE, FILE_TOO_LARGE, etc.)
- [x] T012 Create rate limiting and file validation middleware in `backend/src/api/middleware.py`: rate limiter per session (configurable via config.py), file type validation (JPEG/PNG/WebP for photos, STL for scans), file size validation
- [x] T013 Implement session management API routes in `backend/src/api/routes.py`: POST /api/v1/sessions (create session, return 201), GET /api/v1/sessions/{session_id} (return session state, 404 if not found) per contracts/api.md
- [x] T014 [P] Create frontend TypeScript type definitions in `frontend/src/types/index.ts` mirroring all backend models: Session, UploadedPhoto, LandmarkPoint, ReferenceLine, ExternalMarker, IntraOralMarker, AlignmentResult, ExportFile, ErrorResponse, all enums
- [x] T015 [P] Create frontend API client service in `frontend/src/services/api.ts` using Axios: createSession(), getSession(), uploadPhoto(), triggerAnalysis(), updateLandmarks(), getAnnotatedPhoto(), uploadScan(), triggerAlignment(), approveAlignment(), generateExport(), downloadExport() — all matching contracts/api.md endpoints
- [x] T016 Create frontend app shell in `frontend/src/App.tsx` with react-router-dom: 5 workflow step routes (/, /analysis, /scan, /align, /export), step progress indicator, session state context provider
- [x] T017 [P] Create useSession hook in `frontend/src/hooks/useSession.ts`: manages session lifecycle (create on first visit, poll status, store session_id), provides session state to all pages
- [x] T018 [P] Create React entry point in `frontend/src/main.tsx`: render App with BrowserRouter wrapper
- [x] T018a [P] Create ConsentDisclosure component in `frontend/src/components/ConsentDisclosure.tsx`: displays what analysis will be performed (facial landmark detection, marker detection), what data is collected (face photos, device info), how data is handled (ephemeral in-memory only, no persistence, no third-party sharing), requires explicit "I Understand & Consent" button click before enabling the Analyze action per constitution Principle II
- [x] T018b Update CaptureStep page in `frontend/src/pages/CaptureStep.tsx`: show ConsentDisclosure before the "Analyze" button is enabled; consent state stored in session context; "Analyze" button disabled until consent given
- [x] T019 Verify foundation by running `pytest backend/tests/contract/` — T006 and T007 tests should now PASS

**Checkpoint**: Foundation ready — session creation, error handling, API shell, frontend shell all functional. User story implementation can now begin.

---

## Phase 3: User Story 1 — Capture & Analyze Face Photo (Priority: P1) MVP

**Goal**: Dental professional uploads frontal + side photos, system detects facial landmarks (interpupillary, Frankfort, ala-tragus, canthus-tragus lines) and external AprilTag markers, displays results overlaid on photos with confidence scores. Manual landmark adjustment for ear landmarks.

**Independent Test**: Upload a frontal photo and side photo with AprilTag markers → verify all detectable landmarks, both markers, and reference lines are returned with confidence scores and displayed on annotated photos.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T020 [P] [US1] Write contract test for POST /sessions/{id}/photos in `backend/tests/contract/test_photo_upload.py`: verify 201 with photo metadata, verify 400 for invalid file type (PDF), verify 400 for file > 10 MB, verify 404 for unknown session
- [x] T021 [P] [US1] Write contract test for POST /sessions/{id}/analyze in `backend/tests/contract/test_analyze.py`: verify 202 Accepted with session_id and status="analyzing", verify 400 when photos insufficient; write contract test for GET /sessions/{id}/analyze/status: verify 200 with progress fields (status, progress_pct, current_step), verify full results returned when status=analysis_complete with landmarks/markers/reference_lines structure and confidence scores
- [x] T022 [P] [US1] Write contract test for PUT /sessions/{id}/photos/{id}/landmarks in `backend/tests/contract/test_landmarks_update.py`: verify 200 with updated landmarks and recalculated reference lines, verify 400 for invalid landmark type
- [x] T023 [P] [US1] Write contract test for GET /sessions/{id}/photos/{id}/annotated in `backend/tests/contract/test_annotated_photo.py`: verify 200 returns image/png content type
- [x] T024 [P] [US1] Write unit test for image_utils service in `backend/tests/unit/test_image_utils.py`: test EXIF stripping (verify EXIF removed from output), test MIME type validation (accept JPEG/PNG/WebP, reject others), test file size validation
- [x] T025 [P] [US1] Write unit test for face_analysis service in `backend/tests/unit/test_face_analysis.py`: test MediaPipe landmark extraction returns expected landmark types (left_pupil, right_pupil, left_outer_canthus, right_outer_canthus, left_ala, right_ala) with confidence scores, test reference line computation from landmark pairs
- [x] T026 [P] [US1] Write unit test for marker_detection service in `backend/tests/unit/test_marker_detection.py`: test AprilTag marker detection returns marker_id, center, corners, confidence; test detection on image with no markers returns empty result with warning

### Implementation for User Story 1

- [x] T027 [P] [US1] Create FacialLandmarkSet and ReferenceLinesResult Pydantic models in `backend/src/models/landmarks.py` with LandmarkType enum (left_pupil, right_pupil, left_outer_canthus, right_outer_canthus, left_ala, right_ala, left_tragus, right_tragus, left_porion, right_porion, left_orbitale, right_orbitale), LandmarkPoint model (x, y, z, confidence, is_manual, mediapipe_index), ReferenceLine model per data-model.md
- [x] T028 [P] [US1] Create ExternalMarkerSet and ExternalMarker Pydantic models in `backend/src/models/markers.py` with marker_id, center (Point2D), corners (list[Point2D]), confidence, size_pixels fields per data-model.md
- [x] T029 [US1] Implement image_utils service in `backend/src/services/image_utils.py`: validate_image() for MIME type and size checks, strip_exif() to remove EXIF metadata from uploaded images (preserving image data), extract_focal_length() to read focal length from EXIF before stripping, draw_annotation_overlay() to render landmarks/lines/markers on photo copy using Pillow
- [x] T030 [US1] Implement face_analysis service in `backend/src/services/face_analysis.py`: initialize MediaPipe FaceLandmarker, detect_landmarks(image_bytes) extracts landmarks from photo, maps MediaPipe indices to LandmarkType (468→left_pupil, 473→right_pupil, 33→right_outer_canthus, 263→left_outer_canthus, 219→right_ala, 439→left_ala, ~111→right_orbitale, ~340→left_orbitale), compute_reference_lines(landmarks_dict) computes interpupillary/frankfort/ala_tragus/canthus_tragus lines from landmark pairs, returns None for lines with missing endpoints (tragus requires manual placement)
- [x] T031 [US1] Implement marker_detection service in `backend/src/services/marker_detection.py`: initialize AprilTag detector (pupil-apriltags, tag36h11 family), detect_apriltag_markers(image_bytes) returns list of ExternalMarker with center/corners/confidence, handles orientation-invariant detection per spec edge case
- [x] T032 [US1] Implement photo upload API route in `backend/src/api/routes.py`: POST /api/v1/sessions/{session_id}/photos — validate file with image_utils, strip EXIF, store UploadedPhoto in session, return photo metadata per contracts/api.md
- [x] T033 [US1] Implement async analysis trigger API route in `backend/src/api/routes.py`: POST /api/v1/sessions/{session_id}/analyze — validate session has frontal + side photos, launch analysis as FastAPI BackgroundTask (face_analysis.detect_landmarks() + marker_detection.detect_apriltag_markers() + compute reference lines), update session status to "analyzing" immediately, return 202 Accepted with session_id and status per constitution Principle III (async processing with progress)
- [x] T033a [US1] Implement analysis status polling route in `backend/src/api/routes.py`: GET /api/v1/sessions/{session_id}/analyze/status — returns current analysis progress (status: analyzing/analysis_complete/analysis_failed, progress_pct: 0-100, current_step: "detecting_landmarks"/"detecting_markers"/"computing_lines", warnings so far), returns full results when status=analysis_complete
- [x] T033b [US1] Update CaptureStep and AnalysisStep pages to poll analysis status: after triggering analysis, show progress bar with current_step label, poll GET /analyze/status every 1 second, transition to AnalysisStep with full results when complete, show error with retry option if analysis_failed
- [x] T034 [US1] Implement landmark manual adjustment API route in `backend/src/api/routes.py`: PUT /api/v1/sessions/{session_id}/photos/{photo_id}/landmarks — update specified landmarks with is_manual=True, recompute all reference lines, return updated landmarks and reference lines per contracts/api.md
- [x] T035 [US1] Implement annotated photo API route in `backend/src/api/routes.py`: GET /api/v1/sessions/{session_id}/photos/{photo_id}/annotated — call image_utils.draw_annotation_overlay() with detected landmarks/markers/lines, return PNG image
- [x] T036 [US1] Add analysis response schemas to `backend/src/api/schemas.py`: AnalysisResponse, PhotoAnalysisResult, LandmarkResponse, ExternalMarkerResponse, ReferenceLineResponse matching contracts/api.md analyze endpoint response
- [x] T037 [P] [US1] Create PhotoUpload component in `frontend/src/components/PhotoUpload.tsx`: drag-and-drop file upload zone, file type validation (JPEG/PNG/WebP), file size validation (10 MB), photo_type selector (frontal/side), calls api.uploadPhoto(), displays upload progress
- [x] T038 [P] [US1] Create PhotoCapture component in `frontend/src/components/PhotoCapture.tsx`: device camera access via getUserMedia API, guidance overlay (face framing outline, ear visibility reminder, marker visibility check, lighting indicator per FR-017), capture button, outputs image blob for upload
- [x] T039 [P] [US1] Create ConfidenceBadge component in `frontend/src/components/ConfidenceBadge.tsx`: displays confidence score as colored badge (green >= 0.8, yellow >= 0.5, red < 0.5), shows percentage value
- [x] T040 [US1] Create LandmarkOverlay component in `frontend/src/components/LandmarkOverlay.tsx`: renders detected landmarks as colored circles on photo canvas, draws reference lines (interpupillary, Frankfort, ala-tragus, canthus-tragus) with labels and ConfidenceBadge, draws external marker positions with bounding boxes, highlights missing landmarks with warning icons
- [x] T041 [US1] Create LandmarkEditor component in `frontend/src/components/LandmarkEditor.tsx`: extends LandmarkOverlay with draggable landmark points, when user drags a landmark calls api.updateLandmarks() with new position, recalculates and redraws reference lines from response, zoomed ear area view with anatomical guidance for tragus placement per research.md semi-automatic approach
- [x] T042 [US1] Create CaptureStep page in `frontend/src/pages/CaptureStep.tsx`: workflow step 1, shows PhotoUpload and PhotoCapture options, manages list of uploaded photos (1 frontal required + 1+ side required), "Analyze" button triggers api.triggerAnalysis(), navigates to AnalysisStep on completion
- [x] T043 [US1] Create AnalysisStep page in `frontend/src/pages/AnalysisStep.tsx`: workflow step 2, displays each uploaded photo with LandmarkOverlay, shows reference lines panel with confidence scores, shows warnings for missing landmarks (especially tragus), enables LandmarkEditor for manual adjustment, "Continue to Scan" button navigates to ScanStep
- [x] T044 [US1] Verify US1 by running all US1 tests: `pytest backend/tests/contract/test_photo_upload.py backend/tests/contract/test_analyze.py backend/tests/contract/test_landmarks_update.py backend/tests/contract/test_annotated_photo.py backend/tests/unit/test_image_utils.py backend/tests/unit/test_face_analysis.py backend/tests/unit/test_marker_detection.py -v` — all should PASS

**Checkpoint**: User Story 1 fully functional. Upload photos → detect landmarks + markers → display overlaid results → manually adjust ear landmarks → all reference lines computed. Independently testable.

---

## Phase 4: User Story 2 — Align Face Analysis to Intra-Oral Scan (Priority: P2)

**Goal**: Dental professional uploads an STL scan, system detects 4 intra-oral markers via curvature+RANSAC, computes spatial alignment (PnP for T1, SVD registration for T2, compose T_face_to_scan = T2 * T1⁻¹), displays 3D alignment preview with facial reference planes overlaid on the scan.

**Independent Test**: Upload a pre-analyzed session + STL scan → verify 4 markers detected, alignment computed with quality metrics (reprojection error, RMSD), 3D preview shows scan with facial planes.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T045 [P] [US2] Write contract test for POST /sessions/{id}/scan in `backend/tests/contract/test_scan_upload.py`: verify 201 with scan metadata (vertex_count, face_count, bounding_box, intra_oral_markers), verify 400 for non-STL file, verify 400 for file > 100 MB, verify 422 for corrupted STL
- [x] T046 [P] [US2] Write contract test for POST /sessions/{id}/align in `backend/tests/contract/test_alignment.py`: verify 200 with alignment result (t_face_to_scan matrix, reprojection_error_px, registration_rmsd_mm, quality, reference_planes_in_scan), verify 400 when prerequisites missing
- [x] T047 [P] [US2] Write contract test for POST /sessions/{id}/alignment/approve in `backend/tests/contract/test_alignment_approve.py`: verify 200 with status=export_ready, verify 400 when no alignment exists
- [x] T048 [P] [US2] Write unit test for stl_processing service in `backend/tests/unit/test_stl_processing.py`: test STL loading returns vertex_count/face_count/bounding_box, test marker detection returns 3-4 IntraOralMarker objects with position/fitted_radius/confidence/residual fields
- [x] T049 [P] [US2] Write unit test for alignment service in `backend/tests/unit/test_alignment.py`: test PnP solving with known marker positions returns valid transformation matrix, test SVD registration with known 3D point pairs returns rotation+translation with RMSD < 0.1mm, test transform composition T2 * T1⁻¹ produces correct combined matrix, test quality classification (good/acceptable/poor thresholds)

### Implementation for User Story 2

- [x] T050 [P] [US2] Create IntraOralScan Pydantic model in `backend/src/models/scan.py` with scan_id, original_filename, file_size_bytes, format, vertex_count, face_count, bounding_box (BoundingBox3D) per data-model.md
- [x] T051 [P] [US2] Create IntraOralMarkerSet and IntraOralMarker Pydantic models in `backend/src/models/markers.py` (add to existing file): scan_id, markers list, detection_method, markers_found, sufficient flag; IntraOralMarker with marker_id, position (Point3D), fitted_radius, confidence, residual per data-model.md
- [x] T052 [P] [US2] Create AlignmentResult, TransformMatrix, ReferencePlanesInScan Pydantic models in `backend/src/models/alignment.py` with t1_fork_to_camera, t2_fork_to_scan, t_face_to_scan (TransformMatrix), reprojection_error_px, registration_rmsd_mm, quality (AlignmentQuality enum: good/acceptable/poor), reference_planes_in_scan per data-model.md
- [x] T053 [US2] Implement stl_processing service in `backend/src/services/stl_processing.py`: load_stl(file_bytes) using trimesh.load() to parse binary/ASCII STL and return Trimesh + metadata (vertex_count, face_count, bounding_box), detect_intra_oral_markers(mesh, expected_radius, expected_count=4) implementing curvature-based segmentation + RANSAC sphere fitting pipeline from research.md (compute Gaussian curvature → filter by 1/r² → DBSCAN cluster → sphere fit per cluster → validate radius → return IntraOralMarkerSet)
- [x] T054 [US2] Implement alignment service in `backend/src/services/alignment.py`: estimate_camera_intrinsics(image_width, image_height, focal_length_mm=None) approximates K matrix from image dimensions and EXIF focal length, solve_fork_pose_pnp(marker_2d_corners, marker_3d_positions, camera_matrix) uses cv2.solvePnP with AprilTag corners to compute T1 (fork→camera), solve_fork_to_scan_registration(fork_marker_positions_3d, scan_marker_positions_3d) implements SVD closed-form registration from research.md to compute T2 (fork→scan), compose_alignment(T1, T2) computes T_face_to_scan = T2 * T1⁻¹, compute_quality_metrics(T1, T2, observed_2d, observed_3d, camera_matrix) returns reprojection error and RMSD, classify_quality() applies thresholds from data-model.md, transform_reference_planes(reference_lines, T_face_to_scan) maps 2D reference lines into 3D scan coordinate system as Plane3D objects
- [x] T055 [US2] Implement scan upload API route in `backend/src/api/routes.py`: POST /api/v1/sessions/{session_id}/scan — validate STL file, call stl_processing.load_stl() and detect_intra_oral_markers(), store IntraOralScan and markers in session, return response per contracts/api.md
- [x] T056 [US2] Implement alignment trigger API route in `backend/src/api/routes.py`: POST /api/v1/sessions/{session_id}/align — validate prerequisites (analysis complete with both external markers, scan with >= 3 intra-oral markers), call alignment.solve_fork_pose_pnp() + solve_fork_to_scan_registration() + compose_alignment() + transform_reference_planes(), store AlignmentResult, return response per contracts/api.md
- [x] T057 [US2] Implement alignment approve API route in `backend/src/api/routes.py`: POST /api/v1/sessions/{session_id}/alignment/approve — verify alignment exists, update session status to export_ready, return response per contracts/api.md
- [x] T058 [US2] Add scan and alignment response schemas to `backend/src/api/schemas.py`: ScanUploadResponse, IntraOralMarkerResponse, AlignmentResponse, AlignmentApproveResponse matching contracts/api.md
- [x] T059 [P] [US2] Create StlViewer component in `frontend/src/components/StlViewer.tsx` using @react-three/fiber: load STL via STLLoader in Web Worker, render mesh with MeshStandardMaterial, add OrbitControls for rotation/zoom/pan, render detected intra-oral markers as colored SphereGeometry at 3D positions, accepts optional plane overlays (semi-transparent PlaneGeometry) for reference planes
- [x] T060 [P] [US2] Create AlignmentPreview component in `frontend/src/components/AlignmentPreview.tsx`: extends StlViewer to show facial reference planes overlaid on the scan, displays quality metrics (reprojection error, RMSD, quality badge), color-coded plane visualization (interpupillary=blue, Frankfort=green, ala-tragus=orange, canthus-tragus=purple), approve/reject buttons
- [x] T061 [US2] Create ScanStep page in `frontend/src/pages/ScanStep.tsx`: workflow step 3, STL file upload with drag-and-drop (max 100 MB with progress bar per edge case), displays StlViewer with detected markers after upload, shows marker count and confidence, "Compute Alignment" button triggers api.triggerAlignment(), navigates to AlignStep
- [x] T062 [US2] Create AlignStep page in `frontend/src/pages/AlignStep.tsx`: workflow step 4, displays AlignmentPreview with reference planes on scan, shows quality metrics panel, "Approve" button calls api.approveAlignment() and navigates to ExportStep, "Re-analyze" option to go back to AnalysisStep for landmark adjustment
- [x] T063 [US2] Verify US2 by running all US2 tests: `pytest backend/tests/contract/test_scan_upload.py backend/tests/contract/test_alignment.py backend/tests/contract/test_alignment_approve.py backend/tests/unit/test_stl_processing.py backend/tests/unit/test_alignment.py -v` — all should PASS

**Checkpoint**: User Stories 1 AND 2 both work independently. Full flow: photos → analysis → scan upload → marker detection → alignment → 3D preview → approve.

---

## Phase 5: User Story 3 — Export for Dental CAD Software (Priority: P3)

**Goal**: Dental professional exports a neutral CAD-agnostic package (ZIP containing aligned STL + JSON metadata + annotated face photo) that can be imported into exocad, 3Shape, or other dental CAD software.

**Independent Test**: Use a pre-computed alignment → generate export → verify ZIP contains aligned_scan.stl, alignment_metadata.json, annotated_face.png with correct content.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T064 [P] [US3] Write contract test for POST /sessions/{id}/export in `backend/tests/contract/test_export.py`: verify 200 with export_ready=true and package contents list, verify 400 when alignment not approved
- [ ] T065 [P] [US3] Write contract test for GET /sessions/{id}/export/download in `backend/tests/contract/test_export_download.py`: verify 200 returns application/zip content type with correct Content-Disposition header, verify ZIP contains aligned_scan.stl + alignment_metadata.json + annotated_face.png, verify 400 when export not generated
- [ ] T066 [P] [US3] Write unit test for export service in `backend/tests/unit/test_export.py`: test generate_aligned_stl() applies transformation matrix to mesh vertices, test generate_metadata_json() includes all required fields (transforms, landmarks, markers, confidence, planes), test generate_annotated_photo() produces PNG with overlay, test create_export_package() produces valid ZIP with 3 files

### Implementation for User Story 3

- [ ] T067 [US3] Create ExportFile Pydantic model in `backend/src/models/export.py` with session_id, created_at, aligned_stl (bytes), metadata_json (dict), annotated_photo (bytes), package_zip (bytes), package_size_bytes per data-model.md
- [ ] T068 [US3] Implement export service in `backend/src/services/export.py`: generate_aligned_stl(mesh, T_face_to_scan) applies transformation matrix to STL mesh vertices and returns transformed STL bytes, generate_metadata_json(session) compiles transformation matrices, landmark positions, marker positions, reference plane definitions, and confidence scores into JSON dict, generate_annotated_photo(session) calls image_utils.draw_annotation_overlay() on the best frontal photo and returns PNG bytes, create_export_package(aligned_stl, metadata_json, annotated_photo) creates ZIP archive in memory containing aligned_scan.stl + alignment_metadata.json + annotated_face.png
- [ ] T069 [US3] Implement export generation API route in `backend/src/api/routes.py`: POST /api/v1/sessions/{session_id}/export — verify alignment approved, call export service to generate package, store ExportFile in session, return response per contracts/api.md
- [ ] T070 [US3] Implement export download API route in `backend/src/api/routes.py`: GET /api/v1/sessions/{session_id}/export/download — verify export exists, return ZIP as StreamingResponse with Content-Disposition header per contracts/api.md
- [ ] T071 [US3] Add export response schemas to `backend/src/api/schemas.py`: ExportResponse, ExportDownloadResponse matching contracts/api.md
- [ ] T072 [P] [US3] Create ExportPanel component in `frontend/src/components/ExportPanel.tsx`: "Generate Export" button triggers api.generateExport(), displays package contents list and size after generation, "Download" button triggers file download via api.downloadExport(), shows re-export option
- [ ] T073 [US3] Create ExportStep page in `frontend/src/pages/ExportStep.tsx`: workflow step 5, displays alignment summary (quality, reference planes), ExportPanel for generation and download, "Start New Session" button to reset workflow
- [ ] T074 [US3] Verify US3 by running all US3 tests: `pytest backend/tests/contract/test_export.py backend/tests/contract/test_export_download.py backend/tests/unit/test_export.py -v` — all should PASS

**Checkpoint**: All user stories independently functional. Full end-to-end workflow: capture → analyze → scan → align → export.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories, edge case handling, and quality hardening.

- [ ] T075 [P] Add multi-face detection handling in `backend/src/services/face_analysis.py`: when MediaPipe detects > 1 face, return all face bounding boxes so frontend can prompt user to select one per spec edge case
- [ ] T076 [P] Add frontality validation in `backend/src/services/face_analysis.py`: estimate face yaw angle from MediaPipe landmarks, warn if > 15 degrees from frontal per spec edge case
- [ ] T077 [P] Add partial landmark detection handling across `backend/src/services/face_analysis.py` and `backend/src/api/routes.py`: when specific landmarks missing (e.g., occluded eye, hidden ear), include per-landmark warnings in response, allow partial results per spec edge case
- [ ] T078 [P] Add session expiry cleanup in `backend/src/services/session_store.py`: background task to purge expired sessions and free memory per constitution Privacy-First principle
- [ ] T079 [P] Add file sanitization to `backend/src/services/image_utils.py`: validate uploaded files are genuine images (not polyglot files), check magic bytes match declared MIME type per constitution Privacy & Security Requirements
- [ ] T080 [P] Write integration test for full workflow in `backend/tests/integration/test_full_workflow.py`: create session → upload frontal + side photos → analyze → upload STL → align → approve → export → download ZIP, verify ZIP contents
- [ ] T081 [P] Add responsive layout styles to frontend: ensure all pages render correctly on mobile (Android Chrome, iOS Safari) and desktop (Windows Chrome/Edge) per FR-011, test with viewport widths 375px, 768px, 1440px
- [ ] T082 Run full test suite and verify all pass: `pytest backend/tests/ -v` for backend, `cd frontend && npm test` for frontend
- [ ] T083 Run quickstart.md validation: follow all steps in `specs/001-face-scan-alignment/quickstart.md` on a clean environment to verify setup instructions work

---

## Phase 7: Local Deployment

**Purpose**: Package the application to run on the clinic's local Windows machine, accessible from any device on the local network (phones, tablets, desktops).

- [ ] T084 [P] Create `deploy/generate-cert.ps1` PowerShell script: generate a self-signed TLS certificate (New-SelfSignedCertificate or openssl) for the machine's local IP and localhost, export to `deploy/certs/cert.pem` + `deploy/certs/key.pem`, add `deploy/certs/` to `.gitignore`
- [ ] T085 Build frontend for production in `deploy/build.ps1`: run `npm run build` in `frontend/`, output static files to `frontend/dist/`
- [ ] T086 Configure uvicorn to serve both API and frontend static files in `backend/src/main.py`: mount `frontend/dist/` as StaticFiles at `/` (fallback to index.html for SPA routing), serve API at `/api/v1`, enable `--ssl-keyfile` and `--ssl-certfile` options for HTTPS
- [ ] T087 [P] Create `backend/.env.local` template: CORS_ORIGINS=https://localhost:8000, MAX_IMAGE_SIZE_MB=10, MAX_STL_SIZE_MB=100, RATE_LIMIT_PER_MINUTE=20, SECURE_COOKIES=true, SSL_CERTFILE=deploy/certs/cert.pem, SSL_KEYFILE=deploy/certs/key.pem; add `.env.local` to `.gitignore`
- [ ] T088 Create `deploy/start.ps1` one-click launch script: activate .venv, build frontend if `frontend/dist/` is missing or stale, detect local IP via Get-NetIPAddress, print access URLs (https://localhost:8000 and https://{local-ip}:8000), start uvicorn with `--host 0.0.0.0 --port 8000 --ssl-keyfile --ssl-certfile --workers 2`
- [ ] T089 [P] Create `deploy/install.ps1` first-time setup script: check Python 3.12+ and Node.js 20+ installed, create .venv if missing, pip install -r requirements.txt, npm install in frontend/, run generate-cert.ps1, create .env.local from template, build frontend
- [ ] T090 Create `deploy/README.md`: step-by-step local deployment instructions — (a) first-time setup (run install.ps1), (b) daily use (run start.ps1, open URL on any device), (c) phone access (open https://{ip}:8000 on phone, accept cert warning), (d) troubleshooting (firewall rules for port 8000, cert trust on iOS/Android)
- [ ] T091 Verify local deployment: run `deploy/start.ps1`, confirm app loads at https://localhost:8000, access from a phone on same network at https://{local-ip}:8000, test photo upload + camera capture + analysis through the single server

**Checkpoint**: Application runs from a single PowerShell command, accessible from any device on the clinic's network via HTTPS.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup (Phase 1) completion — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2) completion
- **User Story 2 (Phase 4)**: Depends on Foundational (Phase 2) completion; integrates with US1 analysis results but can be developed independently with mock data
- **User Story 3 (Phase 5)**: Depends on Foundational (Phase 2) completion; integrates with US2 alignment results but can be developed independently with mock data
- **Polish (Phase 6)**: Depends on all desired user stories being complete
- **Local Deployment (Phase 7)**: Depends on at least one user story being complete (can run after Phase 3 for MVP deployment); independent of Phase 6

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) — Requires US1 analysis results at runtime, but models/services can be built independently
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) — Requires US2 alignment results at runtime, but models/services can be built independently

### Within Each User Story

- Tests MUST be written and FAIL before implementation begins
- Models before services (Pydantic models define data contracts)
- Services before API routes (business logic before HTTP layer)
- Backend before frontend (API must exist before UI consumes it)
- Core implementation before integration

### Parallel Opportunities

**Phase 1** (all tasks can run in parallel after T001):
- T002 + T003 + T004 + T005

**Phase 2** (foundation tests in parallel, then implementation):
- T006 + T007 (parallel tests)
- T014 + T015 + T017 + T018 (parallel frontend tasks)

**Phase 3 — US1** (tests in parallel, then models in parallel, then sequential services/routes):
- T020 + T021 + T022 + T023 + T024 + T025 + T026 (all 7 tests in parallel)
- T027 + T028 (models in parallel)
- T037 + T038 + T039 (frontend components in parallel, after backend routes done)

**Phase 4 — US2** (tests in parallel, then models in parallel):
- T045 + T046 + T047 + T048 + T049 (all 5 tests in parallel)
- T050 + T051 + T052 (models in parallel)
- T059 + T060 (frontend components in parallel, after backend routes done)

**Phase 5 — US3** (tests in parallel):
- T064 + T065 + T066 (all 3 tests in parallel)

**Phase 6** (most tasks can run in parallel):
- T075 + T076 + T077 + T078 + T079 + T080 + T081 (7 parallel tasks)

**Phase 7 — Local Deployment** (scripts in parallel, then sequential integration):
- T084 + T087 + T089 (3 parallel tasks: cert script, env template, install script)
- T085 → T086 → T088 → T090 → T091 (sequential: build frontend → serve from uvicorn → launch script → docs → verify)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test US1 independently — upload photos, verify landmarks, markers, reference lines
5. Complete Phase 7: Local Deployment — run from clinic machine

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy via Phase 7 (MVP!)
3. Add User Story 2 → Test independently → Redeploy
4. Add User Story 3 → Test independently → Redeploy
5. Each story adds value without breaking previous stories; redeploy is `deploy/start.ps1`

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (backend services + API)
   - Developer B: User Story 1 (frontend components + pages)
   - After US1: Developer A on US2 backend, Developer B on US1 frontend polish → US2 frontend
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Tests MUST fail before implementing (constitution principle IV: Test-First)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
