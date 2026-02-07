/** Scan upload page — workflow step 3 (T061). */

import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSessionContext } from "../App";
import { StlViewer } from "../components/StlViewer";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import * as api from "../services/api";
import type { IntraOralMarker } from "../types";

export function ScanStep() {
  const { session, refresh } = useSessionContext();
  const navigate = useNavigate();

  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanBlob, setScanBlob] = useState<Blob | null>(null);
  const [scanMeta, setScanMeta] = useState<{
    scan_id: string;
    vertex_count: number;
    face_count: number;
    intra_oral_markers: {
      markers_found: number;
      sufficient: boolean;
      markers: IntraOralMarker[];
    };
  } | null>(null);
  const [aligning, setAligning] = useState(false);

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file || !session) return;

      // Validate file size (100 MB)
      if (file.size > 100 * 1024 * 1024) {
        setError("STL file must be under 100 MB");
        return;
      }

      setUploading(true);
      setError(null);

      try {
        const result = await api.uploadScan(session.session_id, file);
        setScanMeta(result as typeof scanMeta);
        setScanBlob(file);
        await refresh();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Upload failed";
        setError(msg);
      } finally {
        setUploading(false);
      }
    },
    [session, refresh],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0];
      if (file && session) {
        // Trigger same upload logic
        const input = document.createElement("input");
        input.type = "file";
        const dt = new DataTransfer();
        dt.items.add(file);
        input.files = dt.files;
        handleFileSelect({ target: input } as unknown as React.ChangeEvent<HTMLInputElement>);
      }
    },
    [session, handleFileSelect],
  );

  const handleAlign = useCallback(async () => {
    if (!session) return;
    setAligning(true);
    setError(null);
    try {
      await api.triggerAlignment(session.session_id);
      await refresh();
      navigate("/align");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Alignment failed";
      setError(msg);
    } finally {
      setAligning(false);
    }
  }, [session, refresh, navigate]);

  if (!session) {
    return <div style={{ padding: "24px", textAlign: "center" }}>No session. Go back to Capture.</div>;
  }

  return (
    <div style={{ padding: "24px" }}>
      <h2>Step 3: Upload Intra-Oral Scan</h2>

      {/* Upload zone */}
      {!scanMeta && (
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          style={{
            border: "2px dashed #94a3b8",
            borderRadius: "12px",
            padding: "48px",
            textAlign: "center",
            backgroundColor: "#f8fafc",
            cursor: "pointer",
          }}
        >
          <p style={{ fontSize: "1.1em", marginBottom: "12px" }}>
            Drag & drop your STL scan file here
          </p>
          <p style={{ color: "#64748b", marginBottom: "16px" }}>or</p>
          <label
            style={{
              padding: "10px 24px",
              backgroundColor: "#2563eb",
              color: "white",
              borderRadius: "6px",
              cursor: "pointer",
            }}
          >
            Browse Files
            <input
              type="file"
              accept=".stl"
              onChange={handleFileSelect}
              style={{ display: "none" }}
            />
          </label>
          <p style={{ color: "#94a3b8", marginTop: "12px", fontSize: "0.85em" }}>
            STL format, max 100 MB
          </p>
        </div>
      )}

      {uploading && (
        <div style={{ textAlign: "center", padding: "24px" }}>
          <p>Uploading and processing scan...</p>
        </div>
      )}

      {error && (
        <div style={{ color: "red", padding: "12px", marginTop: "12px" }}>{error}</div>
      )}

      {/* Scan results */}
      {scanMeta && (
        <div style={{ marginTop: "16px" }}>
          <div style={{ marginBottom: "16px" }}>
            <strong>Vertices:</strong> {scanMeta.vertex_count.toLocaleString()} |{" "}
            <strong>Faces:</strong> {scanMeta.face_count.toLocaleString()}
          </div>

          {/* 3D viewer */}
          {scanBlob && (
            <StlViewer
              stlBlob={scanBlob}
              markers={scanMeta.intra_oral_markers.markers}
            />
          )}

          {/* Marker detection results */}
          <div style={{ marginTop: "16px", padding: "16px", backgroundColor: "#f1f5f9", borderRadius: "8px" }}>
            <h3 style={{ margin: "0 0 8px 0" }}>
              Intra-Oral Markers: {scanMeta.intra_oral_markers.markers_found} detected
              {scanMeta.intra_oral_markers.sufficient ? (
                <span style={{ color: "#22c55e", marginLeft: "8px" }}>Sufficient</span>
              ) : (
                <span style={{ color: "#ef4444", marginLeft: "8px" }}>Insufficient (need 3+)</span>
              )}
            </h3>
            {scanMeta.intra_oral_markers.markers.map((m) => (
              <div key={m.marker_id} style={{ display: "flex", gap: "16px", padding: "4px 0" }}>
                <span>Marker {m.marker_id}</span>
                <span>
                  r={m.fitted_radius.toFixed(2)}mm
                </span>
                <ConfidenceBadge confidence={m.confidence} />
                <span style={{ color: "#64748b" }}>
                  residual: {m.residual.toFixed(3)}mm
                </span>
              </div>
            ))}
          </div>

          {/* Compute alignment button */}
          <button
            onClick={handleAlign}
            disabled={aligning || !scanMeta.intra_oral_markers.sufficient}
            style={{
              marginTop: "16px",
              padding: "12px 32px",
              backgroundColor: aligning ? "#94a3b8" : "#2563eb",
              color: "white",
              border: "none",
              borderRadius: "6px",
              cursor: aligning ? "not-allowed" : "pointer",
              fontWeight: "bold",
              fontSize: "1em",
            }}
          >
            {aligning ? "Computing Alignment..." : "Compute Alignment"}
          </button>
        </div>
      )}
    </div>
  );
}
