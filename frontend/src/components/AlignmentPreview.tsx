/** Alignment preview with reference planes on scan (T060, T020). */

import { useCallback, useState } from "react";
import { StlViewer } from "./StlViewer";
import { exportAlignmentJson, exportCombinedStl } from "../services/api";
import type { AlignmentResult, IntraOralMarker, Landmark3DInScan, Plane3D } from "../types";

interface AlignmentPreviewProps {
  sessionId: string;
  stlBlob?: Blob;
  markers?: IntraOralMarker[];
  alignment: AlignmentResult;
  forkStlBlob?: Blob;
  scanStlBlob?: Blob;
  landmarks3d?: Landmark3DInScan[];
  onApprove: () => void;
  onReject: () => void;
}

const PLANE_COLORS: Array<{
  key: keyof NonNullable<AlignmentResult["reference_planes_in_scan"]>;
  color: string;
  label: string;
}> = [
  { key: "interpupillary_plane", color: "#3b82f6", label: "Interpupillary" },
  { key: "frankfort_plane", color: "#22c55e", label: "Frankfort" },
  { key: "ala_tragus_plane", color: "#f97316", label: "Ala-Tragus" },
  { key: "canthus_tragus_plane", color: "#a855f7", label: "Canthus-Tragus" },
];

function ConfidenceBadge({ label, confidence }: { label: string; confidence: number }) {
  const level = confidence > 0.8 ? "High" : confidence > 0.5 ? "Medium" : "Low";
  const colors = {
    High: { bg: "#dcfce7", text: "#166534" },
    Medium: { bg: "#fef9c3", text: "#854d0e" },
    Low: { bg: "#fee2e2", text: "#991b1b" },
  };
  const c = colors[level];
  return (
    <span style={{
      padding: "3px 10px",
      borderRadius: "10px",
      fontSize: "0.8em",
      fontWeight: "bold",
      backgroundColor: c.bg,
      color: c.text,
    }}>
      {label}: {level} ({(confidence * 100).toFixed(0)}%)
    </span>
  );
}

function QualityBadge({ quality }: { quality: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    good: { bg: "#dcfce7", text: "#166534" },
    acceptable: { bg: "#fef9c3", text: "#854d0e" },
    poor: { bg: "#fee2e2", text: "#991b1b" },
  };
  const c = colors[quality] ?? colors.poor;
  return (
    <span style={{ padding: "4px 12px", borderRadius: "12px", backgroundColor: c!.bg, color: c!.text, fontWeight: "bold" }}>
      {quality.toUpperCase()}
    </span>
  );
}

