/** App shell with routing and session context (T016). */

import { createContext, useContext, useState } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { useSession } from "./hooks/useSession";
import { AlignStep } from "./pages/AlignStep";
import { AnalysisStep } from "./pages/AnalysisStep";
import { CaptureStep } from "./pages/CaptureStep";
import { ForkCalibrationStep } from "./pages/ForkCalibrationStep";
import { ScanStep } from "./pages/ScanStep";
import type { Session } from "./types";

// Session context
interface SessionContextValue {
  session: Session | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  initSession: () => Promise<void>;
  consent: boolean;
  setConsent: (v: boolean) => void;
}

export const SessionContext = createContext<SessionContextValue>({
  session: null,
  loading: true,
  error: null,
  refresh: async () => {},
  initSession: async () => {},
  consent: false,
  setConsent: () => {},
});

export function useSessionContext() {
  return useContext(SessionContext);
}

// Step progress indicator
const STEPS = [
  { path: "/", label: "Capture" },
  { path: "/analysis", label: "Analysis" },
  { path: "/scan", label: "Scan" },
  { path: "/align", label: "Align" },
  { path: "/export", label: "Export" },
];

function StepIndicator() {
  const { pathname } = useLocation();
  const currentIndex = STEPS.findIndex((s) => s.path === pathname);

  return (
    <nav style={{ display: "flex", gap: "8px", padding: "16px", justifyContent: "center" }}>
      {STEPS.map((step, i) => (
        <span
          key={step.path}
          style={{
            padding: "8px 16px",
            borderRadius: "4px",
            backgroundColor: i === currentIndex ? "#2563eb" : i < currentIndex ? "#93c5fd" : "#e5e7eb",
            color: i <= currentIndex ? "white" : "#6b7280",
            fontWeight: i === currentIndex ? "bold" : "normal",
          }}
        >
          {step.label}
        </span>
      ))}
    </nav>
  );
}

// Placeholder pages for later phases
function Placeholder({ name }: { name: string }) {
  return <div style={{ padding: "24px", textAlign: "center" }}>{name} — coming soon</div>;
}

export function App() {
  const { session, loading, error, refresh, initSession } = useSession();
  const [consent, setConsent] = useState(false);

  if (loading) {
    return <div style={{ padding: "24px", textAlign: "center" }}>Loading...</div>;
  }

  if (error) {
    return <div style={{ padding: "24px", textAlign: "center", color: "red" }}>Error: {error}</div>;
  }

  return (
    <SessionContext.Provider value={{ session, loading, error, refresh, initSession, consent, setConsent }}>
      <div style={{ maxWidth: "960px", margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "center", alignItems: "baseline", padding: "16px", gap: "16px" }}>
          <h1 style={{ margin: 0 }}>FaceAnalyzer</h1>
          <Link to="/fork-calibration" style={{ fontSize: "13px", color: "#6b7280", textDecoration: "none" }}>
            Fork Calibration
          </Link>
        </div>
        <StepIndicator />
        <Routes>
          <Route path="/" element={<CaptureStep />} />
          <Route path="/analysis" element={<AnalysisStep />} />
          <Route path="/scan" element={<ScanStep />} />
          <Route path="/align" element={<AlignStep />} />
          <Route path="/export" element={<Placeholder name="Export" />} />
          <Route path="/fork-calibration" element={<ForkCalibrationStep />} />
        </Routes>
      </div>
    </SessionContext.Provider>
  );
}
