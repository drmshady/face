"""Create fork geometry JSON from a fork STL file.

Auto-detects marker spheres from the mesh. AprilTag positions can be
provided via command-line args or interactively.

Usage:
    python backend/scripts/create_fork_geometry.py fork.stl
    python backend/scripts/create_fork_geometry.py fork.stl --output my_fork.json
    python backend/scripts/create_fork_geometry.py fork.stl --tag-size 10 --tag1 "-15,5,0" --tag2 "15,5,0"
"""

import argparse
import io
import json
import sys
from pathlib import Path

import numpy as np
import trimesh


# ---------------------------------------------------------------------------
# Sphere detection (reuses logic from stl_processing service)
# ---------------------------------------------------------------------------

def fit_sphere(points: np.ndarray) -> tuple[np.ndarray | None, float, float]:
    """Least-squares sphere fit. Returns (center, radius, residual)."""
    n = len(points)
    if n < 4:
        return None, 0.0, float("inf")

    A = np.zeros((n, 4))
    A[:, 0] = 2 * points[:, 0]
    A[:, 1] = 2 * points[:, 1]
    A[:, 2] = 2 * points[:, 2]
    A[:, 3] = 1.0

    b = np.sum(points ** 2, axis=1)
    result, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
    center = result[:3]
    radius = np.sqrt(result[3] + np.sum(center ** 2))

    distances = np.linalg.norm(points - center, axis=1)
    residual = np.sqrt(np.mean((distances - radius) ** 2))
    return center, float(radius), float(residual)


def detect_spheres(
    mesh: trimesh.Trimesh,
    min_radius: float = 0.5,
    max_radius: float = 5.0,
) -> list[dict]:
    """Detect all spherical features in a mesh within a radius range."""
    from sklearn.cluster import DBSCAN

    vertices = mesh.vertices
    if len(vertices) < 20:
        return []

    # Compute curvature at multiple scales to catch different sphere sizes
    mid_radius = (min_radius + max_radius) / 2
    try:
        curvature = trimesh.curvature.discrete_gaussian_curvature_measure(
            mesh, vertices, radius=mid_radius * 2
        )
    except Exception:
        print("  Warning: curvature computation failed")
        return []

    # Filter by curvature range matching spheres in [min_radius, max_radius]
    K_min = 1.0 / (max_radius ** 2) * 0.3
    K_max = 1.0 / (min_radius ** 2) * 3.0
    mask = (curvature > K_min) & (curvature < K_max)
    indices = np.where(mask)[0]

    if len(indices) < 4:
        print(f"  Only {len(indices)} high-curvature vertices found")
        return []

    high_pts = vertices[indices]
    print(f"  Found {len(high_pts)} high-curvature vertices")

    # Cluster
    clustering = DBSCAN(eps=max_radius * 2, min_samples=3).fit(high_pts)
    labels = clustering.labels_
    unique_labels = sorted(set(labels) - {-1})
    print(f"  Found {len(unique_labels)} clusters")

    # Fit spheres
    spheres = []
    for label in unique_labels:
        cluster_pts = high_pts[labels == label]
        if len(cluster_pts) < 4:
            continue

        center, radius, residual = fit_sphere(cluster_pts)
        if center is None:
            continue

        if radius < min_radius or radius > max_radius:
            continue

        spheres.append({
            "center": center.tolist(),
            "radius": float(radius),
            "residual": float(residual),
            "num_points": len(cluster_pts),
        })

    # Sort by residual (best fit first)
    spheres.sort(key=lambda s: s["residual"])
    return spheres


# ---------------------------------------------------------------------------
# Flat surface detection (for identifying AprilTag mounting planes)
# ---------------------------------------------------------------------------

