"""API routes per contracts/api.md — sessions + US1 photo/analyze endpoints."""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response, UploadFile, File, Form
from starlette.responses import JSONResponse

from backend.src.api.middleware import COOKIE_NAME
from backend.src.api.schemas import (
    ALIGNMENT_NOT_READY,
    ANALYSIS_IN_PROGRESS,
    FILE_TOO_LARGE,
    INSUFFICIENT_PHOTOS,
    INVALID_FILE_TYPE,
    INVALID_LANDMARK,
    PHOTO_NOT_FOUND,
    SCAN_PARSE_ERROR,
    SESSION_NOT_FOUND,
    make_error,
)
from backend.src.models.landmarks import LandmarkPoint, LandmarkType
from backend.src.models.session import PhotoType, SessionStatus, UploadedPhoto
from backend.src.services.image_utils import (
    draw_annotation_overlay,
    extract_focal_length,
    get_image_dimensions,
    strip_exif,
    validate_image,
)
from backend.src.services.session_store import store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session(session_id: str, request: Request):
    """Retrieve session or return (None, error_response)."""
    token = request.state.session_token
    session = store.get_session_by_id(session_id, token)
    if session is None:
        return None, JSONResponse(
            status_code=404,
            content=make_error(SESSION_NOT_FOUND, f"Session '{session_id}' not found", session_id=session_id),
        )
    return session, None


def _get_photo(session, photo_id: str):
    """Find photo in session by ID."""
    if session.frontal_photo and session.frontal_photo.photo_id == photo_id:
        return session.frontal_photo
    for p in session.side_photos:
        if p.photo_id == photo_id:
            return p
    return None


def _serialize_landmarks(lm_set):
    """Serialize a FacialLandmarkSet to dict."""
    return {
        lm_type.value: {
            "x": lm.x,
            "y": lm.y,
            "z": lm.z,
            "confidence": lm.confidence,
            "is_manual": lm.is_manual,
            "mediapipe_index": lm.mediapipe_index,
        }
        for lm_type, lm in lm_set.landmarks.items()
    }


def _serialize_markers(marker_set):
    """Serialize an ExternalMarkerSet to dict."""
    return {
        "both_detected": marker_set.both_detected,
        "markers": [
            {
                "marker_id": m.marker_id,
                "center": {"x": m.center.x, "y": m.center.y},
                "corners": [{"x": c.x, "y": c.y} for c in m.corners],
                "confidence": m.confidence,
            }
            for m in marker_set.markers
        ],
    }


def _serialize_reference_lines(ref_lines):
    """Serialize ReferenceLinesResult to dict."""
    result = {}
    for name in ("interpupillary", "frankfort_plane", "ala_tragus", "canthus_tragus"):
        line = getattr(ref_lines, name, None)
        if line is None:
            result[name] = None
        else:
            result[name] = {
                "start_landmark": line.start_landmark.value,
                "end_landmark": line.end_landmark.value,
                "start_point": {"x": line.start_point.x, "y": line.start_point.y},
                "end_point": {"x": line.end_point.x, "y": line.end_point.y},
                "angle_degrees": line.angle_degrees,
                "confidence": line.confidence,
                "warnings": line.warnings,
            }
    return result


# ---------------------------------------------------------------------------
# Session Management (Phase 2)
# ---------------------------------------------------------------------------

@router.post("/sessions", status_code=201)
async def create_session(response: Response) -> dict:
    """Create a new analysis session. Sets session cookie."""
    session, token = store.create_session()

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=3600,
    )

    return {
        "session_id": session.session_id,
        "status": session.status.value,
        "created_at": session.created_at.isoformat(),
    }


@router.get("/sessions/{session_id}")
async def get_session_endpoint(session_id: str, request: Request) -> Response:
    """Get current session state."""
    session, err = _get_session(session_id, request)
    if err:
        return err

    photos = []
    if session.frontal_photo:
        p = session.frontal_photo
        photos.append({
            "photo_id": p.photo_id,
            "photo_type": p.photo_type.value,
            "original_filename": p.original_filename,
            "width": p.width,
            "height": p.height,
        })
    for p in session.side_photos:
        photos.append({
            "photo_id": p.photo_id,
            "photo_type": p.photo_type.value,
            "original_filename": p.original_filename,
            "width": p.width,
            "height": p.height,
        })

    return JSONResponse(
        status_code=200,
        content={
            "session_id": session.session_id,
            "status": session.status.value,
            "created_at": session.created_at.isoformat(),
            "photos": photos,
            "has_scan": session.scan is not None,
            "has_alignment": session.alignment is not None,
            "has_export": False,
        },
    )


