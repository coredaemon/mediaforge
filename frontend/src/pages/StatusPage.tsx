import { useEffect, useState } from "react";
import { ApiError, getApiBaseUrl, getHealth } from "../api";
import type { HealthResponse } from "../types";

export function StatusPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await getHealth();
        setHealth(response);
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Failed to reach backend";
        setError(message);
        setHealth(null);
      } finally {
        setLoading(false);
      }
    }

    void load();
  }, []);

  return (
    <section className="panel">
      <h2>About / Status</h2>
      <p>
        MediaForge is a local-first media library organizer. This minimal web UI lets you run the
        discovery, parsing, TMDB matching, and dry-run planning pipeline without changing files on
        disk.
      </p>
      <div className="summary-grid">
        <div className="summary-item">
          <strong>Backend URL</strong>
          <span>{getApiBaseUrl()}</span>
        </div>
        <div className="summary-item">
          <strong>Frontend URL</strong>
          <span>{window.location.origin}</span>
        </div>
        <div className="summary-item">
          <strong>Health</strong>
          <span>
            {loading ? "Checking..." : error ? error : `${health?.app} ${health?.status}`}
          </span>
        </div>
      </div>
      <p className="muted">
        Apply, rollback, poster download, and NFO writing are not implemented yet. Planning is
        dry-run only.
      </p>
    </section>
  );
}