def detect_flat_surfaces(mesh: trimesh.Trimesh, area_threshold: float = 50.0) -> list[dict]:
    """Find large flat surfaces that could be AprilTag mounts.

    Returns list of {center, normal, area} for each flat region.
    """
    face_normals = mesh.face_normals
    face_areas = mesh.area_faces

    from sklearn.cluster import DBSCAN

    # Cluster faces by normal direction
    clustering = DBSCAN(eps=0.05, min_samples=5).fit(face_normals)
    labels = clustering.labels_
    unique_labels = sorted(set(labels) - {-1})

    surfaces = []
    for label in unique_labels:
        face_mask = labels == label
        cluster_area = float(np.sum(face_areas[face_mask]))
        if cluster_area < area_threshold:
            continue

        # Compute centroid of these faces
        face_indices = np.where(face_mask)[0]
        face_centroids = mesh.triangles_center[face_indices]
        center = np.mean(face_centroids, axis=0)
        normal = np.mean(face_normals[face_indices], axis=0)
        normal = normal / np.linalg.norm(normal)

        surfaces.append({
            "center": center.tolist(),
            "normal": normal.tolist(),
            "area_mm2": cluster_area,
            "num_faces": int(np.sum(face_mask)),
        })

    surfaces.sort(key=lambda s: s["area_mm2"], reverse=True)
    return surfaces


# ---------------------------------------------------------------------------
# AprilTag corner computation
# ---------------------------------------------------------------------------

def compute_tag_corners(center: list[float], size_mm: float, normal: list[float]) -> list[list[float]]:
    """Compute 4 corners of an AprilTag given center, size, and face normal."""
    half = size_mm / 2.0
    n = np.array(normal)
    n = n / np.linalg.norm(n)

    # Find two orthogonal vectors in the tag plane
    if abs(n[2]) < 0.9:
        up = np.array([0.0, 0.0, 1.0])
    else:
        up = np.array([0.0, 1.0, 0.0])

    u = np.cross(n, up)
    u = u / np.linalg.norm(u)
    v = np.cross(n, u)
    v = v / np.linalg.norm(v)

    c = np.array(center)
    return [
        (c - half * u - half * v).tolist(),
        (c + half * u - half * v).tolist(),
        (c + half * u + half * v).tolist(),
        (c - half * u + half * v).tolist(),
    ]


# ---------------------------------------------------------------------------
# Interactive helpers
# ---------------------------------------------------------------------------

def ask_float(prompt: str, default: float | None = None) -> float:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"  {prompt}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        try:
            return float(raw)
        except ValueError:
            print("    Invalid number, try again.")


def ask_xyz(label: str) -> list[float]:
    print(f"  {label} (X, Y, Z in mm):")
    x = ask_float("    X")
    y = ask_float("    Y")
    z = ask_float("    Z")
    return [x, y, z]


