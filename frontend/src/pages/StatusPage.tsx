import { useEffect, useState } from "react";
import { ApiError, getApiBaseUrl, getHealth } from "../api";
import { t } from "../i18n";
import type { HealthResponse } from "../types";

export function StatusPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        setHealth(await getHealth());
      } catch (err) {
        setError(err instanceof ApiError ? err.message : t.health.offline);
        setHealth(null);
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  return (
    <section className="panel">
      <h2>{t.statusPage.title}</h2>
      <p>{t.statusPage.description}</p>
      <div className="summary-grid">
        <div className="summary-item">
          <strong>{t.statusPage.backendUrl}</strong>
          <span>{getApiBaseUrl()}</span>
        </div>
        <div className="summary-item">
          <strong>{t.statusPage.frontendUrl}</strong>
          <span>{window.location.origin}</span>
        </div>
        <div className="summary-item">
          <strong>{t.statusPage.healthLabel}</strong>
          <span>
            {loading
              ? t.common.loading
              : error
                ? error
                : `${health?.app ?? ""} — ${health?.status ?? ""}`}
          </span>
        </div>
      </div>
      <p className="muted" style={{ marginTop: "1rem" }}>
        {t.statusPage.disclaimer}
      </p>
    </section>
  );
}
