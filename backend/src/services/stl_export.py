"""STL export service for combined mesh generation (T022, T025).

Exports landmarks as spheres, fork, reference geometry (interpupillary line,
midline plane, AprilTag markers), and optionally the scan into a single STL.
"""

import io
import logging
import math
from pathlib import Path

import cv2
import numpy as np
import trimesh

from backend.src.models import Point3D
from backend.src.models.alignment import Landmark3DInFork, Landmark3DInScan
from backend.src.models.session import FaceAnalysisSession
from backend.src.services.fork_processing import load_fork_geometry

logger = logging.getLogger(__name__)

# Project root for finding fork.stl
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def create_landmark_spheres(
    landmarks_3d: list[Landmark3DInScan],
    radius: float = 1.5,
) -> list[trimesh.Trimesh]:
    """Create icosphere meshes for each 3D landmark.

    Args:
        landmarks_3d: List of 3D landmarks with positions
        radius: Sphere radius in mm (default 1.5mm matches marker size)

    Returns:
        List of sphere meshes positioned at landmark locations
    """
    meshes = []
    for lm in landmarks_3d:
        sphere = trimesh.creation.icosphere(subdivisions=2, radius=radius)
        sphere.apply_translation([lm.point.x, lm.point.y, lm.point.z])
        meshes.append(sphere)
    return meshes


def load_fork_stl() -> trimesh.Trimesh:
    """Load fork.stl from project root.

    Returns:
        Fork mesh

    Raises:
        FileNotFoundError: If fork.stl not found
        ValueError: If STL cannot be parsed
    """
    fork_path = PROJECT_ROOT / "fork.stl"
    if not fork_path.exists():
        raise FileNotFoundError(f"Fork STL not found at {fork_path}")

    try:
        mesh = trimesh.load(str(fork_path), file_type="stl", force="mesh")
        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError("Fork STL did not produce a valid mesh")
        return mesh
    except Exception as e:
        raise ValueError(f"Failed to parse fork STL: {e}") from e


def project_landmarks_to_fork_space(
    session: FaceAnalysisSession,
) -> list[Landmark3DInScan]:
    """Project 2D landmarks to 3D in fork coordinate space using AprilTag PnP.

    This works after image analysis without needing intra-oral scan.
    Uses detected AprilTags to solve camera pose relative to fork,
    then projects 2D landmarks to 3D.
    """
    from backend.src.services.alignment import estimate_camera_intrinsics

    fork_geometry = load_fork_geometry()
    if fork_geometry is None or not fork_geometry.apriltags:
        raise ValueError("Fork geometry with AprilTags required for export")

    # Build mapping of tag_id -> 3D corners
    tag_corners_3d = {}
    for tag in fork_geometry.apriltags:
        tag_corners_3d[tag.tag_id] = np.array(tag.corners_mm, dtype=np.float64)

    # Gather 2D and 3D correspondences from detected markers
    all_2d_corners = []
    all_3d_corners = []
    image_width = 640
    image_height = 480
    focal_length_mm = None

    for photo_id, marker_set in session.external_markers.items():
        # Get image dimensions
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

        for marker in marker_set.markers:
            if marker.marker_id in tag_corners_3d:
                corners_3d = tag_corners_3d[marker.marker_id]
                for i, corner in enumerate(marker.corners):
                    all_2d_corners.append([corner.x, corner.y])
                    all_3d_corners.append(corners_3d[i])

    if len(all_2d_corners) < 4:
        raise ValueError("Need at least 4 AprilTag corner correspondences for PnP")

    marker_2d = np.array(all_2d_corners, dtype=np.float64)
    marker_3d = np.array(all_3d_corners, dtype=np.float64)

    # Solve PnP
    K = estimate_camera_intrinsics(image_width, image_height, focal_length_mm)
    dist_coeffs = np.zeros(4)

    success, rvec, tvec = cv2.solvePnP(
        marker_3d, marker_2d, K, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
    )
    if not success:
        raise ValueError("PnP solver failed")

    R, _ = cv2.Rodrigues(rvec)
    T_fork_to_cam = np.eye(4)
    T_fork_to_cam[:3, :3] = R
    T_fork_to_cam[:3, 3] = tvec.flatten()

    # Invert to get camera-to-fork transformation
    T_cam_to_fork = np.linalg.inv(T_fork_to_cam)

    # Estimated depth (distance to fork)
    estimated_depth = float(np.linalg.norm(tvec))
    if estimated_depth < 1.0:
        estimated_depth = 200.0

    K_inv = np.linalg.inv(K)

    # Project each 2D landmark to 3D in fork space
    results: list[Landmark3DInScan] = []
    for _photo_id, lm_set in session.landmark_results.items():
        for lm_type, lm in lm_set.landmarks.items():
            # Unproject to 3D ray in camera frame
            px = np.array([lm.x, lm.y, 1.0])
            ray_cam = K_inv @ px
            ray_cam = ray_cam / np.linalg.norm(ray_cam)

            # Point in camera frame at estimated depth
            point_cam = ray_cam * estimated_depth
            point_cam_h = np.array([*point_cam, 1.0])

            # Transform to fork space
            point_fork = T_cam_to_fork @ point_cam_h

            results.append(Landmark3DInScan(
                name=lm_type.value if hasattr(lm_type, "value") else str(lm_type),
                point=Point3D(
                    x=float(point_fork[0]),
                    y=float(point_fork[1]),
                    z=float(point_fork[2]),
                ),
                confidence=lm.confidence,
            ))

    return results


