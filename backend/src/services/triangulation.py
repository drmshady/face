"""Multi-view triangulation and bundle adjustment service (T004-T008).

Computes 3D landmark positions in fork coordinate space from multiple
camera poses and 2D landmark observations.

Pipeline:
  1. Per-photo PnP → camera poses in fork frame (done in alignment.py)
  2. DLT triangulation → initial 3D point estimates
  3. Bundle adjustment → refined camera poses + 3D points
  4. Scale validation → verify against calibrated AprilTag distances
"""

import logging
from dataclasses import dataclass

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.distance import pdist

logger = logging.getLogger(__name__)

# Weight for fixed AprilTag reprojection residuals in bundle adjustment.
# Higher weight means tag positions anchor the optimization more strongly.
APRILTAG_WEIGHT = 10.0

# Minimum angular spread (degrees) between camera views for triangulation
MIN_ANGULAR_SPREAD_DEG = 10.0


@dataclass
class TriangulationResult:
    """Result for a single triangulated 3D point."""
    point_3d: np.ndarray  # (3,) array in fork coordinates
    residual_px: float  # Mean reprojection residual
    depth_method: str  # "bundle_adjusted" | "triangulated" | "mediapipe_z" | "constant"
    depth_confidence: float  # 0.0-1.0
    num_views: int  # Number of views used


@dataclass
class TriangulationOutput:
    """Full output from the triangulation pipeline."""
    landmarks: dict[str, TriangulationResult]  # landmark_name → result
    camera_rvecs: np.ndarray  # (N, 3) refined rotation vectors
    camera_tvecs: np.ndarray  # (N, 3) refined translation vectors
    scale_deviation_pct: float | None
    bundle_adjustment_residual: float | None
    triangulation_method: str  # "bundle_adjusted" | "mediapipe_z" | "constant"
    warnings: list[str]


def project_point(
    point_3d: np.ndarray,
    rvec: np.ndarray,
    tvec: np.ndarray,
    K: np.ndarray,
) -> np.ndarray:
    """Project a 3D point to 2D using camera pose and intrinsics.

    Returns:
        (2,) array of projected pixel coordinates [u, v].
    """
    R, _ = cv2.Rodrigues(rvec.reshape(3, 1))
    point_cam = R @ point_3d + tvec
    if point_cam[2] <= 0:
        return np.array([1e6, 1e6])  # Behind camera
    proj = K @ point_cam
    return proj[:2] / proj[2]


# ---------------------------------------------------------------------------
# T004: Multi-view DLT triangulation
# ---------------------------------------------------------------------------


def triangulate_point_multiview(
    proj_matrices: list[np.ndarray],
    observations: list[np.ndarray],
) -> np.ndarray:
    """Triangulate a 3D point from N views using DLT (Direct Linear Transform).

    Builds the 2N×4 system matrix A where each view contributes two rows,
    then solves via SVD for the homogeneous 3D point.

    Args:
        proj_matrices: List of N 3×4 projection matrices (P = K @ [R|t]).
        observations: List of N (2,) arrays of 2D pixel coordinates.

    Returns:
        (3,) array of the triangulated 3D point in world coordinates.

    Raises:
        ValueError: If fewer than 2 views provided.
    """
    n = len(proj_matrices)
    if n < 2:
        raise ValueError(f"Need at least 2 views for triangulation, got {n}")

    A = np.zeros((2 * n, 4))
    for i in range(n):
        P = proj_matrices[i]
        u, v = observations[i]
        A[2 * i] = u * P[2] - P[0]
        A[2 * i + 1] = v * P[2] - P[1]

    # Solve via SVD: the solution is the last column of V^T
    _, _, Vt = np.linalg.svd(A)
    X_h = Vt[-1]

    # Convert from homogeneous
    if abs(X_h[3]) < 1e-10:
        logger.warning("Degenerate triangulation (point at infinity)")
        return np.array([0.0, 0.0, 0.0])

    return X_h[:3] / X_h[3]


# ---------------------------------------------------------------------------
# T005: Bundle adjustment
# ---------------------------------------------------------------------------


