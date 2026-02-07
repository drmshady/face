"""Alignment service (T054).

Computes the spatial transformation chain:
  Face/Camera Frame --T1--> Fork Frame --T2--> STL/Scan Frame
  T_face_to_scan = T2 * T1^-1
"""

import logging

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from backend.src.models import Plane3D, Point3D
from backend.src.models.alignment import (
    AlignmentQuality,
    AlignmentResult,
    Landmark3DInScan,
    ReferencePlanesInScan,
    TransformMatrix,
)

logger = logging.getLogger(__name__)


def estimate_camera_intrinsics(
    image_width: int,
    image_height: int,
    focal_length_mm: float | None = None,
) -> np.ndarray:
    """Approximate camera intrinsic matrix K from image dimensions.

    If EXIF focal length is available, use it with an assumed sensor width.
    Otherwise approximate fx ~ image_width * 1.1 (typical smartphone ~28mm equiv).
    """
    cx = image_width / 2.0
    cy = image_height / 2.0

    if focal_length_mm is not None and focal_length_mm > 0:
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


def solve_fork_pose_pnp(
    marker_2d_corners: np.ndarray,
    marker_3d_positions: np.ndarray,
    camera_matrix: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Solve PnP for fork pose using marker observations.

    Args:
        marker_2d_corners: Nx2 array of 2D image points
        marker_3d_positions: Nx3 array of corresponding 3D world points
        camera_matrix: 3x3 camera intrinsic matrix K

    Returns:
        T1: 4x4 homogeneous transformation (fork -> camera)
        reproj_error: Mean reprojection error in pixels
    """
    dist_coeffs = np.zeros(4)  # Assume no distortion

    success, rvec, tvec = cv2.solvePnP(
        marker_3d_positions.astype(np.float64),
        marker_2d_corners.astype(np.float64),
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )

    if not success:
        raise ValueError("PnP solver failed to find a valid pose")

    R, _ = cv2.Rodrigues(rvec)

    T1 = np.eye(4)
    T1[:3, :3] = R
    T1[:3, 3] = tvec.flatten()

    # Compute reprojection error
    projected, _ = cv2.projectPoints(
        marker_3d_positions.astype(np.float64),
        rvec, tvec,
        camera_matrix,
        dist_coeffs,
    )
    projected = projected.reshape(-1, 2)
    reproj_error = float(np.mean(np.linalg.norm(
        projected - marker_2d_corners.astype(np.float64), axis=1
    )))

    return T1, reproj_error


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


def compute_full_alignment(
    session,
    marker_3d_positions_on_fork: np.ndarray | None = None,
) -> AlignmentResult:
    """Compute the full alignment chain for a session.

    Uses external markers (AprilTag) for PnP (T1) and
    intra-oral markers for registration (T2).
    """
    # Gather 2D marker observations from photos
    all_2d_corners = []
    image_width = 640
    image_height = 480
    focal_length_mm = None

    for photo_id, marker_set in session.external_markers.items():
        for marker in marker_set.markers:
            for corner in marker.corners:
                all_2d_corners.append([corner.x, corner.y])
        # Get image dimensions from photo
        photo = None
        if session.frontal_photo and session.frontal_photo.photo_id == photo_id:
            photo = session.frontal_photo
        else:
            for p in session.side_photos:
                if p.photo_id == photo_id:
                    photo = p
                    break
        if photo:
            image_width = photo.width
            image_height = photo.height
            if photo.exif_focal_length_mm:
                focal_length_mm = photo.exif_focal_length_mm

    marker_2d = np.array(all_2d_corners, dtype=np.float64) if all_2d_corners else np.zeros((0, 2))

    # If no marker 3D positions provided, try loading from fork geometry config
    if marker_3d_positions_on_fork is None:
        from backend.src.services.fork_processing import load_fork_geometry

        fork_geom = load_fork_geometry()
        if fork_geom and len(fork_geom.apriltags) >= 2:
            # Use calibrated AprilTag corners from fork geometry
            all_corners = []
            for tag in fork_geom.apriltags:
                for corner in tag.corners_mm:
                    all_corners.append(corner)
            marker_3d_positions_on_fork = np.array(all_corners, dtype=np.float64)
        else:
            # Fallback: default hardcoded positions
            marker_3d_positions_on_fork = np.array([
                [-15, 0, 0], [-10, 0, 0], [-10, 5, 0], [-15, 5, 0],
                [10, 0, 0], [15, 0, 0], [15, 5, 0], [10, 5, 0],
            ], dtype=np.float64)

    # Ensure matching point counts
    n_2d = len(marker_2d)
    n_3d = len(marker_3d_positions_on_fork)
    n_pts = min(n_2d, n_3d)

    if n_pts < 4:
        # Not enough correspondences — create a reasonable default alignment
        logger.warning("Insufficient marker correspondences (%d), using identity alignment", n_pts)
        T1 = np.eye(4)
        reproj_error = 10.0  # High error indicates poor quality
    else:
        marker_2d = marker_2d[:n_pts]
        marker_3d = marker_3d_positions_on_fork[:n_pts]

        K = estimate_camera_intrinsics(image_width, image_height, focal_length_mm)
        T1, reproj_error = solve_fork_pose_pnp(marker_2d, marker_3d, K)

    # T2: Fork-to-Scan registration from intra-oral markers
    if session.intra_oral_markers and session.intra_oral_markers.markers_found >= 3:
        scan_pts = np.array([
            [m.position.x, m.position.y, m.position.z]
            for m in session.intra_oral_markers.markers
        ], dtype=np.float64)

        # Use fork marker positions from config or defaults
        from backend.src.services.fork_processing import load_fork_geometry

        fork_geom = load_fork_geometry()
        if fork_geom and len(fork_geom.intraoral_markers) >= 3:
            fork_pts_3d = np.array([
                [m.center.x, m.center.y, m.center.z]
                for m in fork_geom.intraoral_markers
            ], dtype=np.float64)[:len(scan_pts)]
        else:
            fork_pts_3d = np.array([
                [-15, 0, 0],
                [-5, 0, 5],
                [5, 0, 5],
                [15, 0, 0],
            ], dtype=np.float64)[:len(scan_pts)]

        R2, t2, rmsd = solve_fork_to_scan_registration(fork_pts_3d, scan_pts)
        T2 = np.eye(4)
        T2[:3, :3] = R2
        T2[:3, 3] = t2
    else:
        # No intra-oral markers — use identity
        T2 = np.eye(4)
        rmsd = 1.0

    # Compose: T_face_to_scan = T2 * T1^-1
    T_face_to_scan = compose_alignment(T1, T2)

    quality = classify_quality(reproj_error, rmsd)

    # Transform reference planes
    ref_planes = transform_reference_planes(session.reference_lines, T_face_to_scan)

    # Project 2D landmarks into scan 3D space
    landmarks_3d = project_landmarks_to_scan(
        session.landmark_results,
        image_width,
        image_height,
        T1,
        T2,
        focal_length_mm,
    )

    return AlignmentResult(
        session_id=session.session_id,
        t1_fork_to_camera=_matrix_to_transform(T1),
        t2_fork_to_scan=_matrix_to_transform(T2),
        t_face_to_scan=_matrix_to_transform(T_face_to_scan),
        reprojection_error_px=float(reproj_error),
        registration_rmsd_mm=float(rmsd),
        quality=AlignmentQuality(quality),
        reference_planes_in_scan=ref_planes,
        landmarks_3d_in_scan=landmarks_3d,
    )
