# Feature Specification: Face-to-Scan Dental Alignment

**Feature Branch**: `001-face-scan-alignment`
**Created**: 2026-02-06
**Status**: Draft
**Input**: User description: "web app capture face photo from different devices android apple windows and analysis it to get different lines like interpupillary line frankfort plane pt will wear bit fork with marker will be used to align face analysis to intra oral scan file and then will output file to be used with dental cad software"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Capture & Analyze Face Photo (Priority: P1)

A dental professional opens the web app on any device (Android phone,
iPhone, iPad, or Windows desktop) and captures or uploads a set of
patient photos: one frontal photo and one or more side/profile photos,
all taken while the patient wears a bite fork with 2 external
fiducial markers visible outside the mouth. From the frontal photo
the system detects the interpupillary line
(horizontal reference connecting both pupil centers). From the side
photos the system detects lateral landmarks to compute the Frankfort
horizontal plane (from porion to orbitale), the ala-tragus line
(Camper's plane, from the ala of the nose to the tragus of the ear
for occlusal plane determination), and the canthus-tragus line (from
the outer canthus of the eye to the tragus of the ear). The system
also detects the 2 external markers on the bite fork across all
photos. These external markers establish the spatial relationship
between the facial reference lines and the fork. The bite fork also
has 4 intra-oral markers (inside the mouth) that are captured by
the intra-oral scanner to link the fork to the dental scan. The
system displays all detected reference lines and external marker
positions overlaid on each photo for visual confirmation.

**Why this priority**: Without face analysis and landmark detection,
no downstream alignment or export is possible. This is the
foundational capability the entire workflow depends on.

**Independent Test**: Can be fully tested by uploading a sample frontal
photo and side photo(s) with visible external bite fork markers and
verifying
that the interpupillary line (from frontal), Frankfort plane,
ala-tragus line, canthus-tragus line (from side photos), and marker
positions are correctly detected and displayed on each photo.

**Acceptance Scenarios**:

1. **Given** a dental professional with a frontal photo and side
   photo(s) of a patient wearing a bite fork with markers, **When**
   they upload the photos to the web app, **Then** the system
   detects the interpupillary line from the frontal photo, the
   Frankfort plane, ala-tragus line, and canthus-tragus line from
   the side photos, and both external markers across all photos,
   displaying results overlaid on each image.
2. **Given** a dental professional using an Android, iOS, or
   Windows device, **When** they access the web app and use the
   camera capture option, **Then** the app activates the device
   camera with an interactive guidance overlay (face framing, ear
   visibility, marker visibility, lighting indicator), and once
   the user captures the photo, proceeds to analysis.
3. **Given** an uploaded photo where the face or markers are not
   clearly visible, **When** analysis completes, **Then** the
   system displays a warning indicating which landmarks or markers
   could not be detected and suggests retaking the photo.

---

### User Story 2 - Align Face Analysis to Intra-Oral Scan (Priority: P2)

After face analysis is complete, the dental professional uploads an
intra-oral scan file (STL format). The scan was captured with the
bite fork in the patient's mouth, so the STL contains the 4
intra-oral markers on the fork. The system uses the 2 external
markers (detected in the face photos) to orient the facial reference
lines relative to the fork, and uses the 4 intra-oral markers
(present in the STL) to establish correspondence between the fork
and the scan coordinate system. This creates the alignment chain:
facial landmarks → external markers → fork → intra-oral markers →
scan. The system computes the 3D alignment that maps the facial
reference planes (interpupillary line, Frankfort plane, ala-tragus
line, canthus-tragus line) onto the scan's coordinate system. The
professional can preview the alignment result to verify correctness
before proceeding.

**Why this priority**: Alignment is the core value proposition that
bridges facial aesthetics with dental restorations. It depends on
User Story 1 but delivers the key differentiating functionality.

**Independent Test**: Can be tested by uploading a pre-analyzed face
photo result and an STL scan file, then verifying the alignment
preview shows correct spatial orientation of facial planes relative
to the dental arch.

**Acceptance Scenarios**:

