# Research: Face-to-Scan Dental Alignment

**Feature Branch**: `001-face-scan-alignment`
**Date**: 2026-02-06
**Input**: spec.md unknowns and technical feasibility questions

## Research Area 1: Facial Landmark Detection

### Question

What libraries can detect the required dental facial landmarks (pupil
centers, outer canthus, ala of nose, tragus, porion, orbitale) from
photographs? What are their coverage gaps?

### Findings

#### MediaPipe Face Landmarker (478 Landmarks) — RECOMMENDED

MediaPipe detects 468 facial surface landmarks + 10 iris landmarks.
It runs in-browser via WASM or server-side via Python.

**Landmark coverage for this project:**

| Dental Landmark | MediaPipe Index | Coverage | Notes |
|----------------|----------------|----------|-------|
| Pupil centers | 468 (left), 473 (right) | Excellent | Iris center landmarks, direct use |
| Outer canthus | 33 (right), 263 (left) | Excellent | Lateral eye corners |
| Ala of nose | 219 (right), 439 (left) | Good | Nostril wing outermost; alternatives: 48/278, 64/294 |
| Tragus | **None** | None | Ear landmarks not in MediaPipe mesh |
| Porion | **None** | None | Bony landmark, hidden inside ear canal |
| Orbitale | ~111/116 (R), ~340/345 (L) | Poor | Soft-tissue approximation only, 3-8mm error from true bony orbitale |

**Key gap**: MediaPipe's mesh terminates at the pre-auricular area.
The tragus, porion, and orbitale are NOT detected. This means 3 of 4
reference lines (Frankfort plane, ala-tragus, canthus-tragus) cannot
be fully automated with MediaPipe alone.

#### dlib (68 Landmarks) — NOT RECOMMENDED

dlib provides fewer landmarks (68 vs 478), no iris/pupil detection
(must estimate from eye corners), same ear landmark gap, poor profile
view performance, and no browser/WASM support. Strictly inferior to
MediaPipe for this use case.

#### Specialized Dental/Cephalometric Models

Traditional cephalometric landmark models (CephNN, CephaNet, WebCeph)
work on X-ray images, not photographs. No off-the-shelf model exists
that detects all required dental landmarks from photographs. Dental
software (DSD, exocad Smile Creator) relies on manual landmark
placement for ear-related points.

### Decision: Semi-Automatic Approach for MVP

**Tier 1 — Automated (MediaPipe):**
- Pupil centers → interpupillary line: fully automated
- Outer canthus → one endpoint of canthus-tragus line: automated
- Ala of nose → one endpoint of ala-tragus line: automated
- Soft-tissue orbitale proxy → one endpoint of Frankfort plane: automated with manual verification

**Tier 2 — Guided Manual Placement:**
- Tragus: user places on profile photo with anatomical guidance overlay
- Porion: derived as geometric offset (~4mm superior to tragus)
- Orbitale: auto-detected with mandatory manual verification

**Rationale**: This matches existing dental software UX (DSD, Smile
Design). FR-013 (manual landmark adjustment) becomes a first-class
feature, not a fallback.

**Future V2**: Train a custom ear landmark model from ~500-1000
annotated lateral face photos for full automation.

### Accuracy Expectations

| Landmark | Expected Error | Manual Adjustment Rate |
|----------|---------------|----------------------|
| Pupil centers | 0.5-1mm | 5-10% of cases |
| Outer canthus | 0.8-1.5mm | 10-15% |
| Ala of nose | 1-2mm | 15-20% |
| Soft-tissue orbitale | 3-8mm from bony | 60-80% |
| Tragus | N/A (manual) | 100% initially |
| Porion | N/A (derived) | 100% initially |

---

## Research Area 2: STL Marker Detection

### Question

How to detect 4 intra-oral fiducial markers (spheres of known radius)
within an STL dental scan?

### Findings

#### Library Comparison

| Library | Role | Strengths |
|---------|------|-----------|
| **trimesh** | Primary STL processing | Rich STL I/O, curvature estimation, connected components, sampling, lightweight, pip-installable |
| **Open3D** | RANSAC/ICP supplement | RANSAC primitive fitting, ICP registration, DBSCAN clustering, point cloud processing. Heavier (~200MB) |
| **numpy-stl** | Not recommended | Basic I/O only, no topology/curvature. Superseded by trimesh |
| **scipy.spatial** | KD-trees, spatial queries | Use alongside trimesh for fast nearest-neighbor |