def create_fork_landmark_spheres(
    landmarks_3d: list[Landmark3DInFork],
    radius: float = 1.5,
) -> list[trimesh.Trimesh]:
    """Create icosphere meshes for fork-space landmarks."""
    meshes = []
    for lm in landmarks_3d:
        sphere = trimesh.creation.icosphere(subdivisions=2, radius=radius)
        sphere.apply_translation([lm.point.x, lm.point.y, lm.point.z])
        meshes.append(sphere)
    return meshes


def _create_cylinder_between(
    start: np.ndarray, end: np.ndarray, radius: float = 0.8
) -> trimesh.Trimesh:
    """Create a cylinder mesh between two 3D points."""
    diff = end - start
    height = float(np.linalg.norm(diff))
    if height < 1e-6:
        return trimesh.creation.icosphere(radius=radius)

    cylinder = trimesh.creation.cylinder(radius=radius, height=height, sections=12)

    # Cylinder is along Z axis; rotate to align with diff direction
    direction = diff / height
    z_axis = np.array([0, 0, 1.0])
    v = np.cross(z_axis, direction)
    c = np.dot(z_axis, direction)

    if np.linalg.norm(v) < 1e-10:
        if c < 0:
            R = np.diag([-1, -1, 1.0])
        else:
            R = np.eye(3)
    else:
        vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        R = np.eye(3) + vx + vx @ vx * (1 / (1 + c))

    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = (start + end) / 2.0
    cylinder.apply_transform(T)
    return cylinder


def _create_thin_box(
    center: np.ndarray,
    normal: np.ndarray,
    up: np.ndarray,
    width: float = 80.0,
    height: float = 80.0,
    thickness: float = 0.5,
) -> trimesh.Trimesh:
    """Create a thin box (slab) oriented by normal and up vector."""
    box = trimesh.creation.box(extents=[width, height, thickness])

    # Build rotation matrix from normal and up
    n = normal / max(np.linalg.norm(normal), 1e-10)
    u = up - np.dot(up, n) * n
    u = u / max(np.linalg.norm(u), 1e-10)
    r = np.cross(u, n)

    T = np.eye(4)
    T[:3, 0] = r
    T[:3, 1] = u
    T[:3, 2] = n
    T[:3, 3] = center
    box.apply_transform(T)
    return box