1. **Given** a completed face analysis with detected landmarks and
   markers, **When** the professional uploads an STL intra-oral
   scan file, **Then** the system computes and displays an
   alignment preview showing facial reference planes mapped onto
   the scan coordinate system.
2. **Given** an alignment preview is displayed, **When** the
   professional reviews it and confirms it looks correct, **Then**
   the system marks the alignment as approved and enables export.
3. **Given** the uploaded scan file is corrupted or in an
   unsupported format, **When** the upload completes, **Then** the
   system displays a clear error message identifying the issue.

---

### User Story 3 - Export for Dental CAD Software (Priority: P3)

Once alignment is approved, the dental professional exports the
result as a file that can be imported into dental CAD software
(e.g., exocad, 3Shape). The export includes the aligned facial
reference planes, marker positions, and the spatial transformation
data. The professional downloads the file and imports it into their
CAD workflow to guide prosthetic design with facial aesthetic
alignment.

**Why this priority**: Export is the final delivery step. Without
it, the analysis and alignment have no practical use. It depends
on both prior stories but is the simplest to implement once
alignment data exists.

**Independent Test**: Can be tested by using a pre-computed
alignment result and verifying the exported file can be opened in
dental CAD software and contains the correct reference planes and
transformation data.

**Acceptance Scenarios**:

1. **Given** an approved alignment result, **When** the professional
   clicks export, **Then** the system generates a downloadable
   package containing the aligned STL, a JSON metadata file with
   transformation and landmark data, and the annotated face photo.
2. **Given** an exported file, **When** the professional imports it
   into dental CAD software, **Then** the CAD software correctly
   interprets the facial reference planes and alignment data.
3. **Given** the professional wants to re-export with adjustments,
   **When** they modify alignment parameters and re-export, **Then**
   a new file is generated reflecting the updated alignment.

---

### Edge Cases

- What happens when the patient's face is partially occluded (e.g.,
  hair covering one eye)? The system MUST report which specific
  landmarks could not be detected and allow partial results with
  warnings.
- What happens when one of the 2 external markers is not visible in
  the photo? The system MUST detect both external markers for
  alignment and report an error if either is missing or occluded.
- What happens when some of the 4 intra-oral markers are missing
  from the STL scan? The system MUST detect at least 3 of 4
  intra-oral markers in the scan for alignment and report an error
  if fewer are found.
- What happens when the photo is taken at an extreme angle (not
  frontal)? The system MUST validate approximate frontality and warn
  if the face angle exceeds 15 degrees from frontal.
- What happens when the intra-oral scan file is very large (>100 MB)?
  The system MUST display upload progress and handle the file without
  browser crashes or timeouts.
- What happens when two faces are detected in the photo? The system
  MUST prompt the user to select which face to analyze.
- What happens when the bite fork is upside down or rotated? The
  marker detection MUST be orientation-invariant and correctly
  identify marker positions regardless of rotation.
- What happens when the tragus or ear area is occluded by hair?
  The system MUST warn that ala-tragus and canthus-tragus lines
  cannot be computed and indicate which side is affected, since
  these landmarks require ear visibility.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow users to upload face photos in JPEG,
  PNG, or WebP format (max 10 MB per image). A session requires one
  frontal photo and at least one side/profile photo.
- **FR-002**: System MUST allow users to capture photos directly from
  the device camera (front or rear) on Android, iOS, and Windows.
  The capture flow MUST guide the user through frontal then side
  photo steps.
- **FR-003**: System MUST detect facial landmarks from the frontal
  photo sufficient to compute the interpupillary line (connecting
  both pupil centers).
- **FR-004**: System MUST detect facial landmarks from side/profile
  photo(s) sufficient to compute the Frankfort horizontal plane
  (porion to orbitale).
- **FR-015**: System MUST detect facial landmarks from side/profile
  photo(s) sufficient to compute the ala-tragus line (Camper's
  plane, from the ala of the nose to the tragus of the ear) for
  occlusal plane reference.
- **FR-016**: System MUST detect facial landmarks from side/profile
  photo(s) sufficient to compute the canthus-tragus line (from the
  outer canthus of the eye to the tragus of the ear) for occlusal
  plane reference.
