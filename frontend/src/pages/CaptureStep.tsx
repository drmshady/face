/** CaptureStep page: photo upload, capture, and analysis trigger (T042). */

import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSessionContext } from "../App";
import { ConsentDisclosure } from "../components/ConsentDisclosure";
import { PhotoCapture } from "../components/PhotoCapture";
import { PhotoUpload } from "../components/PhotoUpload";
import { triggerAnalysis, uploadPhoto } from "../services/api";
import type { UploadedPhoto } from "../types";

export function CaptureStep() {
  const { session, consent, setConsent, refresh } = useSessionContext();
  const navigate = useNavigate();
  const [frontalPhoto, setFrontalPhoto] = useState<UploadedPhoto | null>(null);
  const [sidePhotos, setSidePhotos] = useState<UploadedPhoto[]>([]);
  const [showCamera, setShowCamera] = useState(false);
  const [cameraTarget, setCameraTarget] = useState<"frontal" | "side">("frontal");
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sessionId = session?.session_id ?? "";

  const handleFrontalUploaded = useCallback((photo: UploadedPhoto) => {
    setFrontalPhoto(photo);
  }, []);

  const handleSideUploaded = useCallback((photo: UploadedPhoto) => {
    setSidePhotos((prev) => [...prev, photo]);
  }, []);

  const handleCameraCapture = useCallback(
    async (blob: Blob) => {
      setShowCamera(false);
      const file = new File([blob], `${cameraTarget}-capture.jpg`, { type: "image/jpeg" });
      try {
        const photo = await uploadPhoto(sessionId, file, cameraTarget);
        if (cameraTarget === "frontal") {
          setFrontalPhoto(photo);
        } else {
          setSidePhotos((prev) => [...prev, photo]);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Capture upload failed");
      }
    },
    [sessionId, cameraTarget],
  );

  const handleAnalyze = useCallback(async () => {
    if (!sessionId) return;
    setError(null);
    setAnalyzing(true);

    try {
      await triggerAnalysis(sessionId);
      await refresh();
      navigate("/analysis");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed to start");
      setAnalyzing(false);
    }
  }, [sessionId, refresh, navigate]);

  const canAnalyze = consent && frontalPhoto !== null && sidePhotos.length > 0;

  if (showCamera) {
    return <PhotoCapture onCapture={handleCameraCapture} onClose={() => setShowCamera(false)} />;
  }

  return (
    <div style={{ padding: "24px" }}>
      <h2>Step 1: Capture Face Photos</h2>

      {session && (
        <p style={{ color: "#6b7280" }}>
          Session: {session.session_id.slice(0, 8)}... &middot; Status: {session.status}
        </p>
      )}

      <ConsentDisclosure onConsent={() => setConsent(true)} hasConsented={consent} />

      {consent && (
        <>
          {/* Frontal photo */}
          <div style={{ marginTop: "24px" }}>
            <h3>Frontal Photo {frontalPhoto && " (uploaded)"}</h3>
            {frontalPhoto ? (
              <p style={{ color: "#16a34a" }}>
                {frontalPhoto.original_filename} ({frontalPhoto.width}x{frontalPhoto.height})
              </p>
            ) : (
              <div style={{ display: "flex", gap: "12px", flexDirection: "column" }}>
                <PhotoUpload sessionId={sessionId} photoType="frontal" onUploaded={handleFrontalUploaded} />
                <button
                  onClick={() => {
                    setCameraTarget("frontal");
                    setShowCamera(true);
                  }}
                  style={{
                    padding: "10px",
                    backgroundColor: "#f3f4f6",
                    border: "1px solid #d1d5db",
                    borderRadius: "6px",
                    cursor: "pointer",
                  }}
                >
                  Use Camera
                </button>
              </div>
            )}
          </div>

          {/* Side photos */}
          <div style={{ marginTop: "24px" }}>
            <h3>Side Photo(s) ({sidePhotos.length} uploaded)</h3>
            {sidePhotos.map((p) => (
              <p key={p.photo_id} style={{ color: "#16a34a" }}>
                {p.original_filename} ({p.width}x{p.height})
              </p>
            ))}
            <div style={{ display: "flex", gap: "12px", flexDirection: "column" }}>
              <PhotoUpload sessionId={sessionId} photoType="side" onUploaded={handleSideUploaded} />
              <button
                onClick={() => {
                  setCameraTarget("side");
                  setShowCamera(true);
                }}
                style={{
                  padding: "10px",
                  backgroundColor: "#f3f4f6",
                  border: "1px solid #d1d5db",
                  borderRadius: "6px",
                  cursor: "pointer",
                }}
              >
                Use Camera
              </button>
            </div>
          </div>

          {/* Analyze button */}
          <div style={{ marginTop: "24px" }}>
            <button
              onClick={handleAnalyze}
              disabled={!canAnalyze || analyzing}
              style={{
                padding: "14px 32px",
                fontSize: "18px",
                backgroundColor: canAnalyze && !analyzing ? "#2563eb" : "#9ca3af",
                color: "white",
                border: "none",
                borderRadius: "6px",
                cursor: canAnalyze && !analyzing ? "pointer" : "not-allowed",
              }}
            >
              {analyzing ? "Starting Analysis..." : "Analyze Photos"}
            </button>

            {!canAnalyze && !analyzing && (
              <p style={{ color: "#9ca3af", fontSize: "14px", marginTop: "8px" }}>
                Upload at least 1 frontal and 1 side photo to analyze.
              </p>
            )}

            {error && <p style={{ color: "red", marginTop: "8px" }}>{error}</p>}
          </div>
        </>
      )}
    </div>
  );
}
