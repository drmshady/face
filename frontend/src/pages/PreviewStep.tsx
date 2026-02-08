/** Preview page — 3D preview with fork + reference lines + export (simplified from AlignStep). */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSessionContext } from "../App";
import { AlignmentPreview } from "../components/AlignmentPreview";
import * as api from "../services/api";
import type { AlignmentResult } from "../types";

export function PreviewStep() {
  const { session, refresh } = useSessionContext();
  const navigate = useNavigate();

  const [alignment, setAlignment] = useState<AlignmentResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forkStlBlob, setForkStlBlob] = useState<Blob | null>(null);

  // Fetch alignment data on mount
  useEffect(() => {
    if (!session) return;

    const fetchData = async () => {
      try {
        await refresh();
        // Trigger alignment and get the result
        const resp = await api.triggerAlignment(session.session_id);
        setAlignment(resp);

        // Fetch fork STL
        try {
          const forkBlob = await api.getForkStl();
          setForkStlBlob(forkBlob);
        } catch {
          // Fork STL may not be available
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load alignment");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
        <button onClick={() => navigate("/")} style={{ padding: "8px 16px" }}>
          Start Over
        </button>
      </div>
    );
  }

  if (!alignment) {
    return (
      <div style={{ padding: "24px", textAlign: "center" }}>
        <p>No alignment data available.</p>
        <button
          onClick={() => navigate("/")}
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
          Start Over
        </button>
      </div>
    );
  }

  return (
    <div style={{ padding: "24px" }}>
      <h2>Step 3: Preview</h2>

      <AlignmentPreview
        sessionId={session.session_id}
        alignment={alignment}
        forkStlBlob={forkStlBlob ?? undefined}
      />

      <div style={{ marginTop: "24px" }}>
        <button
          onClick={() => navigate("/")}
          style={{
            padding: "10px 24px",
            backgroundColor: "#6b7280",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          Start Over
        </button>
      </div>
    </div>
  );
}