- **FR-005**: System MUST detect the 2 external fiducial markers on
  the bite fork (outside the mouth) in face photos and compute
  their 2D positions in each image.
- **FR-006**: System MUST display detected reference lines and marker
  positions overlaid on the original photo for visual confirmation.
- **FR-007**: System MUST accept intra-oral scan files in STL format
  where the scan was captured with the bite fork in the patient's
  mouth (STL contains the fork body and 4 intra-oral markers).
- **FR-018**: System MUST detect and localize the 4 intra-oral
  markers within the uploaded STL scan geometry.
- **FR-008**: System MUST compute a spatial alignment using the
  dual-marker chain: 2 external markers (from face photos) orient
  facial reference lines to the fork, and 4 intra-oral markers
  (from the STL) link the fork to the scan coordinate system.
- **FR-009**: System MUST provide an alignment preview before export
  so the professional can verify correctness.
- **FR-010**: System MUST generate a neutral export package
  containing: (a) the aligned STL file with reference planes
  applied, (b) a JSON metadata file with transformation matrices,
  landmarks, markers, and confidence scores, and (c) the annotated
  face photo with analysis overlay.
- **FR-011**: System MUST work responsively across desktop browsers
  (Windows/macOS) and mobile browsers (Android/iOS).
- **FR-012**: System MUST display confidence scores for each detected
  landmark and marker.
- **FR-013**: System MUST allow the professional to manually adjust
  landmark positions if automatic detection is inaccurate.
- **FR-014**: System MUST NOT persist uploaded face photos or scan
  files beyond the active session unless the user explicitly opts
  in (per constitution Privacy-First principle).
- **FR-017**: When using live camera capture, the system MUST display
  an interactive guidance overlay showing a face framing outline,
  ear visibility reminder (required for ala-tragus and
  canthus-tragus lines), bite fork marker visibility check, and
  lighting quality indicator to help the user take an optimal photo.
- **FR-019**: Before any analysis processing begins, the system MUST
  display a consent disclosure informing the user what analysis will
  be performed, what data is collected, and how results are handled.
  The user MUST explicitly acknowledge this disclosure before the
  "Analyze" action becomes available (per constitution Principle II).

### Key Entities

- **Face Analysis Session**: Represents one complete workflow from
  photo upload through export. Contains the uploaded photos (one
  frontal + one or more side/profile), detected landmarks per photo,
  marker positions, computed reference lines, and analysis metadata
  (confidence scores, timestamps, device info).
- **Facial Landmark Set**: Collection of detected facial points
  including pupil centers, porion points, orbitale points, ala
  (nose wing) points, tragus points, and outer canthus points.
  These landmarks are used to compute the four reference lines
  (interpupillary, Frankfort, ala-tragus, canthus-tragus). Each
  landmark has a position and confidence score.
- **External Marker Set**: The 2 fiducial markers attached to the
  bite fork outside the mouth, visible in face photos. These orient
  facial reference lines relative to the fork. Both markers MUST be
  detected in the photos for alignment. Each marker has an ID, 2D
  image position, and confidence score.
- **Intra-Oral Marker Set**: The 4 fiducial markers on the bite
  fork inside the mouth, captured by the intra-oral scanner and
  present in the STL geometry. These link the fork to the scan
  coordinate system. Minimum 3 of 4 markers MUST be detected in
  the STL for alignment. Each marker has an ID, 3D position, and
  confidence score.
- **Intra-Oral Scan**: The uploaded 3D dental scan file (STL) taken
  with the bite fork in the patient's mouth, so the scan contains
  both the dental arch and the bite fork geometry. Has associated
  metadata (file size, vertex count, coordinate system).
- **Alignment Result**: The computed spatial transformation mapping
  facial reference planes to the scan coordinate system. Includes
  the transformation matrix, aligned reference planes, and quality
  metrics.
