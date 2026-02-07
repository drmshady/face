/** Frontend API client per contracts/api.md (T015). */

import axios from "axios";
import type {
  AlignmentResult,
  ExportFile,
  ForkGeometry,
  ForkUploadResponse,
  HexPostMarker3D,
  LandmarkPoint,
  LandmarkType,
  PhotoType,
  ReferenceLine,
  Session,
  UploadedPhoto,
} from "../types";

const client = axios.create({
  baseURL: "/api/v1",
  withCredentials: true, // Send session cookie
});

// Session management

export async function createSession(): Promise<Session> {
  const { data } = await client.post<Session>("/sessions");
  return data;
}

export async function getSession(sessionId: string): Promise<Session> {
  const { data } = await client.get<Session>(`/sessions/${sessionId}`);
  return data;
}

// Photo upload & analysis

export async function uploadPhoto(
  sessionId: string,
  file: File,
  photoType: PhotoType,
): Promise<UploadedPhoto> {
  const form = new FormData();
  form.append("file", file);
  form.append("photo_type", photoType);
  const { data } = await client.post<UploadedPhoto>(
    `/sessions/${sessionId}/photos`,
    form,
  );
  return data;
}

export async function triggerAnalysis(
  sessionId: string,
): Promise<{ status: string }> {
  const { data } = await client.post<{ status: string }>(
    `/sessions/${sessionId}/analyze`,
  );
  return data;
}

export async function getAnalysisStatus(
  sessionId: string,
): Promise<{ status: string; progress: number }> {
  const { data } = await client.get<{ status: string; progress: number }>(
    `/sessions/${sessionId}/analyze/status`,
  );
  return data;
}

export async function updateLandmarks(
  sessionId: string,
  photoId: string,
  landmarks: Record<LandmarkType, LandmarkPoint>,
): Promise<{ updated_landmarks: string[]; reference_lines: Record<string, ReferenceLine | null> }> {
  const { data } = await client.put(
    `/sessions/${sessionId}/photos/${photoId}/landmarks`,
    { landmarks },
  );
  return data as { updated_landmarks: string[]; reference_lines: Record<string, ReferenceLine | null> };
}

export async function getAnnotatedPhoto(
  sessionId: string,
  photoId: string,
): Promise<Blob> {
  const { data } = await client.get(
    `/sessions/${sessionId}/photos/${photoId}/annotated`,
    { responseType: "blob" },
  );
  return data as Blob;
}

// Scan upload

export async function uploadScan(
  sessionId: string,
  file: File,
): Promise<Record<string, unknown>> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post<Record<string, unknown>>(
    `/sessions/${sessionId}/scan`,
    form,
  );
  return data;
}

export async function getScanStl(sessionId: string): Promise<Blob> {
  const { data } = await client.get(
    `/sessions/${sessionId}/scan/stl`,
    { responseType: "blob" },
  );
  return data as Blob;
}

// Alignment

export async function triggerAlignment(
  sessionId: string,
): Promise<AlignmentResult> {
  const { data } = await client.post<{ alignment: AlignmentResult }>(
    `/sessions/${sessionId}/align`,
  );
  return data.alignment;
}

export async function approveAlignment(
  sessionId: string,
): Promise<{ status: string }> {
  const { data } = await client.post<{ status: string }>(
    `/sessions/${sessionId}/alignment/approve`,
  );
  return data;
}

// Export

export async function generateExport(
  sessionId: string,
): Promise<ExportFile> {
  const { data } = await client.post<ExportFile>(
    `/sessions/${sessionId}/export`,
  );
  return data;
}

export async function downloadExport(sessionId: string): Promise<Blob> {
  const { data } = await client.get(
    `/sessions/${sessionId}/export/download`,
    { responseType: "blob" },
  );
  return data as Blob;
}

// Fork calibration (session-independent)

export async function uploadFork(
  file: File,
  onProgress?: (pct: number, phase: string) => void,
): Promise<ForkUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  onProgress?.(0, "Uploading file...");
  let uploadDone = false;
  const processingInterval = setInterval(() => {
    if (uploadDone) {
      clearInterval(processingInterval);
    }
  }, 500);

  try {
    const { data } = await client.post<ForkUploadResponse>("/fork/upload", form, {
      onUploadProgress: (e) => {
        if (e.total) {
          const uploadPct = Math.round((e.loaded / e.total) * 50);
          onProgress?.(uploadPct, uploadPct >= 50 ? "Analyzing mesh..." : "Uploading file...");
        }
      },
      timeout: 300000, // 5 min for large STL files
    });
    uploadDone = true;
    clearInterval(processingInterval);
    onProgress?.(100, "Done");
    return data;
  } finally {
    uploadDone = true;
    clearInterval(processingInterval);
  }
}

export async function getForkStl(): Promise<Blob> {
  const { data } = await client.get("/fork/stl", { responseType: "blob" });
  return data as Blob;
}

export async function saveForkConfig(config: {
  apriltags: Array<{ tag_id: number; center_mm: { x: number; y: number; z: number }; normal: { x: number; y: number; z: number } }>;
  tag_size_mm: number;
  markers: HexPostMarker3D[];
  plate_normal: number[];
}): Promise<ForkGeometry> {
  const { data } = await client.post<ForkGeometry>("/fork/configure", config);
  return data;
}

export async function getForkGeometry(): Promise<ForkGeometry | null> {
  try {
    const { data } = await client.get<ForkGeometry>("/fork/geometry");
    return data;
  } catch {
    return null;
  }
}