# ---------------------------------------------------------------------------
# Photo Upload (T032)
# ---------------------------------------------------------------------------

@router.post("/sessions/{session_id}/photos", status_code=201)
async def upload_photo(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
    photo_type: str = Form(...),
) -> Response:
    """Upload a face photo (frontal or side)."""
    session, err = _get_session(session_id, request)
    if err:
        return err

    # Read file
    file_bytes = await file.read()
    content_type = file.content_type or "application/octet-stream"

    # Validate file type
    type_err = validate_image(content_type, len(file_bytes))
    if type_err:
        code = INVALID_FILE_TYPE if "format" in type_err.lower() else FILE_TOO_LARGE
        return JSONResponse(status_code=400, content=make_error(code, type_err))

    # Validate photo type
    try:
        pt = PhotoType(photo_type)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content=make_error(INVALID_FILE_TYPE, f"Invalid photo_type: {photo_type}"),
        )

    # Extract focal length before stripping EXIF
    focal_length = extract_focal_length(file_bytes)

    # Strip EXIF
    clean_bytes = strip_exif(file_bytes)

    # Get dimensions
    width, height = get_image_dimensions(clean_bytes)

    # Create photo model
    photo = UploadedPhoto(
        photo_type=pt,
        original_filename=file.filename or "unknown",
        mime_type=content_type,
        width=width,
        height=height,
        file_size_bytes=len(file_bytes),
        exif_focal_length_mm=focal_length,
        image_data=clean_bytes,
    )

    # Store in session
    token = request.state.session_token
    if pt == PhotoType.frontal:
        session.frontal_photo = photo
    else:
        session.side_photos.append(photo)

    if session.status == SessionStatus.created:
        session.status = SessionStatus.photos_uploaded

    store.update_session(token, session)

    return JSONResponse(
        status_code=201,
        content={
            "photo_id": photo.photo_id,
            "photo_type": photo.photo_type.value,
            "original_filename": photo.original_filename,
            "mime_type": photo.mime_type,
            "width": photo.width,
            "height": photo.height,
            "file_size_bytes": photo.file_size_bytes,
        },
    )


# ---------------------------------------------------------------------------
# Analysis (T033 + T033a)
# ---------------------------------------------------------------------------

def _run_analysis(session_id: str, token: str) -> None:
    """Run face analysis in background. Updates session in-place."""
    from backend.src.services.face_analysis import compute_all_reference_lines, detect_landmarks
    from backend.src.services.marker_detection import detect_apriltag_markers

    session = store.get_session_by_token(token)
    if session is None:
        return

    try:
        all_photos = []
        if session.frontal_photo:
            all_photos.append(session.frontal_photo)
        all_photos.extend(session.side_photos)

        total_steps = len(all_photos) * 2 + 1  # landmarks + markers per photo + reference lines
        completed = 0

        # Step 1: Detect landmarks for each photo
        session.analysis_current_step = "detecting_landmarks"
        store.update_session(token, session)

        for photo in all_photos:
            lm_result = detect_landmarks(photo.image_data, photo.photo_id)
            session.landmark_results[photo.photo_id] = lm_result
            completed += 1
            session.analysis_progress_pct = int((completed / total_steps) * 100)
            store.update_session(token, session)

        # Step 2: Detect markers for each photo
        session.analysis_current_step = "detecting_markers"
        store.update_session(token, session)

        for photo in all_photos:
            marker_result = detect_apriltag_markers(photo.image_data, photo.photo_id)
            session.external_markers[photo.photo_id] = marker_result
            completed += 1
            session.analysis_progress_pct = int((completed / total_steps) * 100)
            store.update_session(token, session)

        # Step 3: Compute reference lines
        session.analysis_current_step = "computing_lines"
        store.update_session(token, session)

        ref_lines = compute_all_reference_lines(session.landmark_results)
        session.reference_lines = ref_lines
        completed += 1
        session.analysis_progress_pct = 100

        # Check for warnings
        warnings = []
        if ref_lines.frankfort_plane is None:
            warnings.append("Frankfort plane: porion/orbitale landmarks require manual placement")
        if ref_lines.ala_tragus is None:
            warnings.append("Tragus landmarks require manual placement on side photos")
        if ref_lines.canthus_tragus is None:
            warnings.append("Canthus-tragus line requires manual tragus placement")
        session.analysis_warnings = warnings

        session.status = SessionStatus.analysis_complete
        session.analysis_current_step = "done"
        store.update_session(token, session)

    except Exception as e:
        logger.error(f"Analysis failed for session {session_id}: {e}")
        session.analysis_current_step = "failed"
        session.analysis_warnings.append(f"Analysis error: {str(e)}")
        store.update_session(token, session)


