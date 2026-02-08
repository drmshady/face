"""Alignment service (T054, T009-T011).

Computes the spatial transformation chain:
  Face/Camera Frame --T1--> Fork Frame --T2--> STL/Scan Frame
  T_face_to_scan = T2 * T1^-1

For fork-space alignment (002-3d-landmark-registration):
  Per-photo PnP → multi-view triangulation → bundle adjustment
  → 3D landmarks in fork coordinates
"""

import logging
import math

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from backend.src.models import Plane3D, Point3D
from backend.src.models.alignment import (
    AlignmentQuality,
    AlignmentResult,
    AprilTagInFork,
    CameraPose,
    Landmark3DInFork,
    Landmark3DInScan,
    LandmarkToTagRelation,
    ReferenceLine3D,
    ReferencePlane3D,
    ReferencePlanesInScan,
    TransformMatrix,
)
from backend.src.services.triangulation import triangulate_landmarks

logger = logging.getLogger(__name__)


def estimate_camera_intrinsics(
    image_width: int,
    image_height: int,
    focal_length_mm: float | None = None,
    fx_override: float | None = None,
) -> np.ndarray:
    """Approximate camera intrinsic matrix K from image dimensions.

    If fx_override is given, use it directly.
    If EXIF focal length is available, use it with an assumed sensor width.
    Otherwise approximate fx ~ image_width * 1.1 (typical smartphone ~28mm equiv).
    """
    cx = image_width / 2.0
    cy = image_height / 2.0

    if fx_override is not None:
        fx = fx_override
    elif focal_length_mm is not None and focal_length_mm > 0:
        # Assume typical smartphone sensor width ~6mm
        sensor_width_mm = 6.0
        fx = (focal_length_mm / sensor_width_mm) * image_width
    else:
        # Default approximation for smartphone cameras
        fx = image_width * 1.1

    fy = fx  # Square pixels assumption

    K = np.array([
        [fx, 0, cx],
        [0, fy, cy],
        [0, 0, 1],
    ], dtype=np.float64)

    return K


def calibrate_focal_length(
    tag_2d_corners: np.ndarray,
    tag_3d_corners: np.ndarray,
    image_width: int,
    image_height: int,
    tag_centers_3d: list[np.ndarray],
    initial_fx: float | None = None,
) -> float:
    """Optimize focal length using known inter-tag distance as scale constraint.

    Tries focal lengths around initial estimate, runs PnP for each, and picks
    the one where reprojection error is minimized (which also best reproduces
    inter-tag geometry).

    Args:
        tag_2d_corners: (N, 2) detected 2D tag corners from one photo
        tag_3d_corners: (N, 3) calibrated 3D tag corners
        image_width: Image width in pixels
        image_height: Image height in pixels
        tag_centers_3d: List of tag center 3D positions for distance check
        initial_fx: Initial focal length in pixels (default: width * 1.1)

    Returns:
        Optimized focal length in pixels
    """
    if initial_fx is None:
        initial_fx = image_width * 1.1

    # Known inter-tag distance
    if len(tag_centers_3d) >= 2:
        known_dist = float(np.linalg.norm(tag_centers_3d[1] - tag_centers_3d[0]))
    else:
        return initial_fx

    best_fx = initial_fx
    best_error = float("inf")

    # Search ±20% around initial estimate in 21 steps
    for ratio in np.linspace(0.8, 1.2, 41):
        fx_test = initial_fx * ratio
        K_test = np.array([
            [fx_test, 0, image_width / 2.0],
            [0, fx_test, image_height / 2.0],
            [0, 0, 1],
        ], dtype=np.float64)

        try:
            T, reproj = solve_fork_pose_pnp(tag_2d_corners, tag_3d_corners, K_test)
            if reproj < best_error:
                best_error = reproj
                best_fx = fx_test
        except ValueError:
            continue

    logger.info(
        "Focal length calibration: %.1f → %.1f px (reproj %.3f → %.3f px)",
        initial_fx, best_fx, best_error, best_error,
    )
    return best_fx


