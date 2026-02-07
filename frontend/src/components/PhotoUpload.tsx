/** PhotoUpload component: drag-and-drop file upload (T037). */

import { useCallback, useRef, useState } from "react";
import { uploadPhoto } from "../services/api";
import type { PhotoType, UploadedPhoto } from "../types";

const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_SIZE_MB = 10;

interface PhotoUploadProps {
  sessionId: string;
  photoType: PhotoType;
  onUploaded: (photo: UploadedPhoto) => void;
}

export function PhotoUpload({ sessionId, photoType, onUploaded }: PhotoUploadProps) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);

      if (!ALLOWED_TYPES.includes(file.type)) {
        setError("File must be JPEG, PNG, or WebP");
        return;
      }
      if (file.size > MAX_SIZE_MB * 1024 * 1024) {
        setError(`File exceeds ${MAX_SIZE_MB} MB limit`);
        return;
      }

      try {
        setUploading(true);
        const photo = await uploadPhoto(sessionId, file, photoType);
        onUploaded(photo);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setUploading(false);
      }
    },
    [sessionId, photoType, onUploaded],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) void handleFile(file);
    },
    [handleFile],
  );

  const onFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) void handleFile(file);
    },
    [handleFile],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => inputRef.current?.click()}
      style={{
        border: `2px dashed ${dragging ? "#2563eb" : "#d1d5db"}`,
        borderRadius: "8px",
        padding: "32px",
        textAlign: "center",
        cursor: "pointer",
        backgroundColor: dragging ? "#eff6ff" : "#f9fafb",
        transition: "all 0.2s",
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".jpg,.jpeg,.png,.webp"
        onChange={onFileChange}
        style={{ display: "none" }}
      />
      {uploading ? (
        <p>Uploading...</p>
      ) : (
        <>
          <p style={{ fontWeight: "bold", margin: "0 0 8px" }}>
            Drop {photoType} photo here or click to browse
          </p>
          <p style={{ color: "#6b7280", fontSize: "14px", margin: 0 }}>
            JPEG, PNG, or WebP &middot; Max {MAX_SIZE_MB} MB
          </p>
        </>
      )}
      {error && <p style={{ color: "red", marginTop: "8px" }}>{error}</p>}
    </div>
  );
}