@router.post("/sessions/{session_id}/analyze", status_code=202)
async def trigger_analysis(
    session_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """Trigger face analysis on all uploaded photos."""
    session, err = _get_session(session_id, request)
    if err:
        return err

    # Validate preconditions
    if session.frontal_photo is None or len(session.side_photos) == 0:
        return JSONResponse(
            status_code=400,
            content=make_error(
                INSUFFICIENT_PHOTOS,
                "Need at least 1 frontal and 1 side photo",
            ),
        )

    if session.status == SessionStatus.analyzing:
        return JSONResponse(
            status_code=409,
            content=make_error(ANALYSIS_IN_PROGRESS, "Analysis already in progress"),
        )

    # Set status and launch background task
    token = request.state.session_token
    session.status = SessionStatus.analyzing
    session.analysis_progress_pct = 0
    session.analysis_current_step = "starting"
    store.update_session(token, session)

    background_tasks.add_task(_run_analysis, session_id, token)

    return JSONResponse(
        status_code=202,
        content={
            "session_id": session.session_id,
            "status": "analyzing",
        },
    )


@router.get("/sessions/{session_id}/analyze/status")
async def get_analysis_status(session_id: str, request: Request) -> Response:
    """Poll analysis progress."""
    session, err = _get_session(session_id, request)
    if err:
        return err

    result: dict = {
        "session_id": session.session_id,
        "status": session.status.value,
        "progress_pct": session.analysis_progress_pct,
        "current_step": session.analysis_current_step,
        "warnings": session.analysis_warnings,
    }

    # Include full results when complete
    if session.status == SessionStatus.analysis_complete:
        photos_results = {}
        for photo_id, lm_set in session.landmark_results.items():
            marker_set = session.external_markers.get(photo_id)
            # Determine photo type
            photo = _get_photo(session, photo_id)
            photos_results[photo_id] = {
                "photo_type": photo.photo_type.value if photo else "unknown",
                "landmarks": _serialize_landmarks(lm_set),
                "external_markers": _serialize_markers(marker_set) if marker_set else {"both_detected": False, "markers": []},
                "warnings": [],
            }

        ref_lines_data = {}
        if session.reference_lines:
            ref_lines_data = _serialize_reference_lines(session.reference_lines)

        # Overall confidence
        confidences = [
            lm_set.overall_confidence
            for lm_set in session.landmark_results.values()
        ]
        overall = sum(confidences) / len(confidences) if confidences else 0.0

        result["results"] = {
            "photos": photos_results,
            "reference_lines": ref_lines_data,
            "overall_confidence": overall,
            "warnings": session.analysis_warnings,
        }

    return JSONResponse(status_code=200, content=result)


# ---------------------------------------------------------------------------
# Landmark Update (T034)
# ---------------------------------------------------------------------------

@router.put("/sessions/{session_id}/photos/{photo_id}/landmarks")
async def update_landmarks(
    session_id: str,
    photo_id: str,
    request: Request,
) -> Response:
    """Manually adjust landmark positions for a photo."""
    session, err = _get_session(session_id, request)
    if err:
        return err

    photo = _get_photo(session, photo_id)
    if photo is None:
        return JSONResponse(
            status_code=404,
            content=make_error(PHOTO_NOT_FOUND, f"Photo '{photo_id}' not found", photo_id=photo_id),
        )

    body = await request.json()
    landmarks_input = body.get("landmarks", {})

    # Get or create landmark set for this photo
    from backend.src.models.landmarks import FacialLandmarkSet

    lm_set = session.landmark_results.get(photo_id)
    if lm_set is None:
        lm_set = FacialLandmarkSet(photo_id=photo_id, landmarks={}, overall_confidence=0.0)

    updated_names = []
    for lm_name, coords in landmarks_input.items():
        # Validate landmark type
        try:
            lm_type = LandmarkType(lm_name)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content=make_error(INVALID_LANDMARK, f"Invalid landmark type: {lm_name}"),
            )

        lm_set.landmarks[lm_type] = LandmarkPoint(
            x=coords["x"],
            y=coords["y"],
            confidence=1.0,
            is_manual=True,
        )
        updated_names.append(lm_name)

    session.landmark_results[photo_id] = lm_set

    # Recompute reference lines
    from backend.src.services.face_analysis import compute_all_reference_lines

    session.reference_lines = compute_all_reference_lines(session.landmark_results)

    token = request.state.session_token
    store.update_session(token, session)

    ref_lines_data = {}
    if session.reference_lines:
        ref_lines_data = _serialize_reference_lines(session.reference_lines)

    return JSONResponse(
        status_code=200,
        content={
            "photo_id": photo_id,
            "updated_landmarks": updated_names,
            "reference_lines": ref_lines_data,
        },
    )