def _ba_residuals(
    params: np.ndarray,
    n_cameras: int,
    n_points: int,
    camera_indices: np.ndarray,
    point_indices: np.ndarray,
    points_2d: np.ndarray,
    K: np.ndarray,
    fixed_3d_points: np.ndarray,
    fixed_2d_points: np.ndarray,
    fixed_camera_indices: np.ndarray,
) -> np.ndarray:
    """Residual function for bundle adjustment.

    Parameter vector layout:
        [camera_0_rvec(3), camera_0_tvec(3), ..., camera_N_rvec, camera_N_tvec,
         point_0_xyz(3), ..., point_M_xyz(3)]

    Residuals include:
        1. Landmark reprojection errors (observed - projected)
        2. Fixed AprilTag reprojection errors (weighted higher)
    """
    camera_params = params[: n_cameras * 6].reshape(n_cameras, 6)
    points_3d = params[n_cameras * 6 :].reshape(n_points, 3)

    residuals = []

    # Landmark reprojection residuals
    for obs_idx in range(len(points_2d)):
        cam_idx = camera_indices[obs_idx]
        pt_idx = point_indices[obs_idx]
        rvec = camera_params[cam_idx, :3]
        tvec = camera_params[cam_idx, 3:6]
        projected = project_point(points_3d[pt_idx], rvec, tvec, K)
        residuals.append(projected[0] - points_2d[obs_idx, 0])
        residuals.append(projected[1] - points_2d[obs_idx, 1])

    # Fixed AprilTag reprojection residuals (high weight)
    for obs_idx in range(len(fixed_2d_points)):
        cam_idx = fixed_camera_indices[obs_idx]
        rvec = camera_params[cam_idx, :3]
        tvec = camera_params[cam_idx, 3:6]
        projected = project_point(fixed_3d_points[obs_idx], rvec, tvec, K)
        residuals.append((projected[0] - fixed_2d_points[obs_idx, 0]) * APRILTAG_WEIGHT)
        residuals.append((projected[1] - fixed_2d_points[obs_idx, 1]) * APRILTAG_WEIGHT)

    return np.array(residuals)