#### Recommended Detection Pipeline

**Approach: Curvature-Based Segmentation + RANSAC Sphere Fitting**

1. **Load & preprocess**: `trimesh.load()` the STL, repair normals,
   remove degenerate faces
2. **Curvature estimation**: Compute Gaussian curvature at each vertex.
   Sphere of radius r has curvature 1/r². Filter vertices matching
   expected marker curvature
3. **Candidate clustering**: DBSCAN (scikit-learn or Open3D) to cluster
   high-curvature vertices spatially. Filter by expected cluster size
4. **Sphere fitting**: Least-squares or RANSAC sphere fit per cluster.
   Reject fits where radius deviates from known marker radius
5. **Validation**: Verify exactly 4 markers found, inter-marker
   distances match known fork geometry

**Alternative: ICP against fork CAD model** as fallback/validation if
a reference fork STL is available.

#### Dental STL File Characteristics

- Single arch: 5-30 MB binary STL, 200K-1.5M triangles
- Full mouth: 10-60 MB binary STL
- Resolution: 0.05-0.2mm triangle edge length
- Bite fork adds ~50K-200K triangles
- Processing time: 2-8 seconds total (load + curvature + RANSAC)
- Memory: ~100-200MB RAM for a 1M-triangle mesh with adjacency

#### Frontend 3D Rendering (Three.js)

Three.js handles dental STL rendering well:
- `STLLoader` parses binary/ASCII STL in-browser
- Renders 1-2M triangles at 30-60 FPS on modern hardware
- Marker overlay: colored `SphereGeometry` at detected 3D coordinates
- Plane overlay: semi-transparent `PlaneGeometry` oriented by normal
- Controls: `OrbitControls` for rotation/zoom/pan
- Optimization: convert to glTF+Draco on backend for smaller transfer
- Use Web Worker for loading to avoid UI thread blocking

---

## Research Area 3: Alignment Mathematics

### Question

How to compute the spatial transformation chain from face photos
through the bite fork to the STL scan coordinate system?

### Findings

#### The Alignment Chain

```
Face/Camera Frame  ──T1──>  Fork Frame  ──T2──>  STL/Scan Frame

T_face_to_scan = T2 * T1⁻¹
```

All transforms are 4x4 homogeneous matrices:
```
T = [ R  t ]    R = 3x3 rotation, t = 3x1 translation
    [ 0  1 ]
```

#### T1: Fork-to-Camera (PnP Problem)

**Problem**: Given 2D image positions of external markers and their
known 3D positions on the fork, find the fork's 3D pose relative to
the camera.

**Critical issue**: 2 markers provide only 4 equations for 6 unknowns
(3 rotation + 3 translation). The PnP problem requires minimum 4
points for a unique solution.

**Solutions to the 2-marker constraint:**

1. **ArUco markers** (RECOMMENDED): A single ArUco tag provides 4
   corner correspondences. Using 2 ArUco tags gives 8 correspondences
   — well overconstrained. OpenCV `cv2.aruco` module handles detection
   and PnP in one step.

2. **Face model augmentation**: Fit a 3D Morphable Model (MediaPipe's
   468-point mesh) to solve camera parameters first. Then use the 2
   markers to place the fork relative to the face, with the camera
   model providing the missing constraints.

3. **Multi-view geometry**: Using frontal + side photos allows
   triangulation of marker positions without PnP ambiguity.

**Camera intrinsics**: Required for PnP. Can be approximated from
EXIF focal length data or standard smartphone assumptions
(fx ≈ image_width * 1.0-1.2 for ~26-28mm equivalent lenses).

**PnP solver**: `cv2.solvePnP()` with EPnP initial + iterative LM
refinement. For ArUco: `cv2.aruco.estimatePoseSingleMarkers()`.

#### T2: Fork-to-Scan (Rigid Registration)

**Problem**: Given 4 intra-oral markers with known positions on fork
and measured positions in STL, find the rigid transformation.

**Solution**: Closed-form SVD-based registration (Procrustes):