# ---------------------------------------------------------------------------
# Annotated Photo (T035)
# ---------------------------------------------------------------------------

@router.get("/sessions/{session_id}/photos/{photo_id}/annotated")
async def get_annotated_photo(
    session_id: str,
    photo_id: str,
    request: Request,
) -> Response:
    """Get photo with detected landmarks and reference lines overlaid."""
    session, err = _get_session(session_id, request)
    if err:
        return err

    photo = _get_photo(session, photo_id)
    if photo is None:
        return JSONResponse(
            status_code=404,
            content=make_error(PHOTO_NOT_FOUND, f"Photo '{photo_id}' not found", photo_id=photo_id),
        )

    lm_set = session.landmark_results.get(photo_id)
    marker_set = session.external_markers.get(photo_id)

    png_bytes = draw_annotation_overlay(
        photo.image_data,
        landmarks=lm_set,
        markers=marker_set,
        reference_lines=session.reference_lines,
    )

    return Response(
        content=png_bytes,
        media_type="image/png",
    )


# ---------------------------------------------------------------------------
# Scan Upload (T055)
# ---------------------------------------------------------------------------

@router.post("/sessions/{session_id}/scan", status_code=201)
async def upload_scan(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
) -> Response:
    """Upload an intra-oral STL scan file."""
    session, err = _get_session(session_id, request)
    if err:
        return err

    file_bytes = await file.read()
    filename = file.filename or "unknown.stl"

    # Validate file size
    from backend.src.config import MAX_STL_SIZE_BYTES
    if len(file_bytes) > MAX_STL_SIZE_BYTES:
        return JSONResponse(
            status_code=400,
            content=make_error(FILE_TOO_LARGE, "STL file exceeds 100 MB limit"),
        )

    # Validate it looks like STL (not obviously wrong)
    if not filename.lower().endswith(".stl") and file.content_type not in (
        "application/octet-stream",
        "model/stl",
        "application/sla",
    ):
        return JSONResponse(
            status_code=400,
            content=make_error(INVALID_FILE_TYPE, "File must be in STL format"),
        )

    # Load and parse STL
    from backend.src.services.stl_processing import detect_intra_oral_markers, load_stl

    try:
        stl_result = load_stl(file_bytes)
    except ValueError as e:
        return JSONResponse(
            status_code=422,
            content=make_error(SCAN_PARSE_ERROR, str(e)),
        )

    # Detect intra-oral markers
    marker_set = detect_intra_oral_markers(stl_result["mesh"])

    # Create scan model
    from backend.src.models.scan import IntraOralScan

    scan = IntraOralScan(
        original_filename=filename,
        file_size_bytes=len(file_bytes),
        vertex_count=stl_result["vertex_count"],
        face_count=stl_result["face_count"],
        bounding_box=stl_result["bounding_box"],
        mesh_data=stl_result["mesh"],
    )

    # Store in session
    token = request.state.session_token
    session.scan = scan
    session.scan_stl_data = file_bytes
    marker_set.scan_id = scan.scan_id
    session.intra_oral_markers = marker_set

    if session.status in (SessionStatus.analysis_complete,):
        session.status = SessionStatus.scan_uploaded
    store.update_session(token, session)

    # Serialize response
    bb = stl_result["bounding_box"]
    return JSONResponse(
        status_code=201,
        content={
            "scan_id": scan.scan_id,
            "original_filename": scan.original_filename,
            "file_size_bytes": scan.file_size_bytes,
            "vertex_count": scan.vertex_count,
            "face_count": scan.face_count,
            "bounding_box": {
                "min": {"x": bb.min.x, "y": bb.min.y, "z": bb.min.z},
                "max": {"x": bb.max.x, "y": bb.max.y, "z": bb.max.z},
            },
            "intra_oral_markers": {
                "markers_found": marker_set.markers_found,
                "sufficient": marker_set.sufficient,
                "markers": [
                    {
                        "marker_id": m.marker_id,
                        "position": {"x": m.position.x, "y": m.position.y, "z": m.position.z},
                        "fitted_radius": m.fitted_radius,
                        "confidence": m.confidence,
                        "residual": m.residual,
                    }
                    for m in marker_set.markers
                ],
            },
        },
    )