def bundle_adjust(
    rvecs_init: np.ndarray,
    tvecs_init: np.ndarray,
    points_3d_init: np.ndarray,
    camera_indices: np.ndarray,
    point_indices: np.ndarray,
    points_2d: np.ndarray,
    K: np.ndarray,
    fixed_3d_points: np.ndarray,
    fixed_2d_points: np.ndarray,
    fixed_camera_indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Run bundle adjustment to refine camera poses and 3D landmark positions.

    AprilTag 3D positions are FIXED (not optimized) to preserve scale.

    Args:
        rvecs_init: (N, 3) initial Rodrigues rotation vectors per camera.
        tvecs_init: (N, 3) initial translation vectors per camera.
        points_3d_init: (M, 3) initial 3D landmark positions.
        camera_indices: (K,) camera index for each observation.
        point_indices: (K,) point index for each observation.
        points_2d: (K, 2) observed 2D pixel coordinates.
        K: (3, 3) camera intrinsic matrix.
        fixed_3d_points: (F, 3) known AprilTag 3D positions.
        fixed_2d_points: (F, 2) observed AprilTag 2D positions.
        fixed_camera_indices: (F,) camera index for each fixed observation.

    Returns:
        rvecs_refined: (N, 3) refined rotation vectors.
        tvecs_refined: (N, 3) refined translation vectors.
        points_3d_refined: (M, 3) refined 3D landmark positions.
        residual: Mean reprojection error in pixels.
    """
    n_cameras = len(rvecs_init)
    n_points = len(points_3d_init)

    # Pack parameters: cameras first, then points
    x0 = np.concatenate([
        np.hstack([rvecs_init, tvecs_init]).ravel(),
        points_3d_init.ravel(),
    ])

    result = least_squares(
        _ba_residuals,
        x0,
        method="lm",
        args=(
            n_cameras,
            n_points,
            camera_indices,
            point_indices,
            points_2d,
            K,
            fixed_3d_points,
            fixed_2d_points,
            fixed_camera_indices,
        ),
        max_nfev=200,
    )

    # Unpack results
    camera_params = result.x[: n_cameras * 6].reshape(n_cameras, 6)
    rvecs_refined = camera_params[:, :3]
    tvecs_refined = camera_params[:, 3:6]
    points_3d_refined = result.x[n_cameras * 6 :].reshape(n_points, 3)

    # Compute mean reprojection error (landmark observations only, no weight)
    total_err = 0.0
    count = 0
    for obs_idx in range(len(points_2d)):
        cam_idx = camera_indices[obs_idx]
        pt_idx = point_indices[obs_idx]
        projected = project_point(
            points_3d_refined[pt_idx],
            rvecs_refined[cam_idx],
            tvecs_refined[cam_idx],
            K,
        )
        total_err += np.linalg.norm(projected - points_2d[obs_idx])
        count += 1

    residual = total_err / max(count, 1)

    return rvecs_refined, tvecs_refined, points_3d_refined, residual


# ---------------------------------------------------------------------------
# T006: Scale validation
# ---------------------------------------------------------------------------


def validate_scale(
    computed_tag_positions: np.ndarray,
    calibrated_tag_positions: np.ndarray,
) -> float:
    """Validate scale by comparing inter-tag distances to calibrated values.

    Args:
        computed_tag_positions: (N, 3) computed tag center positions.
        calibrated_tag_positions: (N, 3) calibrated tag center positions.

    Returns:
        Maximum deviation percentage across all pairwise distances.
    """
    if len(computed_tag_positions) < 2 or len(calibrated_tag_positions) < 2:
        return 0.0

    computed_dists = pdist(computed_tag_positions)
    calibrated_dists = pdist(calibrated_tag_positions)

    # Avoid division by zero
    mask = calibrated_dists > 1e-6
    if not np.any(mask):
        return 0.0

    deviation_pct = (
        np.abs(computed_dists[mask] - calibrated_dists[mask])
        / calibrated_dists[mask]
        * 100
    )
    return float(np.max(deviation_pct))


# ---------------------------------------------------------------------------
# T007: Single-photo depth fallback
# ---------------------------------------------------------------------------


def estimate_depth_single_photo(
    landmark_2d: np.ndarray,
    mediapipe_z: float | None,
    camera_distance: float,
    camera_matrix: np.ndarray,
    rvec: np.ndarray,
    tvec: np.ndarray,
) -> TriangulationResult:
    """Estimate 3D landmark position from a single photo.

    Uses MediaPipe face mesh z-coordinates scaled by PnP-derived
    camera distance if available. Falls back to constant depth.

    Args:
        landmark_2d: (2,) pixel coordinates of the landmark.
        mediapipe_z: MediaPipe's relative z value (or None).
        camera_distance: Distance from camera to fork from PnP (mm).
        camera_matrix: (3, 3) camera intrinsic matrix K.
        rvec: (3,) Rodrigues rotation from PnP.
        tvec: (3,) translation from PnP.

    Returns:
        TriangulationResult with the 3D position in fork coordinates.
    """
    K_inv = np.linalg.inv(camera_matrix)

    # Unproject to ray in camera frame
    px_h = np.array([landmark_2d[0], landmark_2d[1], 1.0])
    ray_cam = K_inv @ px_h
    ray_cam = ray_cam / np.linalg.norm(ray_cam)

    if mediapipe_z is not None:
        # Scale MediaPipe z: depth_mm = camera_distance * (1.0 + z_mp * scale_factor)
        # MediaPipe z is normalized by inter-eye distance; scale_factor converts
        # to mm offset from the mean face depth.
        scale_factor = 0.5  # Empirical factor
        depth = camera_distance * (1.0 + mediapipe_z * scale_factor)
        depth_method = "mediapipe_z"
        depth_confidence = 0.4
    else:
        depth = camera_distance
        depth_method = "constant"
        depth_confidence = 0.1

    # Point in camera frame
    point_cam = ray_cam * depth

    # Transform to fork frame: point_fork = R^-1 @ (point_cam - t)
    R, _ = cv2.Rodrigues(rvec.reshape(3, 1))
    point_fork = R.T @ (point_cam - tvec)

    return TriangulationResult(
        point_3d=point_fork,
        residual_px=0.0,  # No reprojection check for single photo
        depth_method=depth_method,
        depth_confidence=depth_confidence,
        num_views=1,
    )


# ---------------------------------------------------------------------------
# T008: Orchestrator
# ---------------------------------------------------------------------------


def _compute_angular_spread(rvecs: np.ndarray) -> float:
    """Compute the maximum angular difference between camera viewing directions.

    Returns:
        Maximum angle in degrees between any pair of camera Z-axes.
    """
    if len(rvecs) < 2:
        return 0.0

    z_axes = []
    for rvec in rvecs:
        R, _ = cv2.Rodrigues(rvec.reshape(3, 1))
        # Camera Z-axis in world frame: third column of R^T
        z_axes.append(R.T[:, 2])

    max_angle = 0.0
    for i in range(len(z_axes)):
        for j in range(i + 1, len(z_axes)):
            cos_angle = np.clip(np.dot(z_axes[i], z_axes[j]), -1.0, 1.0)
            angle = np.degrees(np.arccos(cos_angle))
            max_angle = max(max_angle, angle)

    return max_angle


def triangulate_landmarks(
    camera_rvecs: np.ndarray,
    camera_tvecs: np.ndarray,
    landmark_observations: dict[str, list[tuple[int, np.ndarray]]],
    camera_matrix: np.ndarray,
    tag_3d_points: np.ndarray,
    tag_2d_observations: list[tuple[int, int, np.ndarray]],
    mediapipe_z_values: dict[str, float | None] | None = None,
) -> TriangulationOutput:
    """Top-level orchestrator for multi-view landmark triangulation.

    Pipeline:
        1. Build projection matrices from camera poses
        2. Check angular spread → fall back to single-photo if insufficient
        3. Triangulate each landmark via DLT
        4. Bundle adjust (refine camera poses + 3D points jointly)
        5. Validate scale against calibrated tag distances

    Args:
        camera_rvecs: (N, 3) Rodrigues rotation vectors per camera.
        camera_tvecs: (N, 3) translation vectors per camera.
        landmark_observations: Dict of landmark_name → list of (camera_idx, uv(2,)).
        camera_matrix: (3, 3) intrinsic matrix K.
        tag_3d_points: (F, 3) calibrated AprilTag 3D positions in fork space.
        tag_2d_observations: List of (camera_idx, corner_3d_idx, uv(2,)) for each tag corner.
        mediapipe_z_values: Optional dict of landmark_name → MediaPipe z value.

    Returns:
        TriangulationOutput with all results.
    """
    warnings: list[str] = []
    n_cameras = len(camera_rvecs)

    if n_cameras == 0:
        return TriangulationOutput(
            landmarks={},
            camera_rvecs=camera_rvecs,
            camera_tvecs=camera_tvecs,
            scale_deviation_pct=None,
            bundle_adjustment_residual=None,
            triangulation_method="constant",
            warnings=["No camera poses available"],
        )

    # Check angular spread
    angular_spread = _compute_angular_spread(camera_rvecs)
    use_triangulation = n_cameras >= 2 and angular_spread >= MIN_ANGULAR_SPREAD_DEG

    logger.info(
        "Triangulation: %d cameras, angular_spread=%.1f°, use_tri=%s",
        n_cameras, angular_spread, use_triangulation,
    )

    if n_cameras >= 2 and not use_triangulation:
        warnings.append(
            f"Angular spread too narrow ({angular_spread:.1f}° < {MIN_ANGULAR_SPREAD_DEG}°), "
            f"using single-photo depth fallback"
        )

    # --- Single-photo fallback path ---
    if not use_triangulation:
        # Use the camera with the lowest index (typically frontal)
        best_cam = 0
        camera_distance = float(np.linalg.norm(camera_tvecs[best_cam]))
        mp_z = mediapipe_z_values or {}

        results: dict[str, TriangulationResult] = {}
        for lm_name, obs_list in landmark_observations.items():
            # Find observation from best camera, or use first available
            obs_2d = None
            for cam_idx, uv in obs_list:
                if cam_idx == best_cam:
                    obs_2d = uv
                    break
            if obs_2d is None and obs_list:
                obs_2d = obs_list[0][1]

            if obs_2d is not None:
                results[lm_name] = estimate_depth_single_photo(
                    obs_2d,
                    mp_z.get(lm_name),
                    camera_distance,
                    camera_matrix,
                    camera_rvecs[best_cam],
                    camera_tvecs[best_cam],
                )

        method = "mediapipe_z" if mediapipe_z_values else "constant"
        return TriangulationOutput(
            landmarks=results,
            camera_rvecs=camera_rvecs,
            camera_tvecs=camera_tvecs,
            scale_deviation_pct=None,
            bundle_adjustment_residual=None,
            triangulation_method=method,
            warnings=warnings,
        )

    # --- Multi-view triangulation path ---
    logger.info(
        "Triangulating with %d cameras, angular spread %.1f°",
        n_cameras, angular_spread,
    )

    # Step 1: Build projection matrices P_i = K @ [R_i | t_i]
    proj_matrices = []
    for i in range(n_cameras):
        R, _ = cv2.Rodrigues(camera_rvecs[i].reshape(3, 1))
        Rt = np.hstack([R, camera_tvecs[i].reshape(3, 1)])
        P = camera_matrix @ Rt
        proj_matrices.append(P)

    # Step 2: Initial DLT triangulation for each landmark
    landmark_names = []
    initial_points = []
    ba_camera_indices = []
    ba_point_indices = []
    ba_points_2d = []

    for lm_name, obs_list in landmark_observations.items():
        if len(obs_list) < 2:
            # Can't triangulate from single view — skip for now
            continue

        cam_indices = [cam_idx for cam_idx, _ in obs_list]
        uvs = [uv for _, uv in obs_list]

        lm_proj = [proj_matrices[ci] for ci in cam_indices]

        try:
            point_3d = triangulate_point_multiview(lm_proj, uvs)
        except ValueError as e:
            logger.warning("Triangulation failed for %s: %s", lm_name, e)
            continue

        pt_idx = len(initial_points)
        landmark_names.append(lm_name)
        initial_points.append(point_3d)

        # Record observations for BA
        for cam_idx, uv in obs_list:
            ba_camera_indices.append(cam_idx)
            ba_point_indices.append(pt_idx)
            ba_points_2d.append(uv)

    if not initial_points:
        warnings.append("No landmarks could be triangulated from multiple views")
        return TriangulationOutput(
            landmarks={},
            camera_rvecs=camera_rvecs,
            camera_tvecs=camera_tvecs,
            scale_deviation_pct=None,
            bundle_adjustment_residual=None,
            triangulation_method="constant",
            warnings=warnings,
        )

    points_3d_init = np.array(initial_points)
    # Step 3: Prepare fixed AprilTag observations for BA
    # Each observation is (cam_idx, corner_3d_idx, uv) — use index to look up 3D point
    fixed_3d = []
    fixed_2d = []
    fixed_cam = []
    for cam_idx, corner_3d_idx, uv in tag_2d_observations:
        if corner_3d_idx < len(tag_3d_points):
            fixed_3d.append(tag_3d_points[corner_3d_idx])
            fixed_2d.append(uv)
            fixed_cam.append(cam_idx)

    fixed_3d_arr = np.array(fixed_3d) if fixed_3d else np.zeros((0, 3))
    fixed_2d_arr = np.array(fixed_2d) if fixed_2d else np.zeros((0, 2))
    fixed_cam_arr = np.array(fixed_cam, dtype=int) if fixed_cam else np.zeros(0, dtype=int)

    # Step 4: Bundle adjustment
    try:
        rvecs_refined, tvecs_refined, points_refined, ba_residual = bundle_adjust(
            camera_rvecs.copy(),
            camera_tvecs.copy(),
            points_3d_init.copy(),
            np.array(ba_camera_indices, dtype=int),
            np.array(ba_point_indices, dtype=int),
            np.array(ba_points_2d),
            camera_matrix,
            fixed_3d_arr,
            fixed_2d_arr,
            fixed_cam_arr,
        )

        # Sanity check: BA can diverge with narrow baselines. If the refined
        # points are much larger than the DLT estimates, fall back to DLT.
        dlt_extent = float(np.max(np.abs(points_3d_init)))
        ba_extent = float(np.max(np.abs(points_refined)))
        # Allow up to 3x expansion from DLT (generous); beyond that, BA diverged
        if ba_extent > max(dlt_extent * 3.0, 500.0):
            logger.warning(
                "BA diverged (extent %.1f >> DLT %.1f), using DLT results",
                ba_extent, dlt_extent,
            )
            rvecs_refined = camera_rvecs
            tvecs_refined = camera_tvecs
            points_refined = points_3d_init
            ba_residual = None
            method = "triangulated"
            warnings.append("Bundle adjustment diverged, using DLT results")
        else:
            method = "bundle_adjusted"
            logger.info("Bundle adjustment converged, residual=%.2f px", ba_residual)
    except Exception as e:
        logger.warning("Bundle adjustment failed: %s, using DLT results", e)
        rvecs_refined = camera_rvecs
        tvecs_refined = camera_tvecs
        points_refined = points_3d_init
        ba_residual = None
        method = "triangulated"
        warnings.append(f"Bundle adjustment failed: {e}")

    # Step 5: Compute per-landmark reprojection residuals
    results: dict[str, TriangulationResult] = {}
    for pt_idx, lm_name in enumerate(landmark_names):
        # Compute mean reprojection error for this landmark
        obs_list = landmark_observations[lm_name]
        total_err = 0.0
        count = 0
        for cam_idx, uv in obs_list:
            projected = project_point(
                points_refined[pt_idx],
                rvecs_refined[cam_idx],
                tvecs_refined[cam_idx],
                camera_matrix,
            )
            total_err += np.linalg.norm(projected - uv)
            count += 1

        residual_px = total_err / max(count, 1)

        # Depth confidence based on number of views and residual
        n_views = len(obs_list)
        if residual_px < 2.0 and n_views >= 3:
            depth_confidence = 0.9
        elif residual_px < 5.0 and n_views >= 2:
            depth_confidence = 0.7
        else:
            depth_confidence = 0.4

        results[lm_name] = TriangulationResult(
            point_3d=points_refined[pt_idx],
            residual_px=residual_px,
            depth_method=method,
            depth_confidence=depth_confidence,
            num_views=n_views,
        )

    # Step 6: Scale validation
    # Group tag corner observations by their 3D index, then triangulate
    # each corner independently and compare inter-corner distances.
    scale_deviation = None
    if len(tag_3d_points) >= 2:
        tag_obs_by_point: dict[int, list[tuple[int, np.ndarray]]] = {}
        for cam_idx, corner_3d_idx, uv in tag_2d_observations:
            if corner_3d_idx not in tag_obs_by_point:
                tag_obs_by_point[corner_3d_idx] = []
            tag_obs_by_point[corner_3d_idx].append((cam_idx, uv))

        tag_computed = []
        tag_calibrated = []
        for pt_key in sorted(tag_obs_by_point.keys()):
            obs = tag_obs_by_point[pt_key]
            if len(obs) >= 2:
                tag_proj = [proj_matrices[ci] for ci, _ in obs]
                tag_uvs = [uv for _, uv in obs]
                try:
                    tag_pt = triangulate_point_multiview(tag_proj, tag_uvs)
                    tag_computed.append(tag_pt)
                    tag_calibrated.append(tag_3d_points[pt_key])
                except ValueError:
                    pass

        if len(tag_computed) >= 2:
            computed_arr = np.array(tag_computed)
            calibrated_arr = np.array(tag_calibrated)

            scale_deviation = validate_scale(computed_arr, calibrated_arr)

            if scale_deviation > 2.0:
                warnings.append(
                    f"Scale deviation {scale_deviation:.1f}% exceeds 2% threshold"
                )

    return TriangulationOutput(
        landmarks=results,
        camera_rvecs=rvecs_refined,
        camera_tvecs=tvecs_refined,
        scale_deviation_pct=scale_deviation,
        bundle_adjustment_residual=ba_residual,
        triangulation_method=method,
        warnings=warnings,
    )
