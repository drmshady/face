/** Alignment review page — workflow step 4 (T062). */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSessionContext } from "../App";
import { AlignmentPreview } from "../components/AlignmentPreview";
import * as api from "../services/api";
import type { AlignmentResult } from "../types";

export function AlignStep() {
  const { session, refresh } = useSessionContext();
  const navigate = useNavigate();

  const [alignment, setAlignment] = useState<AlignmentResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forkStlBlob, setForkStlBlob] = useState<Blob | null>(null);
  const [scanStlBlob, setScanStlBlob] = useState<Blob | null>(null);

  // Fetch alignment data on mount
  useEffect(() => {
    if (!session) return;

    const fetchData = async () => {
      try {
        await refresh();
        // Trigger alignment and get the result
        const resp = await api.triggerAlignment(session.session_id);
        setAlignment(resp);

        // Fetch fork and scan STL blobs in parallel
        const [forkBlob, scanBlob] = await Promise.allSettled([
          api.getForkStl(),
          api.getScanStl(session.session_id),
        ]);

        if (forkBlob.status === "fulfilled") {
          setForkStlBlob(forkBlob.value);
        }
        if (scanBlob.status === "fulfilled") {
          setScanStlBlob(scanBlob.value);
        }
      } catch {
        // If alignment already computed, just use session status
        setAlignment(null);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleApprove = useCallback(async () => {
    if (!session) return;
    try {
      await api.approveAlignment(session.session_id);
      await refresh();
      navigate("/export");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Approval failed";
      setError(msg);
    }
  }, [session, refresh, navigate]);

  const handleReject = useCallback(() => {
    navigate("/analysis");
  }, [navigate]);

  if (!session) {
    return <div style={{ padding: "24px", textAlign: "center" }}>No session available.</div>;
  }

  if (loading) {
    return (
      <div style={{ padding: "24px", textAlign: "center" }}>
        <p>Loading alignment results...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: "24px" }}>
        <div style={{ color: "red", marginBottom: "16px" }}>{error}</div>
        <button onClick={() => navigate("/analysis")} style={{ padding: "8px 16px" }}>
          Back to Analysis
        </button>
      </div>
    );
  }

  if (!alignment) {
    return (
      <div style={{ padding: "24px", textAlign: "center" }}>
        <p>No alignment data available.</p>
        <button
          onClick={() => navigate("/analysis")}
          style={{
            marginTop: "12px",
            padding: "10px 24px",
            backgroundColor: "#2563eb",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          Back to Analysis
        </button>
      </div>
    );
  }

  return (
    <div style={{ padding: "24px" }}>
      <h2>Step 4: Review Alignment</h2>

      <AlignmentPreview
        sessionId={session.session_id}
        alignment={alignment}
        forkStlBlob={forkStlBlob ?? undefined}
        scanStlBlob={scanStlBlob ?? undefined}
        onApprove={handleApprove}
        onReject={handleReject}
      />
    </div>
  );
}