# ---------------------------------------------------------------------------
# Scan STL Download
# ---------------------------------------------------------------------------

@router.get("/sessions/{session_id}/scan/stl")
async def get_scan_stl(session_id: str, request: Request) -> Response:
    """Download the uploaded scan STL file."""
    session, err = _get_session(session_id, request)
    if err:
        return err

    if session.scan_stl_data is None:
        return JSONResponse(
            status_code=404,
            content=make_error(SESSION_NOT_FOUND, "No scan STL data available"),
        )

    return Response(content=session.scan_stl_data, media_type="application/octet-stream")


# ---------------------------------------------------------------------------
# Alignment (T056)
# ---------------------------------------------------------------------------

@router.post("/sessions/{session_id}/align")
async def trigger_alignment(session_id: str, request: Request) -> Response:
    """Compute alignment between face analysis and scan."""
    session, err = _get_session(session_id, request)
    if err:
        return err

    # Validate prerequisites
    if session.scan is None:
        return JSONResponse(
            status_code=400,
            content=make_error(ALIGNMENT_NOT_READY, "No scan uploaded"),
        )

    if session.status not in (
        SessionStatus.scan_uploaded,
        SessionStatus.analysis_complete,
        SessionStatus.alignment_complete,
    ):
        return JSONResponse(
            status_code=400,
            content=make_error(ALIGNMENT_NOT_READY, "Analysis must be complete and scan uploaded before alignment"),
        )

    # Compute alignment
    from backend.src.services.alignment import compute_full_alignment

    token = request.state.session_token
    session.status = SessionStatus.aligning
    store.update_session(token, session)

    try:
        alignment_result = compute_full_alignment(session)
    except Exception as e:
        logger.error(f"Alignment failed: {e}")
        session.status = SessionStatus.scan_uploaded
        store.update_session(token, session)
        return JSONResponse(
            status_code=400,
            content=make_error(ALIGNMENT_NOT_READY, f"Alignment computation failed: {e}"),
        )

    session.alignment = alignment_result
    session.status = SessionStatus.alignment_complete
    store.update_session(token, session)

    # Serialize response
    a = alignment_result
    return JSONResponse(
        status_code=200,
        content={
            "session_id": session.session_id,
            "status": "alignment_complete",
            "alignment": {
                "t_face_to_scan": {
                    "matrix": a.t_face_to_scan.matrix,
                    "rotation_euler_deg": a.t_face_to_scan.rotation_euler_deg,
                    "translation_mm": a.t_face_to_scan.translation_mm,
                },
                "t2_fork_to_scan": {
                    "matrix": a.t2_fork_to_scan.matrix,
                    "rotation_euler_deg": a.t2_fork_to_scan.rotation_euler_deg,
                    "translation_mm": a.t2_fork_to_scan.translation_mm,
                },
                "reprojection_error_px": a.reprojection_error_px,
                "registration_rmsd_mm": a.registration_rmsd_mm,
                "quality": a.quality.value,
                "reference_planes_in_scan": {
                    "interpupillary_plane": _serialize_plane(a.reference_planes_in_scan.interpupillary_plane),
                    "frankfort_plane": _serialize_plane(a.reference_planes_in_scan.frankfort_plane),
                    "ala_tragus_plane": _serialize_plane(a.reference_planes_in_scan.ala_tragus_plane),
                    "canthus_tragus_plane": _serialize_plane(a.reference_planes_in_scan.canthus_tragus_plane),
                },
                "landmarks_3d_in_scan": [
                    {
                        "name": lm.name,
                        "point": {"x": lm.point.x, "y": lm.point.y, "z": lm.point.z},
                        "confidence": lm.confidence,
                    }
                    for lm in a.landmarks_3d_in_scan
                ],
            },
        },
    )