def generate_combined_stl(
    session: FaceAnalysisSession,
    include_landmarks: bool = False,
    include_fork: bool = False,
    include_scan: bool = False,
    include_apriltag_markers: bool = False,
    landmark_radius: float = 1.5,
) -> bytes:
    """Generate combined STL with interpupillary line and midline plane.

    Args:
        session: Session with alignment results
        include_landmarks: (unused, kept for API compat)
        include_fork: (unused, kept for API compat)
        include_scan: (unused, kept for API compat)
        include_apriltag_markers: (unused, kept for API compat)
        landmark_radius: (unused, kept for API compat)

    Returns:
        Binary STL file bytes

    Raises:
        ValueError: If alignment not available or no meshes to export
    """
    if session.alignment is None:
        raise ValueError("Alignment must be completed before export")

    meshes: list[trimesh.Trimesh] = []
    a = session.alignment

    # Fork mesh
    try:
        fork = load_fork_stl()
        meshes.append(fork)
        logger.info("Added fork mesh")
    except (FileNotFoundError, ValueError) as e:
        logger.warning("Could not include fork: %s", e)

    # Interpupillary line as cylinder
    if a.interpupillary_line_3d:
        lp = a.interpupillary_line_3d.start_point
        rp = a.interpupillary_line_3d.end_point
        cyl = _create_cylinder_between(
            np.array([lp.x, lp.y, lp.z]),
            np.array([rp.x, rp.y, rp.z]),
            radius=3.0,
        )
        meshes.append(cyl)
        logger.info("Added interpupillary line cylinder (%.1f mm)", a.interpupillary_line_3d.length_mm)

    # Midline as vertical cylinder along up_vector through midline point
    if a.midline_plane_3d:
        mp = a.midline_plane_3d
        center = np.array([mp.point.x, mp.point.y, mp.point.z])
        up = np.array([mp.up_vector.x, mp.up_vector.y, mp.up_vector.z])
        up = up / max(np.linalg.norm(up), 1e-10)
        half_len = 60.0  # 120mm total length
        cyl = _create_cylinder_between(
            center - up * half_len,
            center + up * half_len,
            radius=3.0,
        )
        meshes.append(cyl)
        logger.info("Added midline cylinder")

    if not meshes:
        raise ValueError("No meshes to export")

    combined = trimesh.util.concatenate(meshes)
    return combined.export(file_type="stl")


def generate_analysis_export_stl(
    session: FaceAnalysisSession,
    include_landmarks: bool = True,
    include_fork: bool = True,
    landmark_radius: float = 1.5,
) -> bytes:
    """Generate STL export after image analysis (no scan required).

    Projects 2D landmarks to 3D in fork coordinate space using AprilTag PnP.

    Args:
        session: Session with analysis results (landmarks + AprilTag detections)
        include_landmarks: Include landmark spheres
        include_fork: Include fork mesh (untransformed, in original coordinates)
        landmark_radius: Radius for landmark spheres in mm

    Returns:
        Binary STL file bytes
    """
    meshes: list[trimesh.Trimesh] = []

    # Project landmarks to fork space
    if include_landmarks:
        try:
            landmarks_3d = project_landmarks_to_fork_space(session)
            logger.info(
                "Projected %d landmarks to fork space (radius=%.1fmm)",
                len(landmarks_3d),
                landmark_radius,
            )
            meshes.extend(create_landmark_spheres(landmarks_3d, landmark_radius))
        except Exception as e:
            logger.warning("Could not project landmarks: %s", e)

    # Add fork mesh (in original coordinates)
    if include_fork:
        try:
            fork = load_fork_stl()
            meshes.append(fork)
            logger.info("Added fork mesh")
        except (FileNotFoundError, ValueError) as e:
            logger.warning("Could not include fork: %s", e)

    if not meshes:
        raise ValueError("No meshes to export")

    combined = trimesh.util.concatenate(meshes)
    return combined.export(file_type="stl")