1. Compute centroids of both point sets
2. Center the points
3. Compute cross-covariance matrix H = Σ q_fork * q_scan^T
4. SVD: H = U Σ V^T
5. Rotation: R = V * diag(1, 1, det(V*U^T)) * U^T
6. Translation: t = p̄_scan - R * p̄_fork

**4 markers is well-determined**: 3 non-collinear points minimum for
6 DOF rigid registration. 4 points provide redundancy for error
detection and least-squares fitting.

**No ICP needed**: Correspondences are known (marker 1→1, 2→2, etc.).
ICP is only for unknown correspondences. Optional ICP refinement
using surrounding fork geometry as validation.

#### 2D-to-3D Gap for Facial Landmarks

Facial landmarks in photos are 2D. To get 3D positions:

1. **MediaPipe Face Mesh**: Provides approximate 3D coordinates
   (468 landmarks with depth) — lightweight option
2. **3D Morphable Model** (FLAME/Basel): Full 3D face reconstruction
   from single image — more accurate
3. **Multi-view stereo**: Triangulate from frontal + lateral photos

**Recommendation**: Use MediaPipe's 3D landmark output for MVP.
The reference planes (Frankfort, ala-tragus, canthus-tragus) are
defined by direction vectors, not absolute 3D positions, so
approximate depth is acceptable.

#### Composing the Full Transform

```
1. Detect 2D facial landmarks + markers in photo (MediaPipe + ArUco)
2. Fit 3D face model → camera parameters + 3D face geometry
3. Solve PnP for fork pose using marker observations → T1
4. Extract 4 intra-oral markers from STL → 3D positions in scan frame
5. Solve rigid registration fork↔scan → T2
6. Compose: T_face_to_scan = T2 * T1⁻¹
7. Transform facial reference planes into scan coordinate system
```

#### Error Sources and Quality Metrics

**Reprojection error (PnP validation):**
```
error = (1/n) Σ ||p_observed - project(K, R, t, P_3D)||²
```
Acceptable: < 2 pixels. Use `cv2.projectPoints()`.

**Registration RMSD (fork-to-scan validation):**
```
RMSD = sqrt((1/n) Σ ||p_scan - (R * p_fork + t)||²)
```
Acceptable: < 0.5mm for clinical applications.

**Target Registration Error (TRE):**
Error at points distant from markers is larger than at markers:
```
TRE ≈ FRE * sqrt(1 + d²/σ²)
```
Markers should be spread widely (large bounding volume) and not
collinear.

#### Python Library Stack

| Library | Role |
|---------|------|
| `opencv-python` | PnP solving, ArUco detection, camera model, image processing |
| `numpy` | Matrix math, SVD, linear algebra |
| `scipy.spatial.transform` | Rotation representations, composing transforms |
| `mediapipe` | Face landmark detection (468+10 iris), 3D face mesh |
| `trimesh` | STL loading, mesh analysis, curvature |
| `open3d` | RANSAC sphere fitting, optional ICP refinement |

---

## Key Decisions from Research

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Face landmark library | MediaPipe | Best coverage (478 landmarks), browser+server, iris detection |
| Ear landmarks (MVP) | Semi-automatic (guided manual) | No model auto-detects tragus; matches dental software UX |
| External marker type | ArUco tags (recommended) | 4 corners per tag → well-constrained PnP; orientation-invariant |
| STL processing | trimesh + Open3D | trimesh for I/O/curvature, Open3D for RANSAC sphere fitting |
| Marker detection approach | Curvature + RANSAC sphere fitting | No template model required, works at arbitrary orientation |
| Fork-to-scan registration | SVD closed-form | Known correspondences, exact solution, fast |
| 3D frontend rendering | Three.js | Mature STL support, 1M+ triangle performance, rich ecosystem |
| Camera intrinsics | EXIF-based approximation | Sufficient for clinical accuracy without formal calibration |

## Open Risks

1. **2-marker PnP**: If user opts for simple circular markers instead
   of ArUco tags, PnP is underconstrained. Mitigation: strongly
   recommend ArUco; if simple markers, augment with face model pose.
2. **Soft-tissue Frankfort plane**: 3-8mm error vs true bony landmark.
   Accepted clinical practice for photographic analysis but should be
   documented as limitation.
3. **Profile photo ear visibility**: Hair or accessories may occlude
   the tragus. Mitigation: camera guidance overlay reminding user to
   ensure ear visibility.