def parse_xyz(s: str) -> list[float]:
    """Parse 'x,y,z' string into [x, y, z]."""
    parts = s.split(",")
    if len(parts) != 3:
        raise ValueError(f"Expected 3 comma-separated values, got: {s}")
    return [float(p.strip()) for p in parts]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create fork geometry JSON from STL file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s fork.stl
  %(prog)s fork.stl --tag-size 10 --tag1 "-15,5,0" --tag2 "15,5,0"
  %(prog)s fork.stl --sphere-min-r 1.0 --sphere-max-r 3.0
        """,
    )
    parser.add_argument("stl_file", help="Path to fork STL file")
    parser.add_argument("-o", "--output", default="backend/fork_geometry.json")
    parser.add_argument("--tag-size", type=float, default=None, help="AprilTag side length (mm)")
    parser.add_argument("--tag1", type=str, default=None, help="Tag 1 center as 'x,y,z' (mm)")
    parser.add_argument("--tag2", type=str, default=None, help="Tag 2 center as 'x,y,z' (mm)")
    parser.add_argument("--tag-normal", type=str, default=None, help="Tag face normal as 'x,y,z'")
    parser.add_argument("--sphere-min-r", type=float, default=0.5, help="Min sphere radius (mm)")
    parser.add_argument("--sphere-max-r", type=float, default=5.0, help="Max sphere radius (mm)")
    args = parser.parse_args()

    stl_path = Path(args.stl_file)
    if not stl_path.exists():
        print(f"Error: STL file not found: {stl_path}")
        sys.exit(1)

    # --- Load STL ---
    print("=" * 60)
    print("  Fork Geometry Extractor")
    print("=" * 60)
    print()
    print(f"  Loading: {stl_path}")

    file_bytes = stl_path.read_bytes()
    mesh = trimesh.load(io.BytesIO(file_bytes), file_type="stl", force="mesh")

    if not isinstance(mesh, trimesh.Trimesh):
        print("Error: Could not load mesh from STL")
        sys.exit(1)

    print(f"  Vertices: {len(mesh.vertices):,}")
    print(f"  Faces:    {len(mesh.faces):,}")
    bounds = mesh.bounds
    dims = bounds[1] - bounds[0]
    print(f"  Bounds:   X=[{bounds[0][0]:.1f}, {bounds[1][0]:.1f}] "
          f"Y=[{bounds[0][1]:.1f}, {bounds[1][1]:.1f}] "
          f"Z=[{bounds[0][2]:.1f}, {bounds[1][2]:.1f}]")
    print(f"  Size:     {dims[0]:.1f} x {dims[1]:.1f} x {dims[2]:.1f} mm")
    print()

    # --- Detect spheres ---
    print("-" * 60)
    print("  DETECTING MARKER SPHERES")
    print("-" * 60)
    print()

    spheres = detect_spheres(mesh, min_radius=args.sphere_min_r, max_radius=args.sphere_max_r)

    if spheres:
        print(f"\n  Detected {len(spheres)} sphere(s):\n")
        for i, s in enumerate(spheres):
            c = s["center"]
            print(f"    Sphere {i}: center=({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f})  "
                  f"r={s['radius']:.3f}mm  residual={s['residual']:.4f}  "
                  f"pts={s['num_points']}")
    else:
        print("\n  No spheres detected. You may need to adjust --sphere-min-r / --sphere-max-r")

    # Let user select which spheres are markers
    markers = []
    if spheres:
        print()
        use_all = input(f"  Use all {len(spheres)} detected spheres as markers? [Y/n]: ").strip().lower()
        if use_all in ("", "y", "yes"):
            for i, s in enumerate(spheres):
                markers.append({
                    "marker_id": i,
                    "radius_mm": round(s["radius"], 3),
                    "center_mm": [round(v, 3) for v in s["center"]],
                })
        else:
            print("  Enter sphere indices to use (comma-separated), e.g. '0,1,2,3':")
            indices_str = input("  Indices: ").strip()
            for idx_str in indices_str.split(","):
                idx = int(idx_str.strip())
                if 0 <= idx < len(spheres):
                    s = spheres[idx]
                    markers.append({
                        "marker_id": len(markers),
                        "radius_mm": round(s["radius"], 3),
                        "center_mm": [round(v, 3) for v in s["center"]],
                    })

    if not markers:
        print("\n  No markers selected. Enter positions manually:")
        num = int(ask_float("  Number of marker spheres", 4.0))
        radius = ask_float("  Sphere radius (mm)", 1.5)
        for i in range(num):
            center = ask_xyz(f"  Sphere {i} center")
            markers.append({"marker_id": i, "radius_mm": radius, "center_mm": center})

    # --- Detect flat surfaces for AprilTag candidates ---
    print()
    print("-" * 60)
    print("  DETECTING FLAT SURFACES (AprilTag candidates)")
    print("-" * 60)
    print()

    flat_surfaces = detect_flat_surfaces(mesh)
    if flat_surfaces:
        print(f"  Found {len(flat_surfaces)} flat surface(s):\n")
        for i, s in enumerate(flat_surfaces[:10]):
            c = s["center"]
            n = s["normal"]
            print(f"    Surface {i}: center=({c[0]:.1f}, {c[1]:.1f}, {c[2]:.1f})  "
                  f"normal=({n[0]:.2f}, {n[1]:.2f}, {n[2]:.2f})  "
                  f"area={s['area_mm2']:.1f}mm2")
    else:
        print("  No large flat surfaces found.")

    # --- AprilTag positions ---
    print()
    print("-" * 60)
    print("  APRILTAG POSITIONS")
    print("-" * 60)
    print()
    print("  AprilTags are printed patterns — their exact positions")
    print("  must be specified (they can't be detected from mesh geometry).")
    print()

    # Tag size
    if args.tag_size is not None:
        tag_size = args.tag_size
    else:
        tag_size = ask_float("AprilTag side length (mm)", 10.0)

    # Tag normal
    if args.tag_normal is not None:
        tag_normal = parse_xyz(args.tag_normal)
    elif flat_surfaces:
        print(f"\n  Suggested normal from largest flat surface: "
              f"({flat_surfaces[0]['normal'][0]:.2f}, "
              f"{flat_surfaces[0]['normal'][1]:.2f}, "
              f"{flat_surfaces[0]['normal'][2]:.2f})")
        use_suggested = input("  Use this normal? [Y/n]: ").strip().lower()
        if use_suggested in ("", "y", "yes"):
            tag_normal = [round(v, 4) for v in flat_surfaces[0]["normal"]]
        else:
            tag_normal = parse_xyz(input("  Tag normal (x,y,z): ").strip())
    else:
        tag_normal = [0.0, 0.0, 1.0]
        print(f"  Using default normal: {tag_normal}")

    tags = []
    for i in range(2):
        if i == 0 and args.tag1 is not None:
            center = parse_xyz(args.tag1)
        elif i == 1 and args.tag2 is not None:
            center = parse_xyz(args.tag2)
        else:
            if flat_surfaces and len(flat_surfaces) > i:
                suggested = flat_surfaces[i]["center"]
                print(f"\n  Flat surface {i} center: ({suggested[0]:.1f}, {suggested[1]:.1f}, {suggested[2]:.1f})")
            print(f"\n  --- AprilTag {i + 1} ---")
            tag_id = int(ask_float("  Tag ID", float(i)))
            center = ask_xyz(f"  Tag {i + 1} center position")
            tags.append({
                "tag_id": tag_id,
                "size_mm": tag_size,
                "center_mm": [round(v, 3) for v in center],
                "normal": [round(v, 4) for v in tag_normal],
                "corners_mm": compute_tag_corners(center, tag_size, tag_normal),
            })
            continue

        tags.append({
            "tag_id": i,
            "size_mm": tag_size,
            "center_mm": [round(v, 3) for v in center],
            "normal": [round(v, 4) for v in tag_normal],
            "corners_mm": compute_tag_corners(center, tag_size, tag_normal),
        })

    # --- Build & save ---
    geometry = {
        "description": "Fork geometry for face-scan alignment calibration",
        "source_stl": stl_path.name,
        "mesh_stats": {
            "vertices": len(mesh.vertices),
            "faces": len(mesh.faces),
            "bounds_mm": {
                "min": [round(v, 2) for v in bounds[0].tolist()],
                "max": [round(v, 2) for v in bounds[1].tolist()],
            },
        },
        "coordinate_system": {
            "units": "mm",
            "note": "Coordinates are in the STL file's native coordinate system",
        },
        "apriltag_family": "tag36h11",
        "apriltags": tags,
        "intraoral_markers": markers,
    }

    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print()
    print(f"  Source: {stl_path.name}")
    print(f"  AprilTags: {len(tags)} (size={tag_size}mm)")
    for t in tags:
        print(f"    Tag {t['tag_id']}: center={t['center_mm']}")
    print(f"  Markers: {len(markers)}")
    for m in markers:
        print(f"    Marker {m['marker_id']}: center={m['center_mm']}  r={m['radius_mm']}mm")
    print()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(geometry, f, indent=2)

    print(f"  Saved to: {out_path.resolve()}")


if __name__ == "__main__":
    main()