export function AlignmentPreview({
  sessionId,
  stlBlob,
  markers = [],
  alignment,
  forkStlBlob,
  scanStlBlob,
  landmarks3d,
  onApprove,
  onReject,
}: AlignmentPreviewProps) {
  const refPlanes = alignment.reference_planes_in_scan;
  const planes = refPlanes
    ? PLANE_COLORS.map(({ key, color, label }) => ({
        plane: refPlanes[key] as Plane3D | undefined,
        color,
        label,
      })).filter((p): p is { plane: Plane3D; color: string; label: string } => p.plane != null)
    : [];

  const [exporting, setExporting] = useState(false);
  const [exportingJson, setExportingJson] = useState(false);

  const handleExportFork = useCallback((blob: Blob) => {
    const link = document.createElement("a");
    link.download = "aligned-fork.stl";
    link.href = URL.createObjectURL(blob);
    link.click();
    URL.revokeObjectURL(link.href);
  }, []);

  const handleExportCombined = useCallback(async () => {
    if (!sessionId) return;
    setExporting(true);
    try {
      const blob = await exportCombinedStl(sessionId, {});
      const link = document.createElement("a");
      link.download = `alignment-${sessionId.slice(0, 8)}.stl`;
      link.href = URL.createObjectURL(blob);
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (err) {
      console.error("Export failed:", err);
    } finally {
      setExporting(false);
    }
  }, [sessionId]);

  const handleExportJson = useCallback(async () => {
    if (!sessionId) return;
    setExportingJson(true);
    try {
      const blob = await exportAlignmentJson(sessionId);
      const link = document.createElement("a");
      link.download = `alignment-${sessionId.slice(0, 8)}.json`;
      link.href = URL.createObjectURL(blob);
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (err) {
      console.error("JSON export failed:", err);
    } finally {
      setExportingJson(false);
    }
  }, [sessionId]);

  // Prefer scanStlBlob over stlBlob for the scan mesh
  const scanBlob = scanStlBlob ?? stlBlob;

  return (
    <div>
      <StlViewer
        stlBlob={scanBlob}
        markers={markers}
        planes={planes}
        forkStlBlob={forkStlBlob}
        forkTransformMatrix={alignment.t2_fork_to_scan}
        landmarks3d={landmarks3d ?? alignment.landmarks_3d_in_scan}
        landmarks3dFork={alignment.landmarks_3d_in_fork}
        apriltags={alignment.apriltags_in_fork}
        interpupillaryLine={alignment.interpupillary_line_3d}
        midlinePlane={alignment.midline_plane_3d}
        onExportFork={forkStlBlob ? handleExportFork : undefined}
      />

      {/* Quality metrics */}
      <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
          <div>
            <strong>Quality:</strong> <QualityBadge quality={alignment.quality} />
          </div>
          <div>
            <strong>Reprojection error:</strong> {alignment.reprojection_error_px.toFixed(2)} px
          </div>
          {alignment.registration_rmsd_mm != null && (
            <div>
              <strong>Registration RMSD:</strong> {alignment.registration_rmsd_mm.toFixed(3)} mm
            </div>
          )}
          {alignment.scale_deviation_pct != null && (
            <div>
              <strong>Scale deviation:</strong>{" "}
              <span style={{ color: alignment.scale_deviation_pct > 2 ? "#ef4444" : "#22c55e" }}>
                {alignment.scale_deviation_pct.toFixed(1)}%
              </span>
            </div>
          )}
          {alignment.interpupillary_line_3d && (
            <div>
              <strong>IPD:</strong> {alignment.interpupillary_line_3d.length_mm.toFixed(1)} mm
            </div>
          )}
        </div>

        {/* T028: Confidence indicators */}
        {(alignment.interpupillary_line_3d || alignment.midline_plane_3d || alignment.triangulation_method) && (
          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", alignItems: "center" }}>
            {alignment.interpupillary_line_3d && (
              <ConfidenceBadge label="IPD" confidence={alignment.interpupillary_line_3d.confidence} />
            )}
            {alignment.midline_plane_3d && (
              <ConfidenceBadge label="Midline" confidence={alignment.midline_plane_3d.confidence} />
            )}
            {alignment.triangulation_method && (
              <span style={{
                padding: "3px 10px",
                borderRadius: "10px",
                fontSize: "0.8em",
                fontWeight: "bold",
                backgroundColor: "#f0f0f0",
                color: "#555",
              }}>
                {alignment.triangulation_method === "bundle_adjusted" ? "Bundle Adjusted"
                  : alignment.triangulation_method === "mediapipe_z" ? "Single Photo"
                  : "Constant Depth"}
              </span>
            )}
            {alignment.scale_deviation_pct != null && alignment.scale_deviation_pct > 2 && (
              <span style={{
                padding: "3px 10px",
                borderRadius: "10px",
                fontSize: "0.8em",
                fontWeight: "bold",
                backgroundColor: "#fee2e2",
                color: "#991b1b",
              }}>
                Scale Warning
              </span>
            )}
          </div>
        )}

        {/* Plane legend */}
        {refPlanes && <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
          {PLANE_COLORS.map(({ key, color, label }) => {
            const plane = refPlanes[key];
            return (
              <div key={key} style={{ display: "flex", alignItems: "center", gap: "4px", opacity: plane ? 1 : 0.4 }}>
                <span style={{ width: "12px", height: "12px", borderRadius: "2px", backgroundColor: color, display: "inline-block" }} />
                <span style={{ fontSize: "0.85em" }}>{label}</span>
                {!plane && <span style={{ fontSize: "0.75em", color: "#999" }}>(N/A)</span>}
              </div>
            );
          })}
        </div>}

        {/* Actions */}
        <div style={{ display: "flex", gap: "12px", marginTop: "8px" }}>
          <button
            onClick={onApprove}
            style={{
              padding: "10px 24px",
              backgroundColor: "#22c55e",
              color: "white",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
              fontWeight: "bold",
            }}
          >
            Approve Alignment
          </button>
          <button
            onClick={onReject}
            style={{
              padding: "10px 24px",
              backgroundColor: "#ef4444",
              color: "white",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
            }}
          >
            Re-analyze
          </button>
        </div>

        {/* Export */}
        <div style={{ borderTop: "1px solid #e5e7eb", paddingTop: "16px", marginTop: "16px" }}>
          <h4 style={{ margin: "0 0 8px 0", fontSize: "1em" }}>Export</h4>
          <p style={{ margin: "0 0 12px 0", fontSize: "0.85em", color: "#666" }}>
            Interpupillary line + midline plane
          </p>
          <div style={{ display: "flex", gap: "12px" }}>
            <button
              onClick={handleExportCombined}
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
            <button
              onClick={handleExportJson}
              disabled={exportingJson}
              style={{
                padding: "10px 24px",
                backgroundColor: "#6366f1",
                color: "white",
                border: "none",
                borderRadius: "6px",
                cursor: exportingJson ? "not-allowed" : "pointer",
                opacity: exportingJson ? 0.7 : 1,
              }}
            >
              {exportingJson ? "Exporting..." : "Download JSON"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
