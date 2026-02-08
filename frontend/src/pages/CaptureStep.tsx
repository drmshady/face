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
  const [photos, setPhotos] = useState<UploadedPhoto[]>([]);
  const [showCamera, setShowCamera] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sessionId = session?.session_id ?? "";

  const handlePhotoUploaded = useCallback((photo: UploadedPhoto) => {
    setPhotos((prev) => [...prev, photo]);
  }, []);

  const handleCameraCapture = useCallback(
    async (blob: Blob) => {
      setShowCamera(false);
      const photoType = photos.length === 0 ? "frontal" : "side";
      const file = new File([blob], `capture-${photos.length + 1}.jpg`, { type: "image/jpeg" });
      try {
        const photo = await uploadPhoto(sessionId, file, photoType);
        setPhotos((prev) => [...prev, photo]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Capture upload failed");
      }
    },
    [sessionId, photos.length],
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

  const canAnalyze = consent && photos.length >= 2;

  if (showCamera) {
    return <PhotoCapture onCapture={handleCameraCapture} onClose={() => setShowCamera(false)} />;
  }

  return (
    <div style={{ padding: "24px" }}>
      <h2>Step 1: Upload Photos</h2>

      {session && (
        <p style={{ color: "#6b7280" }}>
          Session: {session.session_id.slice(0, 8)}... &middot; Status: {session.status}
        </p>
      )}

      <ConsentDisclosure onConsent={() => setConsent(true)} hasConsented={consent} />

      {consent && (
        <>
          {/* Photos */}
          <div style={{ marginTop: "24px" }}>
            <h3>Photos ({photos.length} uploaded)</h3>
            <p style={{ color: "#6b7280", fontSize: "14px", marginBottom: "12px" }}>
              Upload 3-5 photos from different angles. First photo is used as frontal reference.
            </p>
            {photos.length > 0 && (
              <div style={{ marginBottom: "12px" }}>
                {photos.map((p, i) => (
                  <p key={p.photo_id} style={{ color: "#16a34a", margin: "4px 0" }}>
                    {i === 0 ? "[Frontal] " : `[Side ${i}] `}
                    {p.original_filename} ({p.width}x{p.height})
                  </p>
                ))}
              </div>
            )}
            <div style={{ display: "flex", gap: "12px", flexDirection: "column" }}>
              <PhotoUpload
                sessionId={sessionId}
                photoType={photos.length === 0 ? "frontal" : "side"}
                onUploaded={handlePhotoUploaded}
                multiple
              />
              <button
                onClick={() => setShowCamera(true)}
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
                Upload at least 2 photos to analyze.
              </p>
            )}

            {error && <p style={{ color: "red", marginTop: "8px" }}>{error}</p>}
          </div>
        </>
      )}
    </div>
  );
}
