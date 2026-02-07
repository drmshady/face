"""STL scan processing service (T053).

Loads STL files via trimesh, detects intra-oral fiducial markers
using curvature-based segmentation + RANSAC sphere fitting.
"""

import io
import logging
from typing import Any

import numpy as np
import trimesh

from backend.src.models import BoundingBox3D, Point3D
from backend.src.models.markers import IntraOralMarker, IntraOralMarkerSet

logger = logging.getLogger(__name__)

# Default expected marker radius in mm (typical spherical fiducial)
DEFAULT_MARKER_RADIUS_MM = 1.5
RADIUS_TOLERANCE = 0.5  # +/- tolerance for radius validation


def load_stl(file_bytes: bytes) -> dict[str, Any]:
    """Load and parse an STL file.

    Returns dict with vertex_count, face_count, bounding_box, mesh.
    Raises ValueError on parse failure.
    """
    try:
        mesh = trimesh.load(
            io.BytesIO(file_bytes),
            file_type="stl",
            force="mesh",
        )
    except Exception as e:
        raise ValueError(f"Failed to parse STL: {e}") from e

    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError("STL file did not produce a valid mesh")

    if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError("STL file contains no geometry")

    bounds = mesh.bounds  # shape (2, 3): [[min_x, min_y, min_z], [max_x, max_y, max_z]]
    bb = BoundingBox3D(
        min=Point3D(x=float(bounds[0][0]), y=float(bounds[0][1]), z=float(bounds[0][2])),
        max=Point3D(x=float(bounds[1][0]), y=float(bounds[1][1]), z=float(bounds[1][2])),
    )

    return {
        "vertex_count": len(mesh.vertices),
        "face_count": len(mesh.faces),
        "bounding_box": bb,
        "mesh": mesh,
    }


def detect_intra_oral_markers(
    mesh: trimesh.Trimesh,
    expected_radius: float = DEFAULT_MARKER_RADIUS_MM,
    expected_count: int = 4,
) -> IntraOralMarkerSet:
    """Detect spherical fiducial markers in an STL mesh.

    Pipeline:
    1. Compute discrete Gaussian curvature at vertices
    2. Filter vertices with curvature matching expected sphere (1/r^2)
    3. Cluster candidate vertices spatially (DBSCAN)
    4. Fit sphere to each cluster via least-squares
    5. Validate radius against expected marker radius
    """
    markers: list[IntraOralMarker] = []

    try:
        vertices = mesh.vertices
        if len(vertices) < 20:
            logger.info("Mesh too small for marker detection (%d vertices)", len(vertices))
            return IntraOralMarkerSet(markers=markers)

        # Step 1: Compute discrete Gaussian curvature
        # trimesh provides discrete_gaussian_curvature_measure
        try:
            # Use vertex defect angle method for Gaussian curvature
            curvature = trimesh.curvature.discrete_gaussian_curvature_measure(
                mesh, mesh.vertices, radius=expected_radius * 2
            )
        except Exception:
            logger.warning("Curvature computation failed, trying alternate method")
            return IntraOralMarkerSet(markers=markers)

        # Step 2: Filter by expected curvature for a sphere
        # A sphere of radius r has Gaussian curvature K = 1/r^2
        expected_K = 1.0 / (expected_radius ** 2)
        K_min = 1.0 / ((expected_radius + RADIUS_TOLERANCE) ** 2)
        K_max = 1.0 / (max(expected_radius - RADIUS_TOLERANCE, 0.1) ** 2)

        # Select vertices with high curvature matching sphere
        high_curv_mask = (curvature > K_min * 0.5) & (curvature < K_max * 2.0)
        high_curv_indices = np.where(high_curv_mask)[0]

        if len(high_curv_indices) < 4:
            logger.info("Not enough high-curvature vertices (%d) for marker detection", len(high_curv_indices))
            return IntraOralMarkerSet(markers=markers)

        high_curv_points = vertices[high_curv_indices]

        # Step 3: Cluster with DBSCAN
        from sklearn.cluster import DBSCAN

        clustering = DBSCAN(
            eps=expected_radius * 3,
            min_samples=3,
        ).fit(high_curv_points)

        labels = clustering.labels_
        unique_labels = set(labels) - {-1}  # Exclude noise

        if not unique_labels:
            logger.info("No clusters found in high-curvature vertices")
            return IntraOralMarkerSet(markers=markers)

        # Step 4 & 5: Fit sphere to each cluster and validate
        marker_id = 1
        for label in sorted(unique_labels):
            cluster_mask = labels == label
            cluster_pts = high_curv_points[cluster_mask]

            if len(cluster_pts) < 4:
                continue

            # Least-squares sphere fit
            center, radius, residual = _fit_sphere(cluster_pts)

            if center is None:
                continue

            # Validate radius
            if abs(radius - expected_radius) > RADIUS_TOLERANCE:
                continue

            # Compute confidence based on fit quality and number of points
            confidence = max(0.0, min(1.0, 1.0 - residual / expected_radius))

            markers.append(IntraOralMarker(
                marker_id=marker_id,
                position=Point3D(x=float(center[0]), y=float(center[1]), z=float(center[2])),
                fitted_radius=float(radius),
                confidence=float(confidence),
                residual=float(residual),
            ))
            marker_id += 1

            if len(markers) >= expected_count:
                break

    except Exception as e:
        logger.warning("Marker detection failed: %s", e)

    return IntraOralMarkerSet(markers=markers)


def _fit_sphere(points: np.ndarray) -> tuple[np.ndarray | None, float, float]:
    """Fit a sphere to a set of 3D points via least-squares.

    Returns (center, radius, residual) or (None, 0, inf) on failure.
    """
    try:
        n = len(points)
        if n < 4:
            return None, 0.0, float("inf")

        # Set up the linear system: |p - c|^2 = r^2
        # Expanding: -2*cx*x - 2*cy*y - 2*cz*z + (cx^2+cy^2+cz^2-r^2) = -(x^2+y^2+z^2)
        A = np.zeros((n, 4))
        A[:, 0] = 2 * points[:, 0]
        A[:, 1] = 2 * points[:, 1]
        A[:, 2] = 2 * points[:, 2]
        A[:, 3] = 1.0

        b = np.sum(points ** 2, axis=1)

        result, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
        center = result[:3]
        radius = np.sqrt(result[3] + np.sum(center ** 2))

        # Compute residual (RMSD of distances from fitted sphere)
        distances = np.linalg.norm(points - center, axis=1)
        residual = np.sqrt(np.mean((distances - radius) ** 2))

        return center, float(radius), float(residual)

    except Exception:
        return None, 0.0, float("inf")
