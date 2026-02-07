/** useSession hook — manages session lifecycle (T017). */

import { useCallback, useEffect, useRef, useState } from "react";
import { createSession, getSession } from "../services/api";
import type { Session } from "../types";

const POLL_INTERVAL_MS = 3000;
const SESSION_ID_KEY = "face_session_id";

export function useSession() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const initSession = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // Check if we already have a session id stored
      const existingId = sessionStorage.getItem(SESSION_ID_KEY);
      if (existingId) {
        try {
          const existing = await getSession(existingId);
          setSession(existing);
          return;
        } catch {
          // Session expired or invalid, create new one
          sessionStorage.removeItem(SESSION_ID_KEY);
        }
      }

      // Create new session
      const newSession = await createSession();
      sessionStorage.setItem(SESSION_ID_KEY, newSession.session_id);
      setSession(newSession);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
    } finally {
      setLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    if (!session) return;
    try {
      const updated = await getSession(session.session_id);
      setSession(updated);
    } catch (err) {
      // If session is gone (server restarted), auto-recover with a new session
      if (err && typeof err === "object" && "response" in err) {
        const axiosErr = err as { response?: { status?: number } };
        if (axiosErr.response?.status === 404 || axiosErr.response?.status === 401) {
          sessionStorage.removeItem(SESSION_ID_KEY);
          try {
            const newSession = await createSession();
            sessionStorage.setItem(SESSION_ID_KEY, newSession.session_id);
            setSession(newSession);
            setError(null);
            return;
          } catch {
            // Fall through to generic error
          }
        }
      }
      setError(err instanceof Error ? err.message : "Failed to refresh session");
    }
  }, [session]);

  // Start polling when session is in a processing state
  useEffect(() => {
    if (!session) return;

    const isProcessing =
      session.status === "analyzing" || session.status === "aligning";

    if (isProcessing && !pollRef.current) {
      pollRef.current = setInterval(refresh, POLL_INTERVAL_MS);
    } else if (!isProcessing && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [session, refresh]);

  // Initialize on mount
  useEffect(() => {
    void initSession();
  }, [initSession]);

  return { session, loading, error, refresh, initSession };
}
