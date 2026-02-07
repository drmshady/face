/** LandmarkOverlay: renders landmarks, markers, and reference lines on photo (T040). */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ConfidenceBadge } from "./ConfidenceBadge";
import type { LandmarkPoint, LandmarkType, ReferenceLine } from "../types";

const LINE_COLORS: Record<string, string> = {
  interpupillary: "#00ff00",
  midline: "#ff3333",
  frankfort_plane: "#ff00ff",
  ala_tragus: "#ffcc00",
  canthus_tragus: "#00ccff",
};

const LANDMARK_COLORS: Partial<Record<LandmarkType, string>> = {
  left_pupil: "#00ff00",
  right_pupil: "#00ff00",
  left_outer_canthus: "#00ccff",
  right_outer_canthus: "#00ccff",
  left_ala: "#ffcc00",
  right_ala: "#ffcc00",
  left_tragus: "#ff6600",
  right_tragus: "#ff6600",
};

interface LandmarkOverlayProps {
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  landmarks?: Record<string, LandmarkPoint>;
  referenceLines?: Record<string, ReferenceLine | null>;
  markerPositions?: Array<{ marker_id: number; center: { x: number; y: number } }>;
}

export function LandmarkOverlay({
  imageUrl,
  imageWidth,
  imageHeight,
  landmarks,
  referenceLines,
  markerPositions,
}: LandmarkOverlayProps) {
  // Scale factor for display
  const displayWidth = Math.min(imageWidth, 800);
  const scale = displayWidth / imageWidth;
  const displayHeight = imageHeight * scale;

  // Zoom / pan state
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStart = useRef({ x: 0, y: 0, panX: 0, panY: 0 });
  const viewportRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // Compute face bounding box from landmarks for auto-crop
  const faceBounds = useMemo(() => {
    if (!landmarks) return null;
    const pts = Object.values(landmarks);
    if (pts.length < 2) return null;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const lm of pts) {
      if (lm.x < minX) minX = lm.x;
      if (lm.y < minY) minY = lm.y;
      if (lm.x > maxX) maxX = lm.x;
      if (lm.y > maxY) maxY = lm.y;
    }
    // Add padding (30% of bounding box size)
    const padX = (maxX - minX) * 0.3;
    const padY = (maxY - minY) * 0.3;
    return {
      minX: Math.max(0, minX - padX),
      minY: Math.max(0, minY - padY),
      maxX: Math.min(imageWidth, maxX + padX),
      maxY: Math.min(imageHeight, maxY + padY),
    };
  }, [landmarks, imageWidth, imageHeight]);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setZoom((prev) => {
      const next = prev * (e.deltaY < 0 ? 1.15 : 1 / 1.15);
      return Math.max(1, Math.min(next, 8));
    });
  }, []);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (zoom <= 1) return;
      e.preventDefault();
      setIsPanning(true);
      panStart.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
    },
    [zoom, pan],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isPanning) return;
      const dx = e.clientX - panStart.current.x;
      const dy = e.clientY - panStart.current.y;
      setPan({ x: panStart.current.panX + dx, y: panStart.current.panY + dy });
    },
    [isPanning],
  );

  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  const resetZoom = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  const autoCrop = useCallback(() => {
    if (!faceBounds || !viewportRef.current) return;
    const bw = faceBounds.maxX - faceBounds.minX;
    const bh = faceBounds.maxY - faceBounds.minY;
    if (bw < 1 || bh < 1) return;

    // Compute zoom to fit face bounds in viewport
    const zoomX = imageWidth / bw;
    const zoomY = imageHeight / bh;
    const newZoom = Math.min(zoomX, zoomY, 8);

    // Center on face bounds (in display coordinates)
    const faceCenterX = ((faceBounds.minX + faceBounds.maxX) / 2) * scale;
    const faceCenterY = ((faceBounds.minY + faceBounds.maxY) / 2) * scale;
    const viewCenterX = displayWidth / 2;
    const viewCenterY = displayHeight / 2;

    setZoom(newZoom);
    setPan({
      x: (viewCenterX - faceCenterX) * newZoom,
      y: (viewCenterY - faceCenterY) * newZoom,
    });
  }, [faceBounds, imageWidth, imageHeight, scale, displayWidth, displayHeight]);

  // Clamp pan when zoom changes
  useEffect(() => {
    if (zoom <= 1) {
      setPan({ x: 0, y: 0 });
    }
  }, [zoom]);

  // Export annotated image
  const exportImage = useCallback(() => {
    const canvas = document.createElement("canvas");
    canvas.width = imageWidth;
    canvas.height = imageHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      ctx.drawImage(img, 0, 0, imageWidth, imageHeight);

      // Draw reference lines
      if (referenceLines) {
        for (const [name, line] of Object.entries(referenceLines)) {
          if (!line) continue;
          const color = LINE_COLORS[name] ?? "#ffffff";
          ctx.strokeStyle = color;
          ctx.lineWidth = 3;
          ctx.setLineDash([8, 4]);
          ctx.beginPath();
          ctx.moveTo(line.start_point.x, line.start_point.y);
          ctx.lineTo(line.end_point.x, line.end_point.y);
          ctx.stroke();
          ctx.setLineDash([]);

          // Label
          const mx = (line.start_point.x + line.end_point.x) / 2;
          const my = (line.start_point.y + line.end_point.y) / 2;
          ctx.fillStyle = color;
          ctx.font = "bold 18px sans-serif";
          ctx.textAlign = "center";
          ctx.fillText(name.replace(/_/g, " "), mx, my - 12);
        }
      }

      // Draw landmarks
      if (landmarks) {
        for (const [name, lm] of Object.entries(landmarks)) {
          const color = LANDMARK_COLORS[name as LandmarkType] ?? "#ffffff";
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(lm.x, lm.y, 7, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = "white";
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      }

      // Draw marker positions
      if (markerPositions) {
        for (const m of markerPositions) {
          ctx.strokeStyle = "#00ff00";
          ctx.lineWidth = 2;
          ctx.strokeRect(m.center.x - 15, m.center.y - 15, 30, 30);
          ctx.fillStyle = "#00ff00";
          ctx.font = "14px sans-serif";
          ctx.textAlign = "left";
          ctx.fillText(`M${m.marker_id}`, m.center.x + 18, m.center.y - 5);
        }
      }

      // Patient orientation labels
      ctx.fillStyle = "rgba(255,255,255,0.7)";
      ctx.font = "bold 36px sans-serif";
      ctx.textAlign = "left";
      ctx.strokeStyle = "black";
      ctx.lineWidth = 1;
      ctx.strokeText("R", 20, 50);
      ctx.fillText("R", 20, 50);
      ctx.textAlign = "right";
      ctx.strokeText("L", imageWidth - 20, 50);
      ctx.fillText("L", imageWidth - 20, 50);

      // Trigger download
      const link = document.createElement("a");
      link.download = "annotated-photo.png";
      link.href = canvas.toDataURL("image/png");
      link.click();
    };
    img.src = imageUrl;
  }, [imageUrl, imageWidth, imageHeight, landmarks, referenceLines, markerPositions]);

  return (
    <div>
      {/* Controls */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "8px", alignItems: "center" }}>
        <button
          onClick={autoCrop}
          disabled={!faceBounds}
          style={{
            padding: "4px 12px",
            fontSize: "13px",
            border: "1px solid #d1d5db",
            borderRadius: "4px",
            backgroundColor: "#f9fafb",
            cursor: faceBounds ? "pointer" : "default",
            opacity: faceBounds ? 1 : 0.5,
          }}
        >
          Auto-crop Face
        </button>
        {zoom > 1 && (
          <button
            onClick={resetZoom}
            style={{
              padding: "4px 12px",
              fontSize: "13px",
              border: "1px solid #d1d5db",
              borderRadius: "4px",
              backgroundColor: "#f9fafb",
              cursor: "pointer",
            }}
          >
            Reset Zoom ({zoom.toFixed(1)}x)
          </button>
        )}
        <button
          onClick={exportImage}
          style={{
            padding: "4px 12px",
            fontSize: "13px",
            border: "1px solid #2563eb",
            borderRadius: "4px",
            backgroundColor: "#eff6ff",
            color: "#2563eb",
            cursor: "pointer",
          }}
        >
          Export Image
        </button>
        <span style={{ fontSize: "12px", color: "#9ca3af" }}>Scroll to zoom, drag to pan</span>
      </div>

      {/* Viewport with zoom/pan */}
      <div
        ref={viewportRef}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{
          position: "relative",
          width: displayWidth,
          height: displayHeight,
          overflow: "hidden",
          cursor: isPanning ? "grabbing" : zoom > 1 ? "grab" : "default",
          borderRadius: "4px",
        }}
      >
        <div
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            transformOrigin: "center center",
            width: displayWidth,
            height: displayHeight,
            position: "relative",
          }}
        >
          <img
            src={imageUrl}
            alt="Analyzed photo"
            style={{ width: displayWidth, height: displayHeight, display: "block" }}
            draggable={false}
          />
          <svg
            ref={svgRef}
            style={{ position: "absolute", top: 0, left: 0, width: displayWidth, height: displayHeight }}
            viewBox={`0 0 ${imageWidth} ${imageHeight}`}
          >
            {/* Reference lines */}
            {referenceLines &&
              Object.entries(referenceLines).map(([name, line]) => {
                if (!line) return null;
                const color = LINE_COLORS[name] ?? "#ffffff";
                return (
                  <g key={name}>
                    <line
                      x1={line.start_point.x}
                      y1={line.start_point.y}
                      x2={line.end_point.x}
                      y2={line.end_point.y}
                      stroke={color}
                      strokeWidth={2}
                      strokeDasharray="6,3"
                    />
                    <text
                      x={(line.start_point.x + line.end_point.x) / 2}
                      y={(line.start_point.y + line.end_point.y) / 2 - 8}
                      fill={color}
                      fontSize={12}
                      textAnchor="middle"
                    >
                      {name.replace(/_/g, " ")}
                    </text>
                  </g>
                );
              })}

            {/* Landmarks */}
            {landmarks &&
              Object.entries(landmarks).map(([name, lm]) => {
                const color = LANDMARK_COLORS[name as LandmarkType] ?? "#ffffff";
                return (
                  <g key={name}>
                    <circle cx={lm.x} cy={lm.y} r={5} fill={color} stroke="white" strokeWidth={1} />
                    {lm.is_manual && (
                      <circle cx={lm.x} cy={lm.y} r={8} fill="none" stroke="#ff6600" strokeWidth={1.5} />
                    )}
                  </g>
                );
              })}

            {/* Patient orientation labels */}
            <text x={20} y={40} fill="white" fontSize={28} fontWeight="bold" opacity={0.7}
              stroke="black" strokeWidth={0.5}>R</text>
            <text x={imageWidth - 40} y={40} fill="white" fontSize={28} fontWeight="bold" opacity={0.7}
              stroke="black" strokeWidth={0.5}>L</text>

            {/* Marker positions */}
            {markerPositions?.map((m) => (
              <g key={m.marker_id}>
                <rect
                  x={m.center.x - 15}
                  y={m.center.y - 15}
                  width={30}
                  height={30}
                  fill="none"
                  stroke="#00ff00"
                  strokeWidth={2}
                />
                <text x={m.center.x + 18} y={m.center.y - 5} fill="#00ff00" fontSize={11}>
                  M{m.marker_id}
                </text>
              </g>
            ))}
          </svg>
        </div>
      </div>

      {/* Confidence badges for reference lines */}
      {referenceLines && (
        <div style={{ marginTop: "8px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {Object.entries(referenceLines).map(([name, line]) => {
            if (!line) {
              return (
                <span
                  key={name}
                  style={{
                    padding: "2px 8px",
                    borderRadius: "12px",
                    fontSize: "12px",
                    color: "#9ca3af",
                    backgroundColor: "#f3f4f6",
                  }}
                >
                  {name.replace(/_/g, " ")}: missing
                </span>
              );
            }
            return (
              <ConfidenceBadge
                key={name}
                confidence={line.confidence}
                label={name.replace(/_/g, " ")}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