- **Export File**: The downloadable output package in a neutral,
  CAD-agnostic format containing three artifacts: (1) the aligned
  STL scan file with facial reference planes applied to its
  coordinate system, (2) a JSON metadata file with transformation
  matrices, landmark positions, marker positions, reference plane
  definitions, and confidence scores, and (3) the annotated face
  photo with detected landmarks, reference lines, and marker
  positions overlaid. This neutral format allows import into any
  dental CAD software (exocad, 3Shape, or others) that accepts
  STL + spatial reference data.

## Clarifications

### Session 2026-02-06

- Q: How does the system establish correspondence between photo markers and STL geometry? → A: The intra-oral scan is taken with the bite fork in place, so the STL contains the fork geometry. The system matches photo markers to corresponding geometric features in the STL.
- Q: How many markers does the bite fork have and what is their arrangement? → A: Two distinct sets: 2 external markers outside the mouth (visible in face photos, for face-to-fork orientation) and 4 intra-oral markers inside the mouth (captured by IOS scanner, for fork-to-scan alignment).
- Q: What is the expected concurrent usage scale? → A: Small clinic, 1-10 concurrent users (shared tool within a practice).
- Q: Should the system provide photo capture guidance to improve detection success? → A: Interactive guidance overlay during camera capture (framing hints, lighting check, ear visibility reminder).
- Q: Single photo or multiple photos per session? → A: Single frontal photo plus side/profile photos in one session. Side photos improve visibility of lateral landmarks (tragus, ala-tragus line, canthus-tragus line).

## Assumptions

- **Fiducial markers**: The bite fork has two distinct marker sets:
  (1) 2 external markers attached outside the mouth, visible in
  face photos, used for face-to-fork orientation; (2) 4 intra-oral
  markers inside the mouth, captured by the intra-oral scanner,
  used for fork-to-scan alignment. All markers are high-contrast
  fiducial targets (e.g., ArUco-style or circular coded targets)
  with known, consistent patterns and dimensions.
- **Single patient per session**: Each analysis session involves one
  patient. Multi-patient batch processing is out of scope.
- **Intra-oral scan format**: STL (stereolithography) is the primary
  scan format. Other formats (PLY, OBJ) are out of scope for MVP.
- **No user accounts for MVP**: The system operates as a session-based
  tool without requiring user registration or login. Authentication
  may be added in a future iteration.
- **Small clinic scale**: Designed for 1-10 concurrent users within
  a single dental practice or lab. Multi-clinic SaaS scaling is out
  of scope for MVP.
- **Multi-photo session**: Each session requires one approximately
  frontal photo (for interpupillary line) and at least one side/
  profile photo (for Frankfort plane, ala-tragus, canthus-tragus).
  The frontal photo detects horizontal symmetry landmarks; side
  photos detect lateral landmarks where the tragus and ear are
  clearly visible.
- **Bite fork in scan**: The intra-oral scan is always captured with
  the bite fork in the patient's mouth so the 4 intra-oral markers
  are present in the STL. The alignment chain is: facial landmarks
  → 2 external markers → fork → 4 intra-oral markers → scan.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A dental professional can complete the full workflow
  (photo upload, analysis, scan alignment, export) in under 5
  minutes on a standard internet connection.
- **SC-002**: Facial landmark detection (interpupillary line from
  frontal; Frankfort plane, ala-tragus line, and canthus-tragus
  line from side photos) achieves correct results on 90% of
  well-lit photo sets with visible landmarks.
- **SC-003**: External marker detection identifies both external
  markers in face photos with at least 95% accuracy, and intra-oral
  marker detection identifies at least 3 of 4 markers in the STL
  scan with at least 95% accuracy.
- **SC-004**: The exported alignment file imports successfully into
  the target dental CAD software without manual data conversion.
- **SC-005**: The web app is usable on the three target platforms
  (Android Chrome, iOS Safari, Windows Chrome/Edge) with identical
  core functionality.
- **SC-006**: 80% of dental professionals can complete the workflow
  on their first attempt without external assistance.
- **SC-007**: Face photo analysis (landmark + marker detection)
  completes and displays results within 10 seconds of upload.
- **SC-008**: The system supports up to 10 concurrent users
  (small clinic scale) without degradation in analysis or
  export performance.
