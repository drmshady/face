/** AnalysisStep page: analysis progress + results display (T043 + T033b). */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSessionContext } from "../App";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { LandmarkEditor } from "../components/LandmarkEditor";
import { LandmarkOverlay } from "../components/LandmarkOverlay";
import { getAnalysisStatus, getAnnotatedPhoto, exportAnalysisStl } from "../services/api";
import type { LandmarkPoint, ReferenceLine } from "../types";

interface AnalysisResults {
  photos: Record<
    string,
    {
      photo_type: string;
      landmarks: Record<string, LandmarkPoint>;
      external_markers: {
        both_detected: boolean;
        markers: Array<{ marker_id: number; center: { x: number; y: number } }>;
      };
      warnings: string[];
    }
  >;
  reference_lines: Record<string, ReferenceLine | null>;
  overall_confidence: number;
  warnings: string[];
}

export function AnalysisStep() {
  const { session, refresh } = useSessionContext();
  const navigate = useNavigate();
  const [status, setStatus] = useState<string>("analyzing");
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState("");
  const [results, setResults] = useState<AnalysisResults | null>(null);
  const [editingPhotoId, setEditingPhotoId] = useState<string | null>(null);
  const [annotatedUrls, setAnnotatedUrls] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [exportOptions, setExportOptions] = useState({
    include_landmarks: true,
    include_fork: true,
  });
  const [exporting, setExporting] = useState(false);

  const sessionId = session?.session_id ?? "";

  // Poll for analysis progress
  useEffect(() => {
    if (!sessionId || status === "analysis_complete") return;

    const interval = setInterval(async () => {
      try {
        const data = await getAnalysisStatus(sessionId);
        setStatus(data.status);
        setProgress(data.progress);

        const raw = data as unknown as Record<string, unknown>;
        if (typeof raw["current_step"] === "string") {
          setCurrentStep(raw["current_step"]);
        }

        if (data.status === "analysis_complete" && raw["results"]) {
          setResults(raw["results"] as AnalysisResults);
          clearInterval(interval);
          void refresh();
        }

        if (raw["current_step"] === "failed") {
          setError("Analysis failed. Please try again.");
          clearInterval(interval);
        }
      } catch {
        setError("Failed to poll analysis status");
        clearInterval(interval);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [sessionId, status, refresh]);

  // Load annotated photos once results are available
  useEffect(() => {
    if (!results || !sessionId) return;

    const photoIds = Object.keys(results.photos);

    async function loadAnnotated() {
      const urls: Record<string, string> = {};
      for (const photoId of photoIds) {
        try {
          const blob = await getAnnotatedPhoto(sessionId, photoId);
          urls[photoId] = URL.createObjectURL(blob);
        } catch {
          // Skip if annotated photo fails
        }
      }
      setAnnotatedUrls(urls);
    }

    void loadAnnotated();
  }, [results, sessionId]);

  const handleLandmarkUpdate = useCallback(
    (
      updatedLandmarks: Record<string, LandmarkPoint>,
      updatedLines: Record<string, ReferenceLine | null>,
    ) => {
      if (!results || !editingPhotoId) return;
      const photoData = results.photos[editingPhotoId];
      if (!photoData) return;
      setResults({
        ...results,
        reference_lines: updatedLines,
        photos: {
          ...results.photos,
          [editingPhotoId]: {
            ...photoData,
            landmarks: updatedLandmarks,
          },
        },
      });
      void refresh();
    },
    [results, editingPhotoId, refresh],
  );

  const handleExportStl = useCallback(async () => {
    if (!sessionId) return;
    setExporting(true);
    try {
      const blob = await exportAnalysisStl(sessionId, exportOptions);
      const link = document.createElement("a");
      link.download = `analysis-${sessionId.slice(0, 8)}.stl`;
      link.href = URL.createObjectURL(blob);
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (err) {
      console.error("Export failed:", err);
      alert("Export failed. Make sure AprilTags were detected in the photos.");
    } finally {
      setExporting(false);
    }
  }, [sessionId, exportOptions]);

  // Analyzing state
  if (status !== "analysis_complete" && !error) {
    return (
      <div style={{ padding: "24px", textAlign: "center" }}>
        <h2>Analyzing Photos...</h2>
        <div
          style={{
            width: "100%",
            maxWidth: "400px",
            margin: "24px auto",
            backgroundColor: "#e5e7eb",
            borderRadius: "8px",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${progress}%`,
              height: "24px",
              backgroundColor: "#2563eb",
              transition: "width 0.3s",
              borderRadius: "8px",
            }}
          />
        </div>
        <p style={{ color: "#6b7280" }}>
          {currentStep.replace(/_/g, " ")} &middot; {progress}%
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: "24px", textAlign: "center" }}>
        <h2>Analysis Error</h2>
        <p style={{ color: "red" }}>{error}</p>
        <button
          onClick={() => navigate("/")}
          style={{
            padding: "10px 24px",
            backgroundColor: "#2563eb",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          Back to Capture
        </button>
      </div>
    );
  }

  if (!results) return null;

  return (
    <div style={{ padding: "24px" }}>
      <h2>Step 2: Analysis Results</h2>

      <div style={{ marginBottom: "16px" }}>
        <ConfidenceBadge confidence={results.overall_confidence} label="Overall" />
      </div>

      {/* Warnings */}
      {results.warnings.length > 0 && (
        <div
          style={{
            padding: "12px",
            backgroundColor: "#fef3c7",
            borderRadius: "6px",
            marginBottom: "16px",
          }}
        >
          <strong>Warnings:</strong>
          <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
            {results.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Photo results */}
      {Object.entries(results.photos).map(([photoId, photoData]) => (
        <div
          key={photoId}
          style={{
            marginBottom: "24px",
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
            padding: "16px",
          }}
        >
          <h3>
            {photoData.photo_type} photo
            {photoData.external_markers.both_detected && (
              <span style={{ color: "#16a34a", fontSize: "14px", marginLeft: "8px" }}>
                Markers detected
              </span>
            )}
          </h3>

          {(() => {
            const photo = session?.photos.find((p) => p.photo_id === photoId);
            const imgW = photo?.width ?? 800;
            const imgH = photo?.height ?? 600;
            return editingPhotoId === photoId ? (
              <LandmarkEditor
                sessionId={sessionId}
                photoId={photoId}
                imageUrl={annotatedUrls[photoId] ?? ""}
                imageWidth={imgW}
                imageHeight={imgH}
                landmarks={photoData.landmarks}
                referenceLines={results.reference_lines}
                onUpdate={handleLandmarkUpdate}
              />
            ) : (
              <>
                {annotatedUrls[photoId] && (
                  <LandmarkOverlay
                    imageUrl={annotatedUrls[photoId]!}
                    imageWidth={imgW}
                    imageHeight={imgH}
                    landmarks={photoData.landmarks}
                    referenceLines={results.reference_lines}
                    markerPositions={photoData.external_markers.markers}
                  />
                )}
              </>
            );
          })()}

          <button
            onClick={() => setEditingPhotoId(editingPhotoId === photoId ? null : photoId)}
            style={{
              marginTop: "8px",
              padding: "8px 16px",
              backgroundColor: "#f3f4f6",
              border: "1px solid #d1d5db",
              borderRadius: "6px",
              cursor: "pointer",
            }}
          >
            {editingPhotoId === photoId ? "Done Editing" : "Edit Landmarks"}
          </button>
        </div>
      ))}

      {/* Reference lines summary */}
      <div style={{ marginTop: "16px", padding: "16px", backgroundColor: "#f9fafb", borderRadius: "8px" }}>
        <h3>Reference Lines</h3>
        {Object.entries(results.reference_lines).map(([name, line]) => (
          <div key={name} style={{ marginBottom: "8px" }}>
            <strong>{name.replace(/_/g, " ")}:</strong>{" "}
            {line ? (
              <>
                {line.angle_degrees.toFixed(1)} &middot; <ConfidenceBadge confidence={line.confidence} />
                {line.warnings.length > 0 && (
                  <span style={{ color: "#ca8a04", fontSize: "13px", marginLeft: "8px" }}>
                    {line.warnings.join(", ")}
                  </span>
                )}
              </>
            ) : (
              <span style={{ color: "#9ca3af" }}>Not computed (landmarks missing)</span>
            )}
          </div>
        ))}
      </div>

      {/* Export STL */}
      <div
        style={{
          marginTop: "24px",
          padding: "16px",
          backgroundColor: "#f0f9ff",
          borderRadius: "8px",
          border: "1px solid #bae6fd",
        }}
      >
        <h3 style={{ margin: "0 0 12px 0" }}>Export 3D Model</h3>
        <p style={{ margin: "0 0 12px 0", fontSize: "14px", color: "#64748b" }}>
          Export landmarks and fork to STL file (uses AprilTag detection for 3D positioning)
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "12px" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={exportOptions.include_landmarks}
              onChange={(e) => setExportOptions((o) => ({ ...o, include_landmarks: e.target.checked }))}
            />
            Include Landmarks (spheres)
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={exportOptions.include_fork}
              onChange={(e) => setExportOptions((o) => ({ ...o, include_fork: e.target.checked }))}
            />
            Include Fork Geometry
          </label>
        </div>
        <button
          onClick={handleExportStl}
          disabled={exporting}
          style={{
            padding: "10px 24px",
            backgroundColor: "#2563eb",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: exporting ? "not-allowed" : "pointer",
            opacity: exporting ? 0.7 : 1,
          }}
        >
          {exporting ? "Exporting..." : "Download STL"}
        </button>
      </div>

      <div style={{ display: "flex", gap: "12px", marginTop: "24px" }}>
        <button
          onClick={() => navigate("/align")}
          style={{
            padding: "14px 32px",
            fontSize: "18px",
            backgroundColor: "#2563eb",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
            fontWeight: "bold",
          }}
        >
          View 3D Alignment
        </button>
        <button
          onClick={() => navigate("/scan")}
          style={{
            padding: "14px 32px",
            fontSize: "18px",
            backgroundColor: "#6b7280",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          Upload Scan (Optional)
        </button>
      </div>
    </div>
  );
}
