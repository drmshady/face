/** Alignment preview with reference planes on scan (T060). */

import { useCallback } from "react";
import { StlViewer } from "./StlViewer";
import type { AlignmentResult, IntraOralMarker, Landmark3DInScan, Plane3D } from "../types";

interface AlignmentPreviewProps {
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
  key: keyof AlignmentResult["reference_planes_in_scan"];
  color: string;
  label: string;
}> = [
  { key: "interpupillary_plane", color: "#3b82f6", label: "Interpupillary" },
  { key: "frankfort_plane", color: "#22c55e", label: "Frankfort" },
  { key: "ala_tragus_plane", color: "#f97316", label: "Ala-Tragus" },
  { key: "canthus_tragus_plane", color: "#a855f7", label: "Canthus-Tragus" },
];

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
  stlBlob,
  markers = [],
  alignment,
  forkStlBlob,
  scanStlBlob,
  landmarks3d,
  onApprove,
  onReject,
}: AlignmentPreviewProps) {
  const planes = PLANE_COLORS.map(({ key, color, label }) => ({
    plane: alignment.reference_planes_in_scan[key] as Plane3D | undefined,
    color,
    label,
  })).filter((p): p is { plane: Plane3D; color: string; label: string } => p.plane != null);

  const handleExportFork = useCallback((blob: Blob) => {
    const link = document.createElement("a");
    link.download = "aligned-fork.stl";
    link.href = URL.createObjectURL(blob);
    link.click();
    URL.revokeObjectURL(link.href);
  }, []);

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
          <div>
            <strong>Registration RMSD:</strong> {alignment.registration_rmsd_mm.toFixed(3)} mm
          </div>
        </div>

        {/* Plane legend */}
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
          {PLANE_COLORS.map(({ key, color, label }) => {
            const plane = alignment.reference_planes_in_scan[key];
            return (
              <div key={key} style={{ display: "flex", alignItems: "center", gap: "4px", opacity: plane ? 1 : 0.4 }}>
                <span style={{ width: "12px", height: "12px", borderRadius: "2px", backgroundColor: color, display: "inline-block" }} />
                <span style={{ fontSize: "0.85em" }}>{label}</span>
                {!plane && <span style={{ fontSize: "0.75em", color: "#999" }}>(N/A)</span>}
              </div>
            );
          })}
        </div>

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
      </div>
    </div>
  );
}