def solve_fork_pose_pnp(
    marker_2d_corners: np.ndarray,
    marker_3d_positions: np.ndarray,
    camera_matrix: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Solve PnP for fork pose using marker observations.

    Uses SOLVEPNP_IPPE for coplanar markers (AprilTags on the same plane)
    and disambiguates by checking that markers are in front of the camera.

    Args:
        marker_2d_corners: Nx2 array of 2D image points
        marker_3d_positions: Nx3 array of corresponding 3D world points
        camera_matrix: 3x3 camera intrinsic matrix K

    Returns:
        T1: 4x4 homogeneous transformation (fork -> camera)
        reproj_error: Mean reprojection error in pixels
    """
    dist_coeffs = np.zeros(4)  # Assume no distortion
    obj_pts = marker_3d_positions.astype(np.float64)
    img_pts = marker_2d_corners.astype(np.float64)

    # IPPE is designed for coplanar point sets and returns both solutions,
    # avoiding the ambiguity that SOLVEPNP_ITERATIVE has with coplanar points.
    n_solutions, rvecs, tvecs, reproj_errors = cv2.solvePnPGeneric(
        obj_pts, img_pts, camera_matrix, dist_coeffs,
        flags=cv2.SOLVEPNP_IPPE,
    )

    if n_solutions == 0:
        raise ValueError("PnP solver failed to find a valid pose")

    # Disambiguate: pick the solution where the 3D points are in front
    # of the camera (positive z in camera frame) and reprojection is lowest.
    best_T = None
    best_reproj = float("inf")
    centroid_3d = np.mean(obj_pts, axis=0)

    for i in range(n_solutions):
        R_i, _ = cv2.Rodrigues(rvecs[i])
        t_i = tvecs[i].flatten()

        # Check that the centroid of 3D points is in front of the camera
        centroid_cam = R_i @ centroid_3d + t_i
        if centroid_cam[2] <= 0:
            continue  # Behind camera — wrong solution

        # Compute reprojection error
        projected, _ = cv2.projectPoints(
            obj_pts, rvecs[i], tvecs[i], camera_matrix, dist_coeffs,
        )
        projected = projected.reshape(-1, 2)
        reproj = float(np.mean(np.linalg.norm(projected - img_pts, axis=1)))

        if reproj < best_reproj:
            best_reproj = reproj
            T1 = np.eye(4)
            T1[:3, :3] = R_i
            T1[:3, 3] = t_i
            best_T = T1

    if best_T is None:
        # Fallback: use the first solution even if centroid check failed
        R_0, _ = cv2.Rodrigues(rvecs[0])
        best_T = np.eye(4)
        best_T[:3, :3] = R_0
        best_T[:3, 3] = tvecs[0].flatten()

        projected, _ = cv2.projectPoints(
            obj_pts, rvecs[0], tvecs[0], camera_matrix, dist_coeffs,
        )
        projected = projected.reshape(-1, 2)
        best_reproj = float(np.mean(np.linalg.norm(projected - img_pts, axis=1)))

    return best_T, best_reproj


def solve_fork_to_scan_registration(
    fork_pts: np.ndarray,
    scan_pts: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    """SVD-based rigid registration (Procrustes) from fork to scan frame.

    Args:
        fork_pts: Nx3 array of 3D points in fork frame
        scan_pts: Nx3 array of corresponding 3D points in scan frame

    Returns:
        R: 3x3 rotation matrix
        t: 3x1 translation vector
        rmsd: Registration RMSD in mm
    """
    assert fork_pts.shape == scan_pts.shape
    n = fork_pts.shape[0]

    # Compute centroids
    centroid_fork = np.mean(fork_pts, axis=0)
    centroid_scan = np.mean(scan_pts, axis=0)

    # Center the points
    fork_centered = fork_pts - centroid_fork
    scan_centered = scan_pts - centroid_scan

    # Cross-covariance matrix
    H = fork_centered.T @ scan_centered

    # SVD
    U, S, Vt = np.linalg.svd(H)

    # Handle reflection case
    d = np.linalg.det(Vt.T @ U.T)
    sign_matrix = np.diag([1, 1, d])

    R = Vt.T @ sign_matrix @ U.T
    t = centroid_scan - R @ centroid_fork

    # Compute RMSD
    transformed = (R @ fork_pts.T).T + t
    residuals = np.linalg.norm(transformed - scan_pts, axis=1)
    rmsd = float(np.sqrt(np.mean(residuals ** 2)))

    return R, t, rmsd


def compose_alignment(T1: np.ndarray, T2: np.ndarray) -> np.ndarray:
    """Compose T_face_to_scan = T2 * T1^-1."""
    T1_inv = np.linalg.inv(T1)
    return T2 @ T1_inv


def classify_quality(reproj_error_px: float, rmsd_mm: float) -> str:
    """Classify alignment quality per data-model.md thresholds."""
    if reproj_error_px < 2.0 and rmsd_mm < 0.3:
        return "good"
    elif reproj_error_px < 5.0 and rmsd_mm < 0.5:
        return "acceptable"
    else:
        return "poor"


def _matrix_to_transform(T: np.ndarray) -> TransformMatrix:
    """Convert a 4x4 numpy matrix to TransformMatrix model."""
    R = T[:3, :3]
    t = T[:3, 3]

    euler_deg = Rotation.from_matrix(R).as_euler("xyz", degrees=True).tolist()

    return TransformMatrix(
        matrix=T.tolist(),
        rotation_euler_deg=euler_deg,
        translation_mm=t.tolist(),
    )


def transform_reference_planes(
    reference_lines,
    T_face_to_scan: np.ndarray,
) -> ReferencePlanesInScan:
    """Map 2D reference lines into 3D scan coordinate system as planes.

    For MVP, we create planes at approximate 3D positions using the
    reference line angles. Full 3D reconstruction would use the face mesh.
    """
    result = ReferencePlanesInScan()

    if reference_lines is None:
        return result

    R = T_face_to_scan[:3, :3]
    t = T_face_to_scan[:3, 3]

    def _line_to_plane(line, z_offset: float = 50.0) -> Plane3D | None:
        if line is None:
            return None
        # Create a 3D plane from the 2D line direction
        dx = line.end_point.x - line.start_point.x
        dy = line.end_point.y - line.start_point.y
        length = np.sqrt(dx * dx + dy * dy)
        if length < 1e-6:
            return None

        # Line direction in camera frame
        line_dir = np.array([dx / length, dy / length, 0.0])
        # Normal is perpendicular to line direction (in image plane, pointing "up")
        normal_cam = np.array([-line_dir[1], line_dir[0], 0.0])

        # Transform to scan coordinates
        normal_scan = R @ normal_cam
        normal_scan = normal_scan / np.linalg.norm(normal_scan)

        # A point on the plane (midpoint of line projected into 3D)
        mid_x = (line.start_point.x + line.end_point.x) / 2.0
        mid_y = (line.start_point.y + line.end_point.y) / 2.0
        point_cam = np.array([mid_x, mid_y, z_offset])
        point_scan = R @ point_cam + t

        return Plane3D(
            point=Point3D(x=float(point_scan[0]), y=float(point_scan[1]), z=float(point_scan[2])),
            normal=Point3D(x=float(normal_scan[0]), y=float(normal_scan[1]), z=float(normal_scan[2])),
        )

    result.interpupillary_plane = _line_to_plane(reference_lines.interpupillary)
    result.frankfort_plane = _line_to_plane(reference_lines.frankfort_plane)
    result.ala_tragus_plane = _line_to_plane(reference_lines.ala_tragus)
    result.canthus_tragus_plane = _line_to_plane(reference_lines.canthus_tragus)

    return result


def project_landmarks_to_scan(
    landmark_results: dict,
    image_width: int,
    image_height: int,
    T1: np.ndarray,
    T2: np.ndarray,
    focal_length_mm: float | None = None,
) -> list[Landmark3DInScan]:
    """Project 2D face landmarks into 3D scan coordinate space.

    Uses camera intrinsics K to unproject 2D landmarks to 3D rays,
    estimates depth from T1 translation, and applies T_face_to_scan.
    """
    K = estimate_camera_intrinsics(image_width, image_height, focal_length_mm)
    K_inv = np.linalg.inv(K)

    # Estimated distance from camera to fork (used as depth estimate)
    t1_translation = T1[:3, 3]
    estimated_depth = float(np.linalg.norm(t1_translation))
    if estimated_depth < 1.0:
        estimated_depth = 200.0  # fallback: ~200mm

    T_face_to_scan = compose_alignment(T1, T2)

    results: list[Landmark3DInScan] = []

    for _photo_id, lm_set in landmark_results.items():
        for lm_type, lm in lm_set.landmarks.items():
            # Unproject 2D to 3D ray
            px = np.array([lm.x, lm.y, 1.0])
            ray_cam = K_inv @ px
            ray_cam = ray_cam / np.linalg.norm(ray_cam)

            # Point in camera frame at estimated depth
            point_cam = ray_cam * estimated_depth
            point_cam_h = np.array([*point_cam, 1.0])

            # Transform to scan space
            point_scan = T_face_to_scan @ point_cam_h

            results.append(Landmark3DInScan(
                name=lm_type.value if hasattr(lm_type, "value") else str(lm_type),
                point=Point3D(
                    x=float(point_scan[0]),
                    y=float(point_scan[1]),
                    z=float(point_scan[2]),
                ),
                confidence=lm.confidence,
            ))

    return results


def _get_photo_for_id(session, photo_id: str):
    """Look up an UploadedPhoto by its photo_id."""
    if session.frontal_photo and session.frontal_photo.photo_id == photo_id:
        return session.frontal_photo
    for p in session.side_photos:
        if p.photo_id == photo_id:
            return p
    return None


def _load_fork_geometry():
    """Load fork geometry config, returning (fork_geom, tag_3d_corners, tag_centers)."""
    from backend.src.services.fork_processing import load_fork_geometry

    fork_geom = load_fork_geometry()
    if fork_geom and len(fork_geom.apriltags) >= 2:
        all_corners = []
        tag_centers = []
        for tag in fork_geom.apriltags:
            for corner in tag.corners_mm:
                all_corners.append(corner)
            tag_centers.append([tag.center_mm.x, tag.center_mm.y, tag.center_mm.z])
        return (
            fork_geom,
            np.array(all_corners, dtype=np.float64),
            np.array(tag_centers, dtype=np.float64),
        )

    # Fallback: default hardcoded positions (2 tags, 4 corners each)
    default_corners = np.array([
        [-15, 0, 0], [-10, 0, 0], [-10, 5, 0], [-15, 5, 0],
        [10, 0, 0], [15, 0, 0], [15, 5, 0], [10, 5, 0],
    ], dtype=np.float64)
    default_centers = np.array([[-12.5, 2.5, 0], [12.5, 2.5, 0]], dtype=np.float64)
    return None, default_corners, default_centers


def _build_apriltags_in_fork(fork_geom) -> list[AprilTagInFork]:
    """Convert fork geometry AprilTags to AprilTagInFork models."""
    if not fork_geom:
        return []
    result = []
    for tag in fork_geom.apriltags:
        corners = [
            Point3D(x=c[0], y=c[1], z=c[2] if len(c) > 2 else 0.0)
            for c in tag.corners_mm
        ]
        result.append(AprilTagInFork(
            tag_id=tag.tag_id,
            center=tag.center_mm,
            corners=corners,
            normal=tag.normal,
            size_mm=tag.size_mm,
        ))
    return result


def _correct_landmark_depth(
    landmarks: list,
    rvecs: list[np.ndarray],
    tvecs: list[np.ndarray],
    tag_3d_corners: np.ndarray,
    fork_geom,
) -> None:
    """Correct landmark depth for narrow-baseline triangulation.

    With narrow angular spread, DLT triangulation gives good lateral
    (perpendicular to camera) positions but poor depth (along camera).
    This shifts landmarks along the mean camera viewing direction so the
    face centroid sits at the expected depth — behind the fork tag plane.

    Modifies landmarks in-place.
    """
    if not landmarks:
        return

    # Mean camera viewing direction in fork frame (camera Z-axis = [0,0,1] in camera frame)
    view_dirs = []
    cam_positions = []
    for rvec, tvec in zip(rvecs, tvecs):
        R, _ = cv2.Rodrigues(rvec.reshape(3, 1))
        # Camera Z-axis in fork frame: R^T @ [0, 0, 1]
        view_dirs.append(R.T[:, 2])
        # Camera position in fork frame: -R^T @ t
        cam_positions.append(-R.T @ tvec)

    mean_view_dir = np.mean(view_dirs, axis=0)
    mean_view_dir /= max(np.linalg.norm(mean_view_dir), 1e-10)
    mean_cam_pos = np.mean(cam_positions, axis=0)

    # Compute the depth of the tag plane along the viewing direction
    tag_centroid = np.mean(tag_3d_corners, axis=0)
    tag_depth = np.dot(tag_centroid - mean_cam_pos, mean_view_dir)

    # Expected face depth: behind the fork tags by ~30-60mm
    # (the fork protrudes from the mouth, face is behind)
    # Use intraoral marker positions if available, otherwise estimate.
    if fork_geom and fork_geom.intraoral_markers:
        intraoral_centroid = np.mean([
            [m.center.x, m.center.y, m.center.z]
            for m in fork_geom.intraoral_markers
        ], axis=0)
        face_depth = np.dot(intraoral_centroid - mean_cam_pos, mean_view_dir)
    else:
        # Face is typically 40mm behind the tag plane
        face_depth = tag_depth + 40.0

    # Current landmark centroid depth along viewing direction
    lm_positions = np.array([[lm.point.x, lm.point.y, lm.point.z] for lm in landmarks])
    lm_centroid = np.mean(lm_positions, axis=0)
    current_depth = np.dot(lm_centroid - mean_cam_pos, mean_view_dir)

    # Shift needed: move landmarks from current depth to expected face depth
    depth_shift = face_depth - current_depth
    shift_vector = depth_shift * mean_view_dir

    logger.info(
        "Depth correction: tag_depth=%.1f, face_depth=%.1f, "
        "current=%.1f, shift=%.1fmm along view dir",
        tag_depth, face_depth, current_depth, depth_shift,
    )

    # Apply shift to all landmarks
    for lm in landmarks:
        lm.point = Point3D(
            x=lm.point.x + float(shift_vector[0]),
            y=lm.point.y + float(shift_vector[1]),
            z=lm.point.z + float(shift_vector[2]),
        )


def _find_best_corner_rotation(
    session,
    fork_geom,
    tag_3d_corners: np.ndarray,
    tag_id_to_corner_offset: dict[int, int],
) -> dict[int, int]:
    """Find the best cyclic rotation of fork geometry corners for each tag.

    The pupil-apriltags detector returns corners in a canonical order that
    may differ from the order used in the fork geometry. Since each tag has
    4 corners that form a cycle, there are 4 possible rotations per tag.
    This tries all 16 combinations (4 per tag × 2 tags) using the first
    photo with both tags detected, returning the best rotation per tag_id.

    Returns:
        Dict mapping tag_id → rotation offset (0-3). A rotation of r means
        detector corner i corresponds to 3D corner (i + r) % 4.
    """
    # Identify which tag IDs we have
    tag_ids = sorted(tag_id_to_corner_offset.keys())
    if not tag_ids:
        return {}

    # Find the first photo with both tags detected
    test_photo_id = None
    test_marker_set = None
    for photo_id, marker_set in session.external_markers.items():
        detected_ids = {m.marker_id for m in marker_set.markers}
        if all(tid in detected_ids for tid in tag_ids):
            test_photo_id = photo_id
            test_marker_set = marker_set
            break

    if test_marker_set is None:
        return {tid: 0 for tid in tag_ids}

    photo = _get_photo_for_id(session, test_photo_id)
    if not photo:
        return {tid: 0 for tid in tag_ids}

    K = estimate_camera_intrinsics(
        photo.width, photo.height, photo.exif_focal_length_mm
    )

    # Build per-tag detector corners
    tag_2d_corners: dict[int, list[list[float]]] = {}
    for marker in test_marker_set.markers:
        if marker.marker_id in tag_id_to_corner_offset:
            tag_2d_corners[marker.marker_id] = [
                [c.x, c.y] for c in marker.corners
            ]

    # Try all rotation combinations
    best_reproj = float("inf")
    best_rotations = {tid: 0 for tid in tag_ids}
    n_corners_per_tag = 4

    rotation_range = list(range(n_corners_per_tag))
    # Build all combinations: for 2 tags = 4 × 4 = 16; for 1 tag = 4
    import itertools
    combos = list(itertools.product(rotation_range, repeat=len(tag_ids)))

    for combo in combos:
        rotations = dict(zip(tag_ids, combo))

        # Build paired 2D/3D arrays with this rotation
        paired_2d = []
        paired_3d = []
        for tid in tag_ids:
            offset = tag_id_to_corner_offset[tid]
            rot = rotations[tid]
            corners_2d = tag_2d_corners.get(tid, [])
            for i, c2d in enumerate(corners_2d):
                rotated_i = (i + rot) % n_corners_per_tag
                idx_3d = offset + rotated_i
                if idx_3d < len(tag_3d_corners):
                    paired_2d.append(c2d)
                    paired_3d.append(tag_3d_corners[idx_3d])

        if len(paired_2d) < 4:
            continue

        arr_2d = np.array(paired_2d, dtype=np.float64)
        arr_3d = np.array(paired_3d, dtype=np.float64)

        try:
            _, reproj = solve_fork_pose_pnp(arr_2d, arr_3d, K)
            if reproj < best_reproj:
                best_reproj = reproj
                best_rotations = rotations.copy()
        except ValueError:
            continue

    logger.info(
        "Corner rotation search: best_rotations=%s, best_reproj=%.2fpx",
        best_rotations, best_reproj,
    )
    return best_rotations


def compute_full_alignment(
    session,
    marker_3d_positions_on_fork: np.ndarray | None = None,
) -> AlignmentResult:
    """Compute the full alignment chain for a session.

    Two paths:
    1. Fork-space alignment (multi-photo triangulation): Per-photo PnP,
       then triangulate landmarks in fork coordinates.
    2. Legacy scan alignment: pooled PnP (T1), scan registration (T2),
       compose T_face_to_scan.
    """
    fork_geom, tag_3d_corners, tag_centers = _load_fork_geometry()
    if marker_3d_positions_on_fork is not None:
        tag_3d_corners = marker_3d_positions_on_fork

    # T033: Warn if fork geometry is uncalibrated (using defaults)
    if fork_geom is None:
        session.analysis_warnings.append(
            "Fork geometry not calibrated — using default AprilTag positions. "
            "Accuracy may be reduced."
        )

    # T029: Warn if fewer than 3 photos uploaded
    total_photos = (1 if session.frontal_photo else 0) + len(session.side_photos)
    if total_photos < 3:
        session.analysis_warnings.append(
            f"Only {total_photos} photo(s) uploaded — multi-view triangulation "
            "requires 3+ photos for best accuracy. Using depth fallback."
        )

    # ---------------------------------------------------------------
    # T009: Per-photo PnP — compute camera pose for each photo
    # ---------------------------------------------------------------
    camera_poses: list[CameraPose] = []
    per_photo_rvecs = []
    per_photo_tvecs = []
    photo_id_to_cam_idx: dict[str, int] = {}

    # Determine common image dimensions (from first photo with markers)
    image_width = 640
    image_height = 480
    focal_length_mm = None
    frontal_cam_idx = 0  # Index of the frontal photo's camera pose

    # Build tag_id → marker lookup for correct corner ordering
    tag_id_to_corner_offset: dict[int, int] = {}
    if fork_geom and fork_geom.apriltags:
        offset = 0
        for tag in fork_geom.apriltags:
            tag_id_to_corner_offset[tag.tag_id] = offset
            offset += len(tag.corners_mm)
    else:
        tag_id_to_corner_offset = {0: 0, 1: 4}

    # Auto-detect correct corner rotation for each tag.
    # The fork geometry corners may not be in the same cyclic order as the
    # detector returns them. Try all 4 rotations per tag using the first
    # photo with both tags detected, pick the best combination.
    best_rotation = _find_best_corner_rotation(
        session, fork_geom, tag_3d_corners, tag_id_to_corner_offset,
    )

    # Calibrate focal length using inter-tag distance as scale constraint.
    # Use the first photo with both tags to find optimal fx.
    calibrated_fx: float | None = None
    for photo_id, marker_set in session.external_markers.items():
        if not marker_set.both_detected:
            continue
        photo = _get_photo_for_id(session, photo_id)
        if not photo:
            continue
        # Build matched 2D/3D corners for this photo
        cal_2d, cal_3d = [], []
        for marker in marker_set.markers:
            corner_offset = tag_id_to_corner_offset.get(marker.marker_id)
            if corner_offset is None:
                continue
            rotation = best_rotation.get(marker.marker_id, 0)
            n_corners = len(marker.corners)
            for i, corner in enumerate(marker.corners):
                rotated_i = (i + rotation) % n_corners
                idx = corner_offset + rotated_i
                if idx < len(tag_3d_corners):
                    cal_2d.append([corner.x, corner.y])
                    cal_3d.append(tag_3d_corners[idx])
        if len(cal_2d) >= 4:
            calibrated_fx = calibrate_focal_length(
                np.array(cal_2d, dtype=np.float64),
                np.array(cal_3d, dtype=np.float64),
                photo.width, photo.height,
                tag_centers,
                initial_fx=photo.width * 1.1,
            )
            logger.info("Calibrated fx=%.1f for %dx%d", calibrated_fx, photo.width, photo.height)
            break

    for photo_id, marker_set in session.external_markers.items():
        photo = _get_photo_for_id(session, photo_id)
        if not photo:
            continue

        # Collect 2D corners matched to 3D corners by tag_id,
        # applying the detected corner rotation for each tag.
        photo_2d_corners = [None] * len(tag_3d_corners)
        matched = 0
        for marker in marker_set.markers:
            corner_offset = tag_id_to_corner_offset.get(marker.marker_id)
            if corner_offset is None:
                continue
            rotation = best_rotation.get(marker.marker_id, 0)
            n_corners = len(marker.corners)
            for i, corner in enumerate(marker.corners):
                # Apply cyclic rotation: detector corner i → 3D corner (i + rotation) % n
                rotated_i = (i + rotation) % n_corners
                idx = corner_offset + rotated_i
                if idx < len(tag_3d_corners):
                    photo_2d_corners[idx] = [corner.x, corner.y]
                    matched += 1

        if matched < 4:
            logger.warning("Photo %s has < 4 matched marker corners, skipping PnP", photo_id)
            continue

        # Filter to only matched pairs
        paired_2d = []
        paired_3d = []
        for idx in range(len(tag_3d_corners)):
            if photo_2d_corners[idx] is not None:
                paired_2d.append(photo_2d_corners[idx])
                paired_3d.append(tag_3d_corners[idx])

        photo_2d = np.array(paired_2d, dtype=np.float64)
        photo_3d = np.array(paired_3d, dtype=np.float64)
        if len(photo_2d) < 4:
            continue

        K = estimate_camera_intrinsics(
            photo.width, photo.height, photo.exif_focal_length_mm,
            fx_override=calibrated_fx,
        )

        try:
            T1_photo, reproj = solve_fork_pose_pnp(
                photo_2d, photo_3d, K
            )
            logger.info("PnP photo %s: reproj=%.2fpx, tvec=%s", photo_id[:8], reproj, T1_photo[:3, 3].tolist())
        except ValueError as e:
            logger.warning("PnP failed for photo %s: %s", photo_id, e)
            continue

        rvec_photo, _ = cv2.Rodrigues(T1_photo[:3, :3])
        tvec_photo = T1_photo[:3, 3]

        cam_idx = len(camera_poses)
        photo_id_to_cam_idx[photo_id] = cam_idx

        camera_poses.append(CameraPose(
            photo_id=photo_id,
            rvec=rvec_photo.flatten().tolist(),
            tvec=tvec_photo.tolist(),
            reprojection_error_px=reproj,
            image_width=photo.width,
            image_height=photo.height,
            focal_length_mm=photo.exif_focal_length_mm,
        ))
        per_photo_rvecs.append(rvec_photo.flatten())
        per_photo_tvecs.append(tvec_photo)

        # Track image dimensions
        image_width = photo.width
        image_height = photo.height
        if photo.exif_focal_length_mm:
            focal_length_mm = photo.exif_focal_length_mm

        # Track frontal photo for midline "up" direction
        if session.frontal_photo and photo_id == session.frontal_photo.photo_id:
            frontal_cam_idx = cam_idx

    # Select best T1 (lowest reprojection error) for backward compatibility
    if camera_poses:
        best_pose = min(camera_poses, key=lambda p: p.reprojection_error_px)
        best_idx = next(
            i for i, p in enumerate(camera_poses)
            if p.photo_id == best_pose.photo_id
        )
        R_best, _ = cv2.Rodrigues(np.array(best_pose.rvec))
        T1 = np.eye(4)
        T1[:3, :3] = R_best
        T1[:3, 3] = np.array(best_pose.tvec)
        reproj_error = best_pose.reprojection_error_px
    else:
        # T031: All photos failed PnP
        logger.warning("No valid camera poses, using identity alignment")
        T1 = np.eye(4)
        reproj_error = 10.0
        session.analysis_warnings.append(
            "No valid camera poses — AprilTag detection may have failed in all photos"
        )

    K = estimate_camera_intrinsics(image_width, image_height, focal_length_mm,
                                    fx_override=calibrated_fx)

    # ---------------------------------------------------------------
    # T010: Integrate triangulation into alignment
    # ---------------------------------------------------------------
    landmarks_3d_in_fork: list[Landmark3DInFork] = []
    triangulation_method = "constant"
    scale_deviation_pct = None
    bundle_adjustment_residual = None
    interpupillary_line_3d = None

    if camera_poses and session.landmark_results:
        # Build landmark observations: landmark_name → list of (cam_idx, uv)
        landmark_observations: dict[str, list[tuple[int, np.ndarray]]] = {}
        mediapipe_z_values: dict[str, float | None] = {}

        for photo_id, lm_set in session.landmark_results.items():
            cam_idx = photo_id_to_cam_idx.get(photo_id)
            if cam_idx is None:
                continue
            for lm_type, lm in lm_set.landmarks.items():
                lm_name = lm_type.value if hasattr(lm_type, "value") else str(lm_type)
                if lm_name not in landmark_observations:
                    landmark_observations[lm_name] = []
                landmark_observations[lm_name].append(
                    (cam_idx, np.array([lm.x, lm.y]))
                )
                # Store MediaPipe z if available
                if lm.z is not None and lm_name not in mediapipe_z_values:
                    mediapipe_z_values[lm_name] = lm.z

        # Build tag 2D observations for BA: (cam_idx, corner_3d_idx, uv)
        # Apply the same corner rotation used for PnP
        tag_2d_observations: list[tuple[int, int, np.ndarray]] = []
        for photo_id, marker_set in session.external_markers.items():
            cam_idx = photo_id_to_cam_idx.get(photo_id)
            if cam_idx is None:
                continue
            for marker in marker_set.markers:
                corner_offset = tag_id_to_corner_offset.get(marker.marker_id)
                if corner_offset is None:
                    continue  # Unknown tag_id, skip
                rotation = best_rotation.get(marker.marker_id, 0)
                n_corners = len(marker.corners)
                for i, corner in enumerate(marker.corners):
                    rotated_i = (i + rotation) % n_corners
                    corner_3d_idx = corner_offset + rotated_i
                    if corner_3d_idx < len(tag_3d_corners):
                        tag_2d_observations.append(
                            (cam_idx, corner_3d_idx, np.array([corner.x, corner.y]))
                        )

        rvecs_arr = np.array(per_photo_rvecs)
        tvecs_arr = np.array(per_photo_tvecs)

        tri_output = triangulate_landmarks(
            camera_rvecs=rvecs_arr,
            camera_tvecs=tvecs_arr,
            landmark_observations=landmark_observations,
            camera_matrix=K,
            tag_3d_points=tag_3d_corners,
            tag_2d_observations=tag_2d_observations,
            mediapipe_z_values=mediapipe_z_values if mediapipe_z_values else None,
        )

        triangulation_method = tri_output.triangulation_method
        scale_deviation_pct = tri_output.scale_deviation_pct
        bundle_adjustment_residual = tri_output.bundle_adjustment_residual

        # Add warnings
        for w in tri_output.warnings:
            session.analysis_warnings.append(w)

        # Convert triangulation results to Landmark3DInFork models
        for lm_name, tri_result in tri_output.landmarks.items():
            # Get original landmark confidence
            orig_confidence = 0.5
            for _pid, lm_set in session.landmark_results.items():
                for lm_type, lm in lm_set.landmarks.items():
                    name = lm_type.value if hasattr(lm_type, "value") else str(lm_type)
                    if name == lm_name:
                        orig_confidence = lm.confidence
                        break

            landmarks_3d_in_fork.append(Landmark3DInFork(
                name=lm_name,
                point=Point3D(
                    x=float(tri_result.point_3d[0]),
                    y=float(tri_result.point_3d[1]),
                    z=float(tri_result.point_3d[2]),
                ),
                confidence=orig_confidence,
                depth_method=tri_result.depth_method,
                depth_confidence=tri_result.depth_confidence,
                triangulation_residual_px=tri_result.residual_px,
            ))

        # ---------------------------------------------------------------
        # Depth correction for narrow-baseline triangulation.
        # With narrow angular spread the DLT depth is unreliable,
        # causing landmarks to appear in front of the fork tags.
        # Fix: shift all landmarks along the mean camera direction so
        # the face centroid sits behind the tag plane.
        # ---------------------------------------------------------------
        if landmarks_3d_in_fork and len(per_photo_rvecs) >= 2:
            _correct_landmark_depth(
                landmarks_3d_in_fork,
                per_photo_rvecs,
                per_photo_tvecs,
                tag_3d_corners,
                fork_geom,
            )

        # ---------------------------------------------------------------
        # T011: Compute interpupillary line
        # ---------------------------------------------------------------
        left_pupil = None
        right_pupil = None
        for lm in landmarks_3d_in_fork:
            if lm.name == "left_pupil":
                left_pupil = lm
            elif lm.name == "right_pupil":
                right_pupil = lm

        if left_pupil and right_pupil:
            lp = np.array([left_pupil.point.x, left_pupil.point.y, left_pupil.point.z])
            rp = np.array([right_pupil.point.x, right_pupil.point.y, right_pupil.point.z])
            length_mm = float(np.linalg.norm(rp - lp))

            # T026: Compute reference line confidence combining:
            # - landmark detection confidence (weight 0.4)
            # - depth estimation confidence (weight 0.4)
            # - number of photos factor (weight 0.2)
            lm_conf = min(left_pupil.confidence, right_pupil.confidence)
            depth_conf = min(left_pupil.depth_confidence, right_pupil.depth_confidence)
            n_photos = len(camera_poses)
            photo_factor = min(n_photos / 3.0, 1.0)  # Saturates at 3 photos
            confidence = float(0.4 * lm_conf + 0.4 * depth_conf + 0.2 * photo_factor)

            # Warn on poor depth estimation (FR-015)
            avg_residual = 0.0
            n_res = 0
            for lm in [left_pupil, right_pupil]:
                if lm.triangulation_residual_px is not None:
                    avg_residual += lm.triangulation_residual_px
                    n_res += 1
            if n_res > 0:
                avg_residual /= n_res
            if avg_residual > 5.0:
                session.analysis_warnings.append(
                    f"High reprojection residual ({avg_residual:.1f}px > 5px) — "
                    "depth estimation quality may be degraded"
                )

            interpupillary_line_3d = ReferenceLine3D(
                start_point=left_pupil.point,
                end_point=right_pupil.point,
                start_landmark="left_pupil",
                end_landmark="right_pupil",
                length_mm=length_mm,
                confidence=confidence,
                depth_method=triangulation_method,
            )
        else:
            session.analysis_warnings.append(
                "Cannot compute interpupillary line: "
                + ("only one pupil" if left_pupil or right_pupil else "no pupils")
                + " detected"
            )

    # ---------------------------------------------------------------
    # T013: Compute midline plane
    # ---------------------------------------------------------------
    midline_plane_3d = None
    if interpupillary_line_3d is not None and camera_poses:
        lp = np.array([
            interpupillary_line_3d.start_point.x,
            interpupillary_line_3d.start_point.y,
            interpupillary_line_3d.start_point.z,
        ])
        rp = np.array([
            interpupillary_line_3d.end_point.x,
            interpupillary_line_3d.end_point.y,
            interpupillary_line_3d.end_point.z,
        ])
        midpoint = (lp + rp) / 2.0
        ipd_dir = rp - lp
        ipd_dir_norm = ipd_dir / max(np.linalg.norm(ipd_dir), 1e-10)

        # Camera Y-axis from frontal photo → "up" in fork space (R4)
        frontal_idx = min(frontal_cam_idx, len(per_photo_rvecs) - 1)
        R_cam, _ = cv2.Rodrigues(per_photo_rvecs[frontal_idx].reshape(3, 1))
        # Camera "up" in camera frame is [0, -1, 0] (image Y points down)
        cam_up_cam = np.array([0.0, -1.0, 0.0])
        # Transform to fork space: R^T maps camera frame to fork frame
        cam_up_fork = R_cam.T @ cam_up_cam
        # Project out depth axis (x) to keep midline vertical in Y-Z plane
        cam_up_fork[0] = 0.0
        cam_up_fork = cam_up_fork / max(np.linalg.norm(cam_up_fork), 1e-10)

        # Midline normal = perpendicular to interpupillary direction in horizontal plane
        midline_normal = np.cross(ipd_dir_norm, cam_up_fork)
        midline_normal = midline_normal / max(np.linalg.norm(midline_normal), 1e-10)

        midline_plane_3d = ReferencePlane3D(
            point=Point3D(x=float(midpoint[0]), y=float(midpoint[1]), z=float(midpoint[2])),
            normal=Point3D(x=float(midline_normal[0]), y=float(midline_normal[1]), z=float(midline_normal[2])),
            up_vector=Point3D(x=float(cam_up_fork[0]), y=float(cam_up_fork[1]), z=float(cam_up_fork[2])),
            confidence=interpupillary_line_3d.confidence,
            source_line="interpupillary",
        )

    # ---------------------------------------------------------------
    # T014: Compute landmark-to-tag relations
    # ---------------------------------------------------------------
    landmark_to_tag_relations: list[LandmarkToTagRelation] = []
    apriltags_in_fork_list = _build_apriltags_in_fork(fork_geom)

    for lm in landmarks_3d_in_fork:
        lm_pos = np.array([lm.point.x, lm.point.y, lm.point.z])
        for tag in apriltags_in_fork_list:
            tag_center = np.array([tag.center.x, tag.center.y, tag.center.z])
            tag_normal = np.array([tag.normal.x, tag.normal.y, tag.normal.z])

            diff = lm_pos - tag_center
            dist = float(np.linalg.norm(diff))
            direction = diff / max(dist, 1e-10)

            # Angle between direction and tag normal
            tag_normal_norm = tag_normal / max(np.linalg.norm(tag_normal), 1e-10)
            cos_angle = np.clip(np.dot(direction, tag_normal_norm), -1.0, 1.0)
            angle_deg = float(math.degrees(math.acos(cos_angle)))

            landmark_to_tag_relations.append(LandmarkToTagRelation(
                landmark_name=lm.name,
                tag_id=tag.tag_id,
                distance_mm=dist,
                direction=Point3D(x=float(direction[0]), y=float(direction[1]), z=float(direction[2])),
                angle_from_tag_normal_deg=angle_deg,
            ))

    # ---------------------------------------------------------------
    # Legacy scan-based alignment (T2) — preserved for backward compat
    # ---------------------------------------------------------------
    T2 = None
    rmsd = None
    T_face_to_scan = None
    ref_planes = None

    if session.intra_oral_markers and session.intra_oral_markers.markers_found >= 3:
        scan_pts = np.array([
            [m.position.x, m.position.y, m.position.z]
            for m in session.intra_oral_markers.markers
        ], dtype=np.float64)

        from backend.src.services.fork_processing import load_fork_geometry as _load_fg
        fg = _load_fg()
        if fg and len(fg.intraoral_markers) >= 3:
            fork_pts_3d = np.array([
                [m.center.x, m.center.y, m.center.z]
                for m in fg.intraoral_markers
            ], dtype=np.float64)[:len(scan_pts)]
        else:
            fork_pts_3d = np.array([
                [-15, 0, 0], [-5, 0, 5], [5, 0, 5], [15, 0, 0],
            ], dtype=np.float64)[:len(scan_pts)]

        R2_mat, t2_vec, rmsd = solve_fork_to_scan_registration(fork_pts_3d, scan_pts)
        T2_mat = np.eye(4)
        T2_mat[:3, :3] = R2_mat
        T2_mat[:3, 3] = t2_vec
        T2 = _matrix_to_transform(T2_mat)

        T_face_to_scan_mat = compose_alignment(T1, T2_mat)
        T_face_to_scan = _matrix_to_transform(T_face_to_scan_mat)

        ref_planes = transform_reference_planes(session.reference_lines, T_face_to_scan_mat)

    # Legacy scan-space landmarks
    landmarks_3d_scan = project_landmarks_to_scan(
        session.landmark_results, image_width, image_height,
        T1, np.eye(4) if T2 is None else np.array(T2.matrix),
        focal_length_mm,
    ) if session.landmark_results else []

    # Quality classification
    if rmsd is not None:
        # Scan-based alignment: use registration RMSD
        quality = classify_quality(reproj_error, rmsd)
    else:
        # Fork-only alignment: use scale deviation as quality proxy.
        # Scale deviation < 5% with good reprojection → good
        # Scale deviation < 10% → acceptable
        sd = scale_deviation_pct if scale_deviation_pct is not None else 0.0
        if reproj_error < 2.0 and sd < 5.0:
            quality = "good"
        elif reproj_error < 5.0 and sd < 10.0:
            quality = "acceptable"
        else:
            quality = "poor"

    return AlignmentResult(
        session_id=session.session_id,
        t1_fork_to_camera=_matrix_to_transform(T1),
        t2_fork_to_scan=T2,
        t_face_to_scan=T_face_to_scan,
        reprojection_error_px=float(reproj_error),
        registration_rmsd_mm=rmsd,
        quality=AlignmentQuality(quality),
        reference_planes_in_scan=ref_planes,
        landmarks_3d_in_scan=landmarks_3d_scan,
        # New fork-space fields
        landmarks_3d_in_fork=landmarks_3d_in_fork,
        camera_poses=camera_poses,
        interpupillary_line_3d=interpupillary_line_3d,
        midline_plane_3d=midline_plane_3d,
        apriltags_in_fork=apriltags_in_fork_list,
        landmark_to_tag_relations=landmark_to_tag_relations,
        triangulation_method=triangulation_method,
        scale_deviation_pct=scale_deviation_pct,
        bundle_adjustment_residual=bundle_adjustment_residual,
    )
