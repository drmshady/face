/** Frontend TypeScript types mirroring backend models per data-model.md (T014). */

// Enums

export type SessionStatus =
  | "created"
  | "photos_uploaded"
  | "analyzing"
  | "analysis_complete"
  | "scan_uploaded"
  | "aligning"
  | "alignment_complete"
  | "export_ready";

export type PhotoType = "frontal" | "side";

export type LandmarkType =
  | "left_pupil"
  | "right_pupil"
  | "left_outer_canthus"
  | "right_outer_canthus"
  | "left_ala"
  | "right_ala"
  | "left_tragus"
  | "right_tragus"
  | "left_porion"
  | "right_porion"
  | "left_orbitale"
  | "right_orbitale";

export type AlignmentQuality = "good" | "acceptable" | "poor";

// Shared types

export interface Point2D {
  x: number;
  y: number;
}

export interface Point3D {
  x: number;
  y: number;
  z: number;
}

export interface BoundingBox3D {
  min: Point3D;
  max: Point3D;
}

export interface Plane3D {
  point: Point3D;
  normal: Point3D;
}

// Session

export interface Session {
  session_id: string;
  status: SessionStatus;
  created_at: string;
  photos: UploadedPhoto[];
  has_scan: boolean;
  has_alignment: boolean;
  has_export: boolean;
}

export interface UploadedPhoto {
  photo_id: string;
  photo_type: PhotoType;
  original_filename: string;
  mime_type?: string;
  width: number;
  height: number;
  file_size_bytes?: number;
}

// Landmarks

export interface LandmarkPoint {
  x: number;
  y: number;
  z?: number;
  confidence: number;
  is_manual: boolean;
  mediapipe_index?: number;
}

export interface ReferenceLine {
  start_landmark: LandmarkType;
  end_landmark: LandmarkType;
  start_point: Point2D;
  end_point: Point2D;
  angle_degrees: number;
  confidence: number;
  warnings: string[];
}

// Markers

export interface ExternalMarker {
  marker_id: number;
  center: Point2D;
  corners: Point2D[];
  confidence: number;
  size_pixels: number;
}

export interface IntraOralMarker {
  marker_id: number;
  position: Point3D;
  fitted_radius: number;
  confidence: number;
  residual: number;
}

// Alignment

export interface TransformMatrix {
  matrix: number[][];
  rotation_euler_deg: number[];
  translation_mm: number[];
}

export interface ReferencePlanesInScan {
  interpupillary_plane?: Plane3D;
  frankfort_plane?: Plane3D;
  ala_tragus_plane?: Plane3D;
  canthus_tragus_plane?: Plane3D;
}

export interface Landmark3DInScan {
  name: string;
  point: Point3D;
  confidence: number;
}

export interface Landmark3DInFork {
  name: string;
  point: Point3D;
  confidence: number;
  depth_method?: string;
  depth_confidence?: number;
  triangulation_residual_px?: number;
}

export interface CameraPose {
  photo_id: string;
  rvec: number[];
  tvec: number[];
  reprojection_error_px: number;
  image_width: number;
  image_height: number;
  focal_length_mm?: number;
}

export interface ReferenceLine3D {
  start_point: Point3D;
  end_point: Point3D;
  start_landmark: string;
  end_landmark: string;
  length_mm: number;
  confidence: number;
  depth_method: string;
}

export interface ReferencePlane3D {
  point: Point3D;
  normal: Point3D;
  up_vector: Point3D;
  confidence: number;
  source_line: string;
}

export interface AprilTagInFork {
  tag_id: number;
  center: Point3D;
  corners: Point3D[];
  normal: Point3D;
  size_mm: number;
}

export interface LandmarkToTagRelation {
  landmark_name: string;
  tag_id: number;
  distance_mm: number;
  direction: Point3D;
  angle_from_tag_normal_deg: number;
}

export interface AlignmentResult {
  t_face_to_scan?: TransformMatrix;
  t2_fork_to_scan?: TransformMatrix;
  reprojection_error_px: number;
  registration_rmsd_mm?: number;
  quality: AlignmentQuality;
  reference_planes_in_scan?: ReferencePlanesInScan;
  landmarks_3d_in_scan?: Landmark3DInScan[];
  // New fields for 002-3d-landmark-registration
  landmarks_3d_in_fork?: Landmark3DInFork[];
  camera_poses?: CameraPose[];
  interpupillary_line_3d?: ReferenceLine3D;
  midline_plane_3d?: ReferencePlane3D;
  apriltags_in_fork?: AprilTagInFork[];
  landmark_to_tag_relations?: LandmarkToTagRelation[];
  triangulation_method?: string;
  scale_deviation_pct?: number;
  bundle_adjustment_residual?: number;
}

// Export

export interface ExportFile {
  session_id: string;
  export_ready: boolean;
  package_size_bytes: number;
  contents: string[];
}

// Fork calibration

export interface HexPostMarker3D {
  marker_id: number;
  center: Point3D;
  top_face_normal: Point3D;
  radius_mm: number;
  height_mm: number;
  confidence: number;
}

export interface AprilTagOnFork {
  tag_id: number;
  center_mm: Point3D;
  size_mm: number;
  normal: Point3D;
  corners_mm: number[][];
}

export interface ForkGeometry {
  apriltags: AprilTagOnFork[];
  intraoral_markers: HexPostMarker3D[];
  plate_normal: number[];
  created_at: string;
}

export interface ForkUploadResponse {
  markers: HexPostMarker3D[];
  plate_normal: number[];
  vertex_count: number;
  face_count: number;
}

// Error response

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}