def _serialize_plane(plane):
    """Serialize a Plane3D to dict or None."""
    if plane is None:
        return None
    return {
        "point": {"x": plane.point.x, "y": plane.point.y, "z": plane.point.z},
        "normal": {"x": plane.normal.x, "y": plane.normal.y, "z": plane.normal.z},
    }


# ---------------------------------------------------------------------------
# Alignment Approve (T057)
# ---------------------------------------------------------------------------

@router.post("/sessions/{session_id}/alignment/approve")
async def approve_alignment(session_id: str, request: Request) -> Response:
    """Confirm alignment result. Enables export."""
    session, err = _get_session(session_id, request)
    if err:
        return err

    if session.alignment is None:
        return JSONResponse(
            status_code=400,
            content=make_error(ALIGNMENT_NOT_READY, "No alignment to approve"),
        )

    token = request.state.session_token
    session.status = SessionStatus.export_ready
    store.update_session(token, session)

    return JSONResponse(
        status_code=200,
        content={
            "session_id": session.session_id,
            "status": "export_ready",
        },
    )


# ---------------------------------------------------------------------------
# Fork Calibration (session-independent)
# ---------------------------------------------------------------------------

# In-memory storage for the uploaded fork STL blob (for serving back to frontend)
_fork_stl_data: dict[str, bytes] = {}


@router.post("/fork/upload", status_code=200)
async def upload_fork(file: UploadFile = File(...)) -> Response:
    """Upload a fork STL file, auto-detect hex post markers."""
    import time as _time
    t_start = _time.perf_counter()
    file_bytes = await file.read()
    filename = file.filename or "fork.stl"
    logger.info("Fork upload: %d bytes, file=%s", len(file_bytes), filename)

    from backend.src.config import MAX_STL_SIZE_BYTES
    if len(file_bytes) > MAX_STL_SIZE_BYTES:
        return JSONResponse(
            status_code=400,
            content=make_error(FILE_TOO_LARGE, "Fork STL file exceeds size limit"),
        )

    if not filename.lower().endswith(".stl"):
        return JSONResponse(
            status_code=400,
            content=make_error(INVALID_FILE_TYPE, "File must be in STL format"),
        )

    from backend.src.services.stl_processing import load_stl
    try:
        stl_result = load_stl(file_bytes)
    except ValueError as e:
        return JSONResponse(
            status_code=422,
            content=make_error(SCAN_PARSE_ERROR, str(e)),
        )
    logger.info("Fork STL loaded in %.1fms", (_time.perf_counter() - t_start) * 1000)

    from backend.src.services.fork_processing import detect_hex_posts
    markers, plate_normal = detect_hex_posts(stl_result["mesh"])
    logger.info("Fork upload total: %.1fms", (_time.perf_counter() - t_start) * 1000)

    # Store STL data in memory and persist to disk
    _fork_stl_data["current"] = file_bytes
    from backend.src.services.fork_processing import save_fork_stl
    save_fork_stl(file_bytes)

    return JSONResponse(
        status_code=200,
        content={
            "markers": [
                {
                    "marker_id": m.marker_id,
                    "center": {"x": m.center.x, "y": m.center.y, "z": m.center.z},
                    "top_face_normal": {
                        "x": m.top_face_normal.x,
                        "y": m.top_face_normal.y,
                        "z": m.top_face_normal.z,
                    },
                    "radius_mm": m.radius_mm,
                    "height_mm": m.height_mm,
                    "confidence": m.confidence,
                }
                for m in markers
            ],
            "plate_normal": plate_normal,
            "vertex_count": stl_result["vertex_count"],
            "face_count": stl_result["face_count"],
        },
    )


