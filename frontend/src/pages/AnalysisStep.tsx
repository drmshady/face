/** AnalysisStep page: analysis progress + results display (T043 + T033b). */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSessionContext } from "../App";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { LandmarkEditor } from "../components/LandmarkEditor";
import { LandmarkOverlay } from "../components/LandmarkOverlay";
import { getAnalysisStatus, getAnnotatedPhoto, triggerAlignment } from "../services/api";
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
  const [alignmentStatus, setAlignmentStatus] = useState<"idle" | "aligning" | "done" | "error">("idle");
  const [alignmentError, setAlignmentError] = useState<string | null>(null);

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

  // Auto-trigger alignment after analysis completes
  useEffect(() => {
    if (!results || !sessionId || alignmentStatus !== "idle") return;

    const runAlignment = async () => {
      setAlignmentStatus("aligning");
      try {
        await triggerAlignment(sessionId);
        setAlignmentStatus("done");
        navigate("/preview");
      } catch (err) {
        setAlignmentStatus("error");
        setAlignmentError(err instanceof Error ? err.message : "Alignment failed");
      }
    };
    void runAlignment();
  }, [results, sessionId, alignmentStatus, navigate]);

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

  if (error || alignmentError) {
    return (
      <div style={{ padding: "24px", textAlign: "center" }}>
        <h2>{alignmentError ? "Alignment Error" : "Analysis Error"}</h2>
        <p style={{ color: "red" }}>{alignmentError ?? error}</p>
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
          Start Over
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

      {/* Alignment progress */}
      {alignmentStatus === "aligning" && (
        <div style={{ marginTop: "24px", textAlign: "center", padding: "16px", backgroundColor: "#f0f9ff", borderRadius: "8px" }}>
          <p style={{ color: "#2563eb", fontWeight: "bold" }}>Running 3D alignment...</p>
        </div>
      )}

      {alignmentStatus === "idle" && (
        <div style={{ marginTop: "24px" }}>
          <button
            onClick={() => navigate("/preview")}
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
            Continue to Preview
          </button>
        </div>
      )}
    </div>
  );
}
