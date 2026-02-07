"""Fork STL processing service.

Detects raised hexagonal post markers on the bite fork via:
1. Find dominant plate plane from face normal histogram
2. Filter vertices elevated above the plate
3. Cluster elevated vertices with DBSCAN
4. Characterize each cluster as a hex post
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import numpy as np
import trimesh

from backend.src.models import Point3D
from backend.src.models.fork import (
    AprilTagOnFork,
    ForkGeometry,
    HexPostMarker,
)

logger = logging.getLogger(__name__)

FORK_GEOMETRY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "fork_geometry.json"
)
FORK_STL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "fork.stl"
)

# Detection parameters
MIN_ELEVATION_MM = 0.8  # minimum height above plate to be considered a post
DBSCAN_EPS_MM = 2.0  # clustering radius
DBSCAN_MIN_SAMPLES = 5  # minimum points per cluster


def detect_hex_posts(mesh: trimesh.Trimesh) -> tuple[list[HexPostMarker], list[float]]:
    """Detect hexagonal post markers on a fork STL mesh.

    Returns:
        markers: list of detected HexPostMarker
        plate_normal: dominant plate plane normal as [x, y, z]
    """
    t0 = time.perf_counter()
    markers: list[HexPostMarker] = []
    vertices = mesh.vertices
    logger.info("Fork mesh: %d vertices, %d faces", len(vertices), len(mesh.faces))

    if len(vertices) < 50:
        logger.warning("Mesh too small for hex post detection (%d vertices)", len(vertices))
        return markers, [0.0, 0.0, 1.0]

    # Step 1: Find dominant plate plane from face normals
    face_normals = mesh.face_normals  # (N, 3)
    face_areas = mesh.area_faces  # (N,)

    # Bin normals by direction (area-weighted histogram)
    # The plate surface dominates the mesh, so its normal is the most common
    # Use absolute normals (plate could face either direction)
    abs_normals = np.abs(face_normals)

    # Weight by face area for robustness
    # Find which axis has the largest component for each face
    dominant_axis = np.argmax(abs_normals, axis=1)

    # Area-weighted vote for each axis
    axis_weights = np.zeros(3)
    for axis in range(3):
        mask = dominant_axis == axis
        axis_weights[axis] = np.sum(face_areas[mask])

    # The plate normal is the axis with the most area
    plate_axis = int(np.argmax(axis_weights))

    # Refine: average the normals of faces aligned with the dominant axis
    aligned_mask = dominant_axis == plate_axis
    aligned_normals = face_normals[aligned_mask]
    aligned_areas = face_areas[aligned_mask]

    # Area-weighted average normal
    weighted_normal = np.average(aligned_normals, weights=aligned_areas, axis=0)
    plate_normal = weighted_normal / np.linalg.norm(weighted_normal)

    # Ensure plate normal points in the positive direction of the dominant axis
    if plate_normal[plate_axis] < 0:
        plate_normal = -plate_normal

    logger.info("Plate normal: [%.3f, %.3f, %.3f] (%.1fms)", *plate_normal, (time.perf_counter() - t0) * 1000)

    # Step 2: Project vertices onto plate normal to get elevation
    # Find the plate surface level (mode of projections)
    projections = vertices @ plate_normal
    # The plate level is the most common projection value
    # Use histogram to find it
    hist, bin_edges = np.histogram(projections, bins=100)
    plate_level = (bin_edges[np.argmax(hist)] + bin_edges[np.argmax(hist) + 1]) / 2

    # Elevation above plate
    elevation = projections - plate_level

    # Step 3: Filter vertices elevated above threshold
    elevated_mask = elevation > MIN_ELEVATION_MM
    elevated_indices = np.where(elevated_mask)[0]

    if len(elevated_indices) < DBSCAN_MIN_SAMPLES:
        logger.info("No elevated vertices found above %.1f mm", MIN_ELEVATION_MM)
        return markers, plate_normal.tolist()

    elevated_points = vertices[elevated_indices]
    elevated_heights = elevation[elevated_indices]

    # Step 4: Cluster with DBSCAN
    logger.info("Elevated vertices: %d (%.1fms)", len(elevated_indices), (time.perf_counter() - t0) * 1000)
    from sklearn.cluster import DBSCAN

    clustering = DBSCAN(
        eps=DBSCAN_EPS_MM,
        min_samples=DBSCAN_MIN_SAMPLES,
    ).fit(elevated_points)

    labels = clustering.labels_
    logger.info("DBSCAN done, %d clusters (%.1fms)", len(set(labels) - {-1}), (time.perf_counter() - t0) * 1000)
    unique_labels = sorted(set(labels) - {-1})

    if not unique_labels:
        logger.info("No clusters found in elevated vertices")
        return markers, plate_normal.tolist()

    # Build a set of elevated vertex indices for fast lookup per cluster
    # Map elevated_points back to original vertex indices
    elevated_vertex_set = set(elevated_indices.tolist())

    # Pre-compute: for each vertex, which faces include it
    # mesh.faces is (F, 3) array of vertex indices
    faces = mesh.faces

    # Step 5: Characterize each cluster as a hex post
    marker_id = 1
    for label in unique_labels:
        cluster_mask = labels == label
        cluster_pts = elevated_points[cluster_mask]
        cluster_heights = elevated_heights[cluster_mask]

        if len(cluster_pts) < 4:
            continue

        # Center of the cluster (top face approximation)
        center = np.mean(cluster_pts, axis=0)

        # Height: median elevation of cluster points
        height = float(np.median(cluster_heights))

        # Compute local normal for this cluster from nearby mesh faces
        # Find original vertex indices for this cluster
        cluster_orig_indices = set(elevated_indices[cluster_mask].tolist())

        # Find faces that have at least one vertex in the cluster
        face_in_cluster = np.zeros(len(faces), dtype=bool)
        for vi in cluster_orig_indices:
            face_in_cluster |= np.any(faces == vi, axis=1)

        cluster_face_indices = np.where(face_in_cluster)[0]

        if len(cluster_face_indices) >= 3:
            # Area-weighted average of face normals for this cluster
            cluster_face_normals = face_normals[cluster_face_indices]
            cluster_face_areas = face_areas[cluster_face_indices]
            local_normal = np.average(cluster_face_normals, weights=cluster_face_areas, axis=0)
            norm_len = np.linalg.norm(local_normal)
            if norm_len > 1e-8:
                local_normal = local_normal / norm_len
            else:
                local_normal = plate_normal.copy()
            # Ensure local normal points away from plate (same hemisphere as plate normal)
            if np.dot(local_normal, plate_normal) < 0:
                local_normal = -local_normal
        else:
            local_normal = plate_normal.copy()

        # Radius: max distance from center in the plane perpendicular to local normal
        center_to_pts = cluster_pts - center
        along_normal = np.outer(center_to_pts @ local_normal, local_normal)
        in_plane = center_to_pts - along_normal
        distances = np.linalg.norm(in_plane, axis=1)
        radius = float(np.percentile(distances, 90))  # 90th percentile for robustness

        # Confidence based on cluster size and shape regularity
        # More points and consistent height -> higher confidence
        height_std = float(np.std(cluster_heights))
        confidence = min(1.0, len(cluster_pts) / 50.0) * max(0.0, 1.0 - height_std / height)
        confidence = max(0.1, confidence)

        markers.append(HexPostMarker(
            marker_id=marker_id,
            center=Point3D(x=float(center[0]), y=float(center[1]), z=float(center[2])),
            top_face_normal=Point3D(
                x=float(local_normal[0]),
                y=float(local_normal[1]),
                z=float(local_normal[2]),
            ),
            radius_mm=radius,
            height_mm=height,
            confidence=float(confidence),
        ))
        marker_id += 1

    logger.info("Detected %d hex post markers (total %.1fms)", len(markers), (time.perf_counter() - t0) * 1000)
    return markers, plate_normal.tolist()


def compute_tag_corners(
    center: list[float],
    normal: list[float],
    size_mm: float,
) -> list[list[float]]:
    """Compute 4 corners of an AprilTag given center, surface normal, and size.

    Corners are ordered: top-left, top-right, bottom-right, bottom-left
    when viewed from the front (along the negative normal direction).
    """
    n = np.array(normal, dtype=np.float64)
    n = n / np.linalg.norm(n)
    c = np.array(center, dtype=np.float64)

    # Find two orthogonal vectors in the tag plane
    # Pick a reference vector not parallel to normal
    ref = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(n, ref)) > 0.9:
        ref = np.array([0.0, 1.0, 0.0])

    u = np.cross(n, ref)
    u = u / np.linalg.norm(u)
    v = np.cross(n, u)
    v = v / np.linalg.norm(v)

    half = size_mm / 2.0
    corners = [
        (c - half * u + half * v).tolist(),  # top-left
        (c + half * u + half * v).tolist(),  # top-right
        (c + half * u - half * v).tolist(),  # bottom-right
        (c - half * u - half * v).tolist(),  # bottom-left
    ]
    return corners


def save_fork_geometry(geometry: ForkGeometry) -> None:
    """Save fork geometry to JSON file."""
    os.makedirs(os.path.dirname(FORK_GEOMETRY_PATH), exist_ok=True)
    with open(FORK_GEOMETRY_PATH, "w") as f:
        json.dump(geometry.model_dump(), f, indent=2)
    logger.info("Saved fork geometry to %s", FORK_GEOMETRY_PATH)


def load_fork_geometry() -> ForkGeometry | None:
    """Load fork geometry from JSON file, or None if not configured."""
    if not os.path.exists(FORK_GEOMETRY_PATH):
        return None
    try:
        with open(FORK_GEOMETRY_PATH) as f:
            data = json.load(f)
        return ForkGeometry(**data)
    except Exception as e:
        logger.warning("Failed to load fork geometry: %s", e)
        return None


def save_fork_stl(data: bytes) -> None:
    """Save fork STL bytes to disk."""
    os.makedirs(os.path.dirname(FORK_STL_PATH), exist_ok=True)
    with open(FORK_STL_PATH, "wb") as f:
        f.write(data)
    logger.info("Saved fork STL to %s (%d bytes)", FORK_STL_PATH, len(data))


def load_fork_stl() -> bytes | None:
    """Load fork STL bytes from disk, or None if not saved."""
    if not os.path.exists(FORK_STL_PATH):
        return None
    try:
        with open(FORK_STL_PATH, "rb") as f:
            return f.read()
    except Exception as e:
        logger.warning("Failed to load fork STL: %s", e)
        return None