@router.get("/fork/stl")
async def get_fork_stl() -> Response:
    """Serve the uploaded fork STL file back to the frontend."""
    stl_bytes = _fork_stl_data.get("current")
    if stl_bytes is None:
        from backend.src.services.fork_processing import load_fork_stl
        stl_bytes = load_fork_stl()
        if stl_bytes is not None:
            _fork_stl_data["current"] = stl_bytes  # cache in memory
    if stl_bytes is None:
        return JSONResponse(status_code=404, content={"error": "No fork STL uploaded"})

    return Response(content=stl_bytes, media_type="application/octet-stream")


@router.post("/fork/configure", status_code=200)
async def configure_fork(request: Request) -> Response:
    """Save fork configuration with user-placed AprilTag positions."""
    body = await request.json()

    apriltags_input = body.get("apriltags", [])
    tag_size_mm = body.get("tag_size_mm", 7.0)
    markers_input = body.get("markers", [])
    plate_normal = body.get("plate_normal", [0.0, 0.0, 1.0])

    from backend.src.services.fork_processing import compute_tag_corners, save_fork_geometry
    from backend.src.models.fork import AprilTagOnFork, ForkGeometry, HexPostMarker
    from backend.src.models import Point3D
    from datetime import datetime, timezone

    apriltags = []
    for tag_data in apriltags_input:
        center = [
            tag_data["center_mm"]["x"],
            tag_data["center_mm"]["y"],
            tag_data["center_mm"]["z"],
        ]
        normal = [
            tag_data["normal"]["x"],
            tag_data["normal"]["y"],
            tag_data["normal"]["z"],
        ]
        corners = compute_tag_corners(center, normal, tag_size_mm)
        apriltags.append(AprilTagOnFork(
            tag_id=tag_data["tag_id"],
            center_mm=Point3D(x=center[0], y=center[1], z=center[2]),
            size_mm=tag_size_mm,
            normal=Point3D(x=normal[0], y=normal[1], z=normal[2]),
            corners_mm=corners,
        ))

    intraoral_markers = []
    for m_data in markers_input:
        intraoral_markers.append(HexPostMarker(
            marker_id=m_data["marker_id"],
            center=Point3D(
                x=m_data["center"]["x"],
                y=m_data["center"]["y"],
                z=m_data["center"]["z"],
            ),
            top_face_normal=Point3D(
                x=m_data.get("top_face_normal", {}).get("x", plate_normal[0]),
                y=m_data.get("top_face_normal", {}).get("y", plate_normal[1]),
                z=m_data.get("top_face_normal", {}).get("z", plate_normal[2]),
            ),
            radius_mm=m_data.get("radius_mm", 1.5),
            height_mm=m_data.get("height_mm", 2.0),
            confidence=m_data.get("confidence", 1.0),
        ))

    geometry = ForkGeometry(
        apriltags=apriltags,
        intraoral_markers=intraoral_markers,
        plate_normal=plate_normal,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    save_fork_geometry(geometry)

    return JSONResponse(status_code=200, content=geometry.model_dump())


@router.get("/fork/geometry")
async def get_fork_geometry() -> Response:
    """Get saved fork geometry configuration."""
    from backend.src.services.fork_processing import load_fork_geometry

    geometry = load_fork_geometry()
    if geometry is None:
        return JSONResponse(
            status_code=404, content={"error": "No fork geometry configured"}
        )

    return JSONResponse(status_code=200, content=geometry.model_dump())
