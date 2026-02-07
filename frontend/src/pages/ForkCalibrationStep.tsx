/** ForkCalibrationStep: page for uploading fork STL and configuring geometry. */

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ForkStlViewer } from "../components/ForkStlViewer";
import type { PlacingMode } from "../components/ForkStlViewer";
import {
  getForkGeometry,
  getForkStl,
  saveForkConfig,
  uploadFork,
} from "../services/api";
import type { ForkGeometry, HexPostMarker3D, Point3D } from "../types";

interface PlacedTag {
  tag_id: number;
  center: Point3D;
  normal: Point3D;
}

export function ForkCalibrationStep() {
  const [stlBlob, setStlBlob] = useState<Blob | null>(null);
  const [markers, setMarkers] = useState<HexPostMarker3D[]>([]);
  const [plateNormal, setPlateNormal] = useState<number[]>([0, 0, 1]);
  const [placedTags, setPlacedTags] = useState<PlacedTag[]>([]);
  const [placingMode, setPlacingMode] = useState<PlacingMode>(null);
  const [tagSizeMm, setTagSizeMm] = useState(7);
  const [nextMarkerId, setNextMarkerId] = useState(0);
  const [editingMarkerId, setEditingMarkerId] = useState<number | null>(null);
  const [editingTagId, setEditingTagId] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadPhase, setUploadPhase] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedGeometry, setSavedGeometry] = useState<ForkGeometry | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Load existing geometry and STL on mount
  useEffect(() => {
    getForkGeometry().then(async (geo) => {
      if (geo) {
        setSavedGeometry(geo);
        // Restore placed tags from saved geometry
        setPlacedTags(
          geo.apriltags.map((t) => ({
            tag_id: t.tag_id,
            center: t.center_mm,
            normal: t.normal,
          })),
        );
        setPlateNormal(geo.plate_normal);
        setMarkers(geo.intraoral_markers);
        const maxId = geo.intraoral_markers.reduce(
          (max, m) => Math.max(max, m.marker_id),
          -1,
        );
        setNextMarkerId(maxId + 1);

        // Also load the STL blob so the 3D viewer renders
        try {
          const blob = await getForkStl();
          setStlBlob(blob);
          setStatusMessage(
            `Loaded saved fork geometry: ${geo.apriltags.length} tags, ${geo.intraoral_markers.length} hex posts.`,
          );
        } catch {
          // STL may not be available if server restarted — user can re-upload
          setStatusMessage(
            "Saved geometry loaded but fork STL not found. Please re-upload the STL file.",
          );
        }
      }
    });
  }, []);

  const handleFileUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      setUploading(true);
      setUploadProgress(0);
      setUploadPhase("Uploading file...");
      setError(null);
      setStatusMessage(null);

      try {
        const result = await uploadFork(file, (pct, phase) => {
          setUploadProgress(pct);
          setUploadPhase(phase);
        });
        setUploadPhase("Loading 3D viewer...");
        setUploadProgress(90);
        setMarkers(result.markers);
        setPlateNormal(result.plate_normal);
        setPlacedTags([]);
        const maxId = result.markers.reduce(
          (max, m) => Math.max(max, m.marker_id),
          -1,
        );
        setNextMarkerId(maxId + 1);

        // Get the STL blob for the viewer
        const blob = await getForkStl();
        setStlBlob(blob);
        setUploadProgress(100);

        setStatusMessage(
          `Loaded fork: ${result.vertex_count} vertices, ${result.face_count} faces. ` +
            `Detected ${result.markers.length} hex post marker(s).`,
        );
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to upload fork STL",
        );
      } finally {
        setUploading(false);
        setUploadProgress(0);
        setUploadPhase("");
      }
    },
    [],
  );

  const handleTagPlaced = useCallback(
    (tagId: number, center: Point3D, normal: Point3D) => {
      setPlacedTags((prev) => {
        const filtered = prev.filter((t) => t.tag_id !== tagId);
        return [...filtered, { tag_id: tagId, center, normal }];
      });
      setPlacingMode(null);
    },
    [],
  );

  const handleHexPlaced = useCallback(
    (center: Point3D, normal: Point3D) => {
      const markerId = nextMarkerId;
      setMarkers((prev) => [
        ...prev,
        {
          marker_id: markerId,
          center,
          top_face_normal: normal,
          radius_mm: 2.5,
          height_mm: 3.0,
          confidence: 1.0,
        },
      ]);
      setNextMarkerId((id) => id + 1);
      setPlacingMode(null);
    },
    [nextMarkerId],
  );

  const handleRemoveMarker = useCallback((markerId: number) => {
    setMarkers((prev) => prev.filter((m) => m.marker_id !== markerId));
    setEditingMarkerId(null);
  }, []);

  const handleUpdateMarker = useCallback(
    (markerId: number, field: string, value: number) => {
      setMarkers((prev) =>
        prev.map((m) => {
          if (m.marker_id !== markerId) return m;
          if (field === "marker_id") return { ...m, marker_id: value };
          if (field === "height_mm") return { ...m, height_mm: value };
          if (field === "od") return { ...m, radius_mm: value / 2 };
          if (field === "cx") return { ...m, center: { ...m.center, x: value } };
          if (field === "cy") return { ...m, center: { ...m.center, y: value } };
          if (field === "cz") return { ...m, center: { ...m.center, z: value } };
          if (field === "nx") return { ...m, top_face_normal: { ...m.top_face_normal, x: value } };
          if (field === "ny") return { ...m, top_face_normal: { ...m.top_face_normal, y: value } };
          if (field === "nz") return { ...m, top_face_normal: { ...m.top_face_normal, z: value } };
          return m;
        }),
      );
    },
    [],
  );

  const handleUpdateTag = useCallback(
    (tagId: number, field: string, value: number) => {
      setPlacedTags((prev) =>
        prev.map((t) => {
          if (t.tag_id !== tagId) return t;
          if (field === "tag_id") return { ...t, tag_id: value };
          if (field === "cx") return { ...t, center: { ...t.center, x: value } };
          if (field === "cy") return { ...t, center: { ...t.center, y: value } };
          if (field === "cz") return { ...t, center: { ...t.center, z: value } };
          if (field === "nx") return { ...t, normal: { ...t.normal, x: value } };
          if (field === "ny") return { ...t, normal: { ...t.normal, y: value } };
          if (field === "nz") return { ...t, normal: { ...t.normal, z: value } };
          return t;
        }),
      );
    },
    [],
  );

  const handleRemoveTag = useCallback((tagId: number) => {
    setPlacedTags((prev) => prev.filter((t) => t.tag_id !== tagId));
    setEditingTagId(null);
  }, []);

  const handleSave = useCallback(async () => {
    if (placedTags.length < 2) {
      setError("Please place both AprilTag markers before saving.");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const geometry = await saveForkConfig({
        apriltags: placedTags.map((t) => ({
          tag_id: t.tag_id,
          center_mm: t.center,
          normal: t.normal,
        })),
        tag_size_mm: tagSizeMm,
        markers,
        plate_normal: plateNormal,
      });
      setSavedGeometry(geometry);
      setStatusMessage("Fork geometry saved successfully.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to save configuration",
      );
    } finally {
      setSaving(false);
    }
  }, [placedTags, tagSizeMm, markers, plateNormal]);

  const navigate = useNavigate();
  const tag0 = placedTags.find((t) => t.tag_id === 0);
  const tag1 = placedTags.find((t) => t.tag_id === 1);

  return (
    <div style={{ padding: "24px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px" }}>
        <button
          onClick={() => navigate(-1)}
          style={{
            padding: "4px 12px",
            border: "1px solid #d1d5db",
            borderRadius: "6px",
            backgroundColor: "#ffffff",
            cursor: "pointer",
            fontSize: "14px",
            color: "#374151",
          }}
        >
          &larr; Back
        </button>
        <Link to="/" style={{ fontSize: "14px", color: "#6b7280", textDecoration: "none" }}>
          Home
        </Link>
        <h2 style={{ margin: 0 }}>Fork Calibration</h2>
      </div>
      <p style={{ color: "#6b7280", marginBottom: "16px" }}>
        Upload the fork STL file to auto-detect hex post markers, then click on
        the 3D model to place the two AprilTag positions.
      </p>

      {/* Upload section */}
      <div
        style={{
          marginBottom: "16px",
          padding: "16px",
          border: "1px solid #d1d5db",
          borderRadius: "8px",
          backgroundColor: "#f9fafb",
        }}
      >
        <label style={{ fontWeight: "bold", marginRight: "12px" }}>
          Fork STL File:
        </label>
        <input
          type="file"
          accept=".stl"
          onChange={handleFileUpload}
          disabled={uploading}
        />
        {uploading && (
          <div style={{ marginTop: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "6px" }}>
              <span style={{ fontSize: "14px", color: "#374151" }}>{uploadPhase}</span>
              <span style={{ fontSize: "13px", color: "#6b7280" }}>{uploadProgress}%</span>
            </div>
            <div
              style={{
                width: "100%",
                height: "8px",
                backgroundColor: "#e5e7eb",
                borderRadius: "4px",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${uploadProgress}%`,
                  height: "100%",
                  backgroundColor: uploadProgress < 50 ? "#3b82f6" : "#22c55e",
                  borderRadius: "4px",
                  transition: "width 0.3s ease",
                }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Status/error messages */}
      {error && (
        <div
          style={{
            marginBottom: "16px",
            padding: "12px",
            backgroundColor: "#fef2f2",
            border: "1px solid #fecaca",
            borderRadius: "6px",
            color: "#b91c1c",
          }}
        >
          {error}
        </div>
      )}
      {statusMessage && (
        <div
          style={{
            marginBottom: "16px",
            padding: "12px",
            backgroundColor: "#f0fdf4",
            border: "1px solid #bbf7d0",
            borderRadius: "6px",
            color: "#166534",
          }}
        >
          {statusMessage}
        </div>
      )}

      {/* Existing geometry notice */}
      {savedGeometry && !stlBlob && (
        <div
          style={{
            marginBottom: "16px",
            padding: "12px",
            backgroundColor: "#eff6ff",
            border: "1px solid #bfdbfe",
            borderRadius: "6px",
            color: "#1e40af",
          }}
        >
          Fork geometry already configured (saved{" "}
          {new Date(savedGeometry.created_at).toLocaleString()}).{" "}
          {savedGeometry.apriltags.length} AprilTag(s),{" "}
          {savedGeometry.intraoral_markers.length} intra-oral marker(s).
          Upload a new STL to recalibrate.
        </div>
      )}

      {/* 3D Viewer */}
      <ForkStlViewer
        stlBlob={stlBlob}
        markers={markers}
        placedTags={placedTags}
        placingMode={placingMode}
        onTagPlaced={handleTagPlaced}
        onHexPlaced={handleHexPlaced}
      />

      {/* Tag placement controls */}
      {stlBlob && (
        <div
          style={{
            marginTop: "16px",
            padding: "16px",
            border: "1px solid #d1d5db",
            borderRadius: "8px",
            backgroundColor: "#f9fafb",
          }}
        >
          <h3 style={{ marginBottom: "12px" }}>AprilTag Placement</h3>
          <p style={{ color: "#6b7280", fontSize: "14px", marginBottom: "12px" }}>
            Click a button below, then click on the fork model to place the marker.
          </p>

          <div
            style={{
              display: "flex",
              gap: "12px",
              alignItems: "center",
              flexWrap: "wrap",
              marginBottom: "12px",
            }}
          >
            <button
              onClick={() =>
                setPlacingMode(
                  placingMode?.type === "tag" && placingMode.id === 0
                    ? null
                    : { type: "tag", id: 0 },
                )
              }
              style={{
                padding: "8px 16px",
                border:
                  placingMode?.type === "tag" && placingMode.id === 0
                    ? "2px solid #3b82f6"
                    : "1px solid #d1d5db",
                borderRadius: "6px",
                backgroundColor:
                  placingMode?.type === "tag" && placingMode.id === 0
                    ? "#eff6ff"
                    : tag0
                      ? "#f0fdf4"
                      : "#ffffff",
                cursor: "pointer",
                fontWeight:
                  placingMode?.type === "tag" && placingMode.id === 0
                    ? "bold"
                    : "normal",
                color:
                  placingMode?.type === "tag" && placingMode.id === 0
                    ? "#1d4ed8"
                    : "#374151",
              }}
            >
              {tag0 ? "Tag 1 placed" : "Place Tag 1"}
            </button>

            <button
              onClick={() =>
                setPlacingMode(
                  placingMode?.type === "tag" && placingMode.id === 1
                    ? null
                    : { type: "tag", id: 1 },
                )
              }
              style={{
                padding: "8px 16px",
                border:
                  placingMode?.type === "tag" && placingMode.id === 1
                    ? "2px solid #f97316"
                    : "1px solid #d1d5db",
                borderRadius: "6px",
                backgroundColor:
                  placingMode?.type === "tag" && placingMode.id === 1
                    ? "#fff7ed"
                    : tag1
                      ? "#f0fdf4"
                      : "#ffffff",
                cursor: "pointer",
                fontWeight:
                  placingMode?.type === "tag" && placingMode.id === 1
                    ? "bold"
                    : "normal",
                color:
                  placingMode?.type === "tag" && placingMode.id === 1
                    ? "#c2410c"
                    : "#374151",
              }}
            >
              {tag1 ? "Tag 2 placed" : "Place Tag 2"}
            </button>

            <button
              onClick={() =>
                setPlacingMode(
                  placingMode?.type === "hex" ? null : { type: "hex" },
                )
              }
              style={{
                padding: "8px 16px",
                border:
                  placingMode?.type === "hex"
                    ? "2px solid #22c55e"
                    : "1px solid #d1d5db",
                borderRadius: "6px",
                backgroundColor:
                  placingMode?.type === "hex" ? "#f0fdf4" : "#ffffff",
                cursor: "pointer",
                fontWeight: placingMode?.type === "hex" ? "bold" : "normal",
                color: placingMode?.type === "hex" ? "#166534" : "#374151",
              }}
            >
              + Add Hex Post
            </button>

            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <label style={{ fontSize: "14px", color: "#6b7280" }}>
                Tag size (mm):
              </label>
              <input
                type="number"
                value={tagSizeMm}
                onChange={(e) => setTagSizeMm(Number(e.target.value))}
                style={{
                  width: "60px",
                  padding: "4px 8px",
                  border: "1px solid #d1d5db",
                  borderRadius: "4px",
                }}
                min={1}
                max={50}
              />
            </div>
          </div>

          {placingMode !== null && (
            <div
              style={{
                padding: "8px 12px",
                backgroundColor: "#fef3c7",
                border: "1px solid #fde68a",
                borderRadius: "6px",
                fontSize: "13px",
                color: "#92400e",
                marginBottom: "12px",
              }}
            >
              {placingMode.type === "tag" ? (
                <>
                  Click on the fork model to place{" "}
                  <strong>Tag {placingMode.id + 1}</strong>. Click the button
                  again to cancel.
                </>
              ) : (
                <>
                  Click on the fork model to place a <strong>hex post</strong>.
                  Click the button again to cancel.
                </>
              )}
            </div>
          )}

          {/* Placed tag coordinates */}
          {placedTags.length > 0 && (
            <div style={{ fontSize: "13px", color: "#6b7280" }}>
              {placedTags
                .sort((a, b) => a.tag_id - b.tag_id)
                .map((tag) => (
                  <div
                    key={tag.tag_id}
                    style={{
                      marginBottom: "6px",
                      padding: "8px",
                      border: editingTagId === tag.tag_id ? "1px solid #3b82f6" : "1px solid #e5e7eb",
                      borderRadius: "6px",
                      backgroundColor: editingTagId === tag.tag_id ? "#f8fafc" : "transparent",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: editingTagId === tag.tag_id ? "8px" : "0" }}>
                      <span style={{ fontWeight: "bold", color: tag.tag_id === 0 ? "#1d4ed8" : "#c2410c" }}>
                        Tag {tag.tag_id + 1}
                      </span>
                      <span>
                        ({tag.center.x.toFixed(1)}, {tag.center.y.toFixed(1)},{" "}
                        {tag.center.z.toFixed(1)}) mm
                      </span>
                      <button
                        onClick={() =>
                          setEditingTagId(
                            editingTagId === tag.tag_id ? null : tag.tag_id,
                          )
                        }
                        style={{
                          padding: "2px 8px",
                          border: "1px solid #d1d5db",
                          borderRadius: "4px",
                          backgroundColor: "#ffffff",
                          cursor: "pointer",
                          fontSize: "12px",
                          color: "#374151",
                        }}
                      >
                        {editingTagId === tag.tag_id ? "Done" : "Edit"}
                      </button>
                      <button
                        onClick={() => handleRemoveTag(tag.tag_id)}
                        style={{
                          padding: "2px 8px",
                          border: "1px solid #fecaca",
                          borderRadius: "4px",
                          backgroundColor: "#fef2f2",
                          cursor: "pointer",
                          fontSize: "12px",
                          color: "#b91c1c",
                        }}
                      >
                        Remove
                      </button>
                    </div>
                    {editingTagId === tag.tag_id && (
                      <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "12px" }}>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                          <span style={{ fontWeight: "bold", width: "50px" }}>Tag ID:</span>
                          <input
                            type="number"
                            step="1"
                            min="0"
                            value={tag.tag_id}
                            onChange={(e) =>
                              handleUpdateTag(tag.tag_id, "tag_id", Number(e.target.value))
                            }
                            style={{ width: "60px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                          />
                        </div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                          <span style={{ fontWeight: "bold", width: "50px" }}>Center:</span>
                          <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                            X:
                            <input
                              type="number"
                              step="0.1"
                              value={tag.center.x}
                              onChange={(e) =>
                                handleUpdateTag(tag.tag_id, "cx", Number(e.target.value))
                              }
                              style={{ width: "70px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                            />
                          </label>
                          <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                            Y:
                            <input
                              type="number"
                              step="0.1"
                              value={tag.center.y}
                              onChange={(e) =>
                                handleUpdateTag(tag.tag_id, "cy", Number(e.target.value))
                              }
                              style={{ width: "70px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                            />
                          </label>
                          <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                            Z:
                            <input
                              type="number"
                              step="0.1"
                              value={tag.center.z}
                              onChange={(e) =>
                                handleUpdateTag(tag.tag_id, "cz", Number(e.target.value))
                              }
                              style={{ width: "70px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                            />
                          </label>
                        </div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                          <span style={{ fontWeight: "bold", width: "50px" }}>Normal:</span>
                          <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                            X:
                            <input
                              type="number"
                              step="0.01"
                              value={tag.normal.x}
                              onChange={(e) =>
                                handleUpdateTag(tag.tag_id, "nx", Number(e.target.value))
                              }
                              style={{ width: "70px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                            />
                          </label>
                          <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                            Y:
                            <input
                              type="number"
                              step="0.01"
                              value={tag.normal.y}
                              onChange={(e) =>
                                handleUpdateTag(tag.tag_id, "ny", Number(e.target.value))
                              }
                              style={{ width: "70px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                            />
                          </label>
                          <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                            Z:
                            <input
                              type="number"
                              step="0.01"
                              value={tag.normal.z}
                              onChange={(e) =>
                                handleUpdateTag(tag.tag_id, "nz", Number(e.target.value))
                              }
                              style={{ width: "70px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                            />
                          </label>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
            </div>
          )}

          {/* Hex post markers list */}
          {markers.length > 0 && (
            <div
              style={{
                marginTop: "12px",
                fontSize: "13px",
                color: "#6b7280",
              }}
            >
              <strong>Hex posts:</strong> {markers.length}
              {markers.map((m) => (
                <div
                  key={m.marker_id}
                  style={{
                    marginLeft: "12px",
                    marginTop: "6px",
                    padding: "8px",
                    border: editingMarkerId === m.marker_id ? "1px solid #3b82f6" : "1px solid #e5e7eb",
                    borderRadius: "6px",
                    backgroundColor: editingMarkerId === m.marker_id ? "#f8fafc" : "transparent",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: editingMarkerId === m.marker_id ? "8px" : "0" }}>
                    <span style={{ fontWeight: "bold" }}>
                      Post {m.marker_id}
                      {m.confidence < 1.0 && (
                        <span style={{ color: "#9ca3af", fontWeight: "normal" }}>
                          {" "}(auto, {(m.confidence * 100).toFixed(0)}%)
                        </span>
                      )}
                      {m.confidence >= 1.0 && (
                        <span style={{ color: "#22c55e", fontWeight: "normal" }}>
                          {" "}(manual)
                        </span>
                      )}
                    </span>
                    <span>
                      ({m.center.x.toFixed(1)}, {m.center.y.toFixed(1)},{" "}
                      {m.center.z.toFixed(1)}) mm
                    </span>
                    <span>
                      OD={( m.radius_mm * 2).toFixed(1)} h={m.height_mm.toFixed(1)}
                    </span>
                    <button
                      onClick={() =>
                        setEditingMarkerId(
                          editingMarkerId === m.marker_id ? null : m.marker_id,
                        )
                      }
                      style={{
                        padding: "2px 8px",
                        border: "1px solid #d1d5db",
                        borderRadius: "4px",
                        backgroundColor: "#ffffff",
                        cursor: "pointer",
                        fontSize: "12px",
                        color: "#374151",
                      }}
                    >
                      {editingMarkerId === m.marker_id ? "Done" : "Edit"}
                    </button>
                    <button
                      onClick={() => handleRemoveMarker(m.marker_id)}
                      style={{
                        padding: "2px 8px",
                        border: "1px solid #fecaca",
                        borderRadius: "4px",
                        backgroundColor: "#fef2f2",
                        cursor: "pointer",
                        fontSize: "12px",
                        color: "#b91c1c",
                      }}
                    >
                      Remove
                    </button>
                  </div>
                  {editingMarkerId === m.marker_id && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "12px" }}>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                        <span style={{ fontWeight: "bold", width: "50px" }}>ID:</span>
                        <input
                          type="number"
                          step="1"
                          min="0"
                          value={m.marker_id}
                          onChange={(e) =>
                            handleUpdateMarker(m.marker_id, "marker_id", Number(e.target.value))
                          }
                          style={{ width: "60px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                        />
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                        <span style={{ fontWeight: "bold", width: "50px" }}>Center:</span>
                        <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                          X:
                          <input
                            type="number"
                            step="0.1"
                            value={m.center.x}
                            onChange={(e) =>
                              handleUpdateMarker(m.marker_id, "cx", Number(e.target.value))
                            }
                            style={{ width: "70px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                          />
                        </label>
                        <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                          Y:
                          <input
                            type="number"
                            step="0.1"
                            value={m.center.y}
                            onChange={(e) =>
                              handleUpdateMarker(m.marker_id, "cy", Number(e.target.value))
                            }
                            style={{ width: "70px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                          />
                        </label>
                        <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                          Z:
                          <input
                            type="number"
                            step="0.1"
                            value={m.center.z}
                            onChange={(e) =>
                              handleUpdateMarker(m.marker_id, "cz", Number(e.target.value))
                            }
                            style={{ width: "70px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                          />
                        </label>
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                        <span style={{ fontWeight: "bold", width: "50px" }}>Normal:</span>
                        <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                          X:
                          <input
                            type="number"
                            step="0.01"
                            value={m.top_face_normal.x}
                            onChange={(e) =>
                              handleUpdateMarker(m.marker_id, "nx", Number(e.target.value))
                            }
                            style={{ width: "70px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                          />
                        </label>
                        <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                          Y:
                          <input
                            type="number"
                            step="0.01"
                            value={m.top_face_normal.y}
                            onChange={(e) =>
                              handleUpdateMarker(m.marker_id, "ny", Number(e.target.value))
                            }
                            style={{ width: "70px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                          />
                        </label>
                        <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                          Z:
                          <input
                            type="number"
                            step="0.01"
                            value={m.top_face_normal.z}
                            onChange={(e) =>
                              handleUpdateMarker(m.marker_id, "nz", Number(e.target.value))
                            }
                            style={{ width: "70px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                          />
                        </label>
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
                        <span style={{ fontWeight: "bold", width: "50px" }}>Size:</span>
                        <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                          OD:
                          <input
                            type="number"
                            step="0.1"
                            min="0.1"
                            value={Number((m.radius_mm * 2).toFixed(3))}
                            onChange={(e) =>
                              handleUpdateMarker(m.marker_id, "od", Number(e.target.value))
                            }
                            style={{ width: "60px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                          />
                        </label>
                        <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                          Height:
                          <input
                            type="number"
                            step="0.1"
                            min="0.1"
                            value={m.height_mm}
                            onChange={(e) =>
                              handleUpdateMarker(m.marker_id, "height_mm", Number(e.target.value))
                            }
                            style={{ width: "60px", padding: "2px 4px", border: "1px solid #d1d5db", borderRadius: "3px" }}
                          />
                        </label>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Save button */}
          <div style={{ marginTop: "16px" }}>
            <button
              onClick={handleSave}
              disabled={saving || placedTags.length < 2}
              style={{
                padding: "10px 24px",
                backgroundColor:
                  placedTags.length >= 2 ? "#2563eb" : "#9ca3af",
                color: "white",
                border: "none",
                borderRadius: "6px",
                cursor:
                  placedTags.length >= 2 && !saving
                    ? "pointer"
                    : "not-allowed",
                fontWeight: "bold",
                fontSize: "14px",
              }}
            >
              {saving ? "Saving..." : "Save Fork Geometry"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
