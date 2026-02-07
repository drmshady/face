/** PhotoCapture component: camera capture with guidance overlay (T038). */

import { useCallback, useEffect, useRef, useState } from "react";

interface PhotoCaptureProps {
  onCapture: (blob: Blob) => void;
  onClose: () => void;
}

export function PhotoCapture({ onCapture, onClose }: PhotoCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function startCamera() {
      try {
        const mediaStream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: { ideal: 1920 }, height: { ideal: 1080 } },
        });
        if (!active) {
          mediaStream.getTracks().forEach((t) => t.stop());
          return;
        }
        setStream(mediaStream);
        if (videoRef.current) {
          videoRef.current.srcObject = mediaStream;
        }
      } catch (err) {
        setError("Camera access denied. Please allow camera permissions.");
      }
    }

    void startCamera();

    return () => {
      active = false;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const capture = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (blob) onCapture(blob);
      },
      "image/jpeg",
      0.92,
    );
  }, [onCapture]);

  const stopCamera = useCallback(() => {
    stream?.getTracks().forEach((t) => t.stop());
    onClose();
  }, [stream, onClose]);

  if (error) {
    return (
      <div style={{ padding: "24px", textAlign: "center" }}>
        <p style={{ color: "red" }}>{error}</p>
        <button onClick={onClose}>Close</button>
      </div>
    );
  }

  return (
    <div style={{ position: "relative" }}>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        style={{ width: "100%", borderRadius: "8px" }}
      />
      {/* Guidance overlay */}
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          border: "2px dashed rgba(255,255,255,0.5)",
          borderRadius: "50%",
          width: "60%",
          height: "80%",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: "10px",
          left: "50%",
          transform: "translateX(-50%)",
          color: "white",
          backgroundColor: "rgba(0,0,0,0.5)",
          padding: "4px 12px",
          borderRadius: "4px",
          fontSize: "14px",
        }}
      >
        Ensure face and bite fork markers are visible
      </div>
      <canvas ref={canvasRef} style={{ display: "none" }} />
      <div style={{ display: "flex", gap: "8px", justifyContent: "center", marginTop: "8px" }}>
        <button
          onClick={capture}
          style={{
            padding: "12px 32px",
            fontSize: "16px",
            backgroundColor: "#2563eb",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          Capture
        </button>
        <button
          onClick={stopCamera}
          style={{
            padding: "12px 24px",
            fontSize: "16px",
            backgroundColor: "#6b7280",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
