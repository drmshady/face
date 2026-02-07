/** LandmarkEditor: draggable landmarks with manual adjustment + zoom/pan (T041). */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { updateLandmarks } from "../services/api";
import type { LandmarkPoint, LandmarkType, ReferenceLine } from "../types";

const ALL_LANDMARK_TYPES: LandmarkType[] = [
  "left_pupil",
  "right_pupil",
  "left_outer_canthus",
  "right_outer_canthus",
  "left_ala",
  "right_ala",
  "left_tragus",
  "right_tragus",
  "left_porion",
  "right_porion",
  "left_orbitale",
  "right_orbitale",
];

interface LandmarkEditorProps {
  sessionId: string;
  photoId: string;
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  landmarks: Record<string, LandmarkPoint>;
  referenceLines: Record<string, ReferenceLine | null>;
  onUpdate: (
    updatedLandmarks: Record<string, LandmarkPoint>,
    updatedLines: Record<string, ReferenceLine | null>,
  ) => void;
}

export function LandmarkEditor({
  sessionId,
  photoId,
  imageUrl,
  imageWidth,
  imageHeight,
  landmarks,
  referenceLines,
  onUpdate,
}: LandmarkEditorProps) {
  const [dragging, setDragging] = useState<string | null>(null);
  const [localLandmarks, setLocalLandmarks] = useState(landmarks);
  const [localRefLines, setLocalRefLines] = useState(referenceLines);
  const [saving, setSaving] = useState(false);
  const [placingLandmark, setPlacingLandmark] = useState<LandmarkType | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Zoom/pan state
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStart = useRef({ x: 0, y: 0, panX: 0, panY: 0 });

  const displayWidth = Math.min(imageWidth, 800);
  const scale = displayWidth / imageWidth;
  const displayHeight = imageHeight * scale;

  const missingLandmarks = useMemo(
    () => ALL_LANDMARK_TYPES.filter((t) => !(t in localLandmarks)),
    [localLandmarks],
  );

  /** Convert client coords to image-space coords, accounting for zoom+pan. */
  const toImageCoords = useCallback(
    (clientX: number, clientY: number) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return { x: 0, y: 0 };
      // Account for viewport → inner transform
      const viewX = clientX - rect.left;
      const viewY = clientY - rect.top;
      // Reverse the transform: translate then scale from center
      const centerX = displayWidth / 2;
      const centerY = displayHeight / 2;
      const innerX = (viewX - pan.x - centerX) / zoom + centerX;
      const innerY = (viewY - pan.y - centerY) / zoom + centerY;
      return {
        x: innerX / scale,
        y: innerY / scale,
      };
    },
    [scale, zoom, pan, displayWidth, displayHeight],
  );

  const handleMouseDown = useCallback((name: string) => {
    setDragging(name);
  }, []);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (isPanning) {
        const dx = e.clientX - panStart.current.x;
        const dy = e.clientY - panStart.current.y;
        setPan({ x: panStart.current.panX + dx, y: panStart.current.panY + dy });
        return;
      }
      if (!dragging) return;
      const coords = toImageCoords(e.clientX, e.clientY);
      setLocalLandmarks((prev) => ({
        ...prev,
        [dragging]: { ...prev[dragging]!, x: coords.x, y: coords.y, is_manual: true },
      }));
    },
    [dragging, isPanning, toImageCoords],
  );

  const saveLandmark = useCallback(
    async (name: string, lm: LandmarkPoint, allLandmarks: Record<string, LandmarkPoint>) => {
      setSaving(true);
      try {
        const resp = await updateLandmarks(sessionId, photoId, {
          [name]: lm,
        } as Record<LandmarkType, LandmarkPoint>);
        setLocalRefLines(resp.reference_lines);
        onUpdate(allLandmarks, resp.reference_lines);
      } catch {
        setLocalLandmarks(landmarks);
        setLocalRefLines(referenceLines);
      } finally {
        setSaving(false);
      }
    },
    [sessionId, photoId, landmarks, referenceLines, onUpdate],
  );

  const handleMouseUp = useCallback(async () => {
    if (isPanning) {
      setIsPanning(false);
      return;
    }
    if (!dragging) return;
    const lm = localLandmarks[dragging];
    if (!lm) {
      setDragging(null);
      return;
    }

    setDragging(null);
    await saveLandmark(dragging, lm, localLandmarks);
  }, [dragging, isPanning, localLandmarks, saveLandmark]);

  const handleImageClick = useCallback(
    async (e: React.MouseEvent) => {
      if (!placingLandmark || dragging) return;

      const coords = toImageCoords(e.clientX, e.clientY);
      const newLm: LandmarkPoint = {
        x: coords.x,
        y: coords.y,
        confidence: 1.0,
        is_manual: true,
      };

      const updated = { ...localLandmarks, [placingLandmark]: newLm };
      setLocalLandmarks(updated);
      setPlacingLandmark(null);
      await saveLandmark(placingLandmark, newLm, updated);
    },
    [placingLandmark, dragging, toImageCoords, localLandmarks, saveLandmark],
  );

  // Middle-click or right-click to pan
  const handleContainerMouseDown = useCallback(
    (e: React.MouseEvent) => {
      // Middle button (1) or right button with ctrl for panning
      if (e.button === 1 || (e.button === 0 && e.altKey)) {
        e.preventDefault();
        setIsPanning(true);
        panStart.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
      }
    },
    [pan],
  );

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setZoom((prev) => {
      const next = prev * (e.deltaY < 0 ? 1.15 : 1 / 1.15);
      return Math.max(1, Math.min(next, 8));
    });
  }, []);

  const resetZoom = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  // Reset pan when zoom returns to 1
  useEffect(() => {
    if (zoom <= 1) {
      setPan({ x: 0, y: 0 });
    }
  }, [zoom]);

  const cursor = placingLandmark
    ? "crosshair"
    : dragging
      ? "grabbing"
      : isPanning
        ? "grabbing"
        : "default";

  return (
    <div>
      <div style={{ marginBottom: "8px", display: "flex", alignItems: "center", gap: "8px" }}>
        <span style={{ fontWeight: "bold" }}>Landmark Editor</span>
        {saving && <span style={{ color: "#6b7280", fontSize: "14px" }}>Saving...</span>}
        {zoom > 1 && (
          <button
            onClick={resetZoom}
            style={{
              padding: "3px 10px",
              fontSize: "12px",
              border: "1px solid #d1d5db",
              borderRadius: "4px",
              backgroundColor: "#f9fafb",
              cursor: "pointer",
            }}
          >
            Reset Zoom ({zoom.toFixed(1)}x)
          </button>
        )}
        <span style={{ color: "#6b7280", fontSize: "14px" }}>
          Drag landmarks to adjust. Scroll to zoom, Alt+drag to pan.
        </span>
      </div>

      {/* Missing landmarks — click to enter placement mode */}
      {missingLandmarks.length > 0 && (
        <div style={{ marginBottom: "8px" }}>
          <span style={{ fontSize: "13px", color: "#6b7280", marginRight: "8px" }}>
            Place missing:
          </span>
          <div style={{ display: "inline-flex", flexWrap: "wrap", gap: "4px" }}>
            {missingLandmarks.map((name) => (
              <button
                key={name}
                onClick={() => setPlacingLandmark(placingLandmark === name ? null : name)}
                style={{
                  padding: "3px 8px",
                  fontSize: "12px",
                  border: placingLandmark === name ? "2px solid #f97316" : "1px solid #d1d5db",
                  borderRadius: "4px",
                  backgroundColor: placingLandmark === name ? "#fff7ed" : "#f9fafb",
                  color: placingLandmark === name ? "#ea580c" : "#374151",
                  cursor: "pointer",
                  fontWeight: placingLandmark === name ? "bold" : "normal",
                }}
              >
                {name.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </div>
      )}

      {placingLandmark && (
        <div
          style={{
            marginBottom: "8px",
            padding: "8px 12px",
            backgroundColor: "#fff7ed",
            border: "1px solid #fed7aa",
            borderRadius: "6px",
            fontSize: "13px",
            color: "#9a3412",
          }}
        >
          Click on the image to place <strong>{placingLandmark.replace(/_/g, " ")}</strong>.
          Press Escape or click the button again to cancel.
        </div>
      )}

      <div
        ref={containerRef}
        onWheel={handleWheel}
        onMouseDown={handleContainerMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onClick={handleImageClick}
        onContextMenu={(e) => e.preventDefault()}
        onKeyDown={(e) => {
          if (e.key === "Escape") setPlacingLandmark(null);
        }}
        tabIndex={0}
        style={{
          position: "relative",
          width: displayWidth,
          height: displayHeight,
          overflow: "hidden",
          cursor,
          userSelect: "none",
          outline: "none",
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
            alt="Edit landmarks"
            style={{ width: displayWidth, height: displayHeight, display: "block" }}
            draggable={false}
          />
          <svg
            style={{ position: "absolute", top: 0, left: 0, width: displayWidth, height: displayHeight }}
            viewBox={`0 0 ${imageWidth} ${imageHeight}`}
          >
            {/* Reference lines */}
            {Object.entries(localRefLines).map(([name, line]) => {
              if (!line) return null;
              return (
                <line
                  key={name}
                  x1={line.start_point.x}
                  y1={line.start_point.y}
                  x2={line.end_point.x}
                  y2={line.end_point.y}
                  stroke="#ffffff80"
                  strokeWidth={1}
                  strokeDasharray="4,2"
                />
              );
            })}

            {/* Patient orientation labels */}
            <text x={20} y={40} fill="white" fontSize={28} fontWeight="bold" opacity={0.7}
              stroke="black" strokeWidth={0.5}>R</text>
            <text x={imageWidth - 40} y={40} fill="white" fontSize={28} fontWeight="bold" opacity={0.7}
              stroke="black" strokeWidth={0.5}>L</text>

            {/* Draggable landmarks */}
            {Object.entries(localLandmarks).map(([name, lm]) => (
              <g
                key={name}
                onMouseDown={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  handleMouseDown(name);
                }}
                style={{ cursor: "grab" }}
              >
                <circle cx={lm.x} cy={lm.y} r={12} fill="transparent" />
                <circle
                  cx={lm.x}
                  cy={lm.y}
                  r={6}
                  fill={lm.is_manual ? "#ff6600" : "#00ff00"}
                  stroke="white"
                  strokeWidth={2}
                />
                <text x={lm.x + 10} y={lm.y - 5} fill="white" fontSize={10} stroke="black" strokeWidth={0.3}>
                  {name.replace(/_/g, " ")}
                </text>
              </g>
            ))}
          </svg>
        </div>
      </div>

      {/* Placement hint */}
      <div
        style={{
          marginTop: "12px",
          padding: "12px",
          backgroundColor: "#fef3c7",
          borderRadius: "6px",
          fontSize: "14px",
        }}
      >
        <strong>Tip:</strong> Tragus and porion landmarks are not automatically detected.
        Select them from the buttons above, then click on the image to place them. The tragus
        is the small pointed cartilage flap in front of the ear canal.
      </div>
    </div>
  );
}
