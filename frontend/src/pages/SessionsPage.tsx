import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, createScanSession, getSettings, listScanSessions } from "../api";
import { FolderPickerModal } from "../components/FolderPickerModal";
import { t } from "../i18n";
import type { ScanSession } from "../types";

function formatDate(value: string): string {
  return new Date(value).toLocaleString("ru-RU");
}

export function SessionsPage() {
  const [sessions, setSessions] = useState<ScanSession[]>([]);
  const [sourcePath, setSourcePath] = useState("");
  const [targetPath, setTargetPath] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState<"source" | "target" | null>(null);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [data, settings] = await Promise.all([listScanSessions(), getSettings()]);
      setSessions(data);
      if (!sourcePath && settings.default_source_path) setSourcePath(settings.default_source_path);
      if (!targetPath && settings.default_target_path) setTargetPath(settings.default_target_path);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось загрузить сессии");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await createScanSession({ source_path: sourcePath, target_path: targetPath });
      await loadData();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать сессию");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <section className="panel">
        <h2>{t.sessions.createTitle}</h2>
        <p className="muted">{t.sessions.quickStartHint}</p>
        <form className="form-grid" onSubmit={handleCreate}>
          <label>
            {t.sessions.sourceFolder}
            <div className="input-row">
              <input
                value={sourcePath}
                onChange={(e) => setSourcePath(e.target.value)}
                placeholder={t.sessions.sourcePlaceholder}
                required
              />
              <button type="button" onClick={() => setPickerOpen("source")}>
                {t.common.selectFolder}
              </button>
            </div>
          </label>
          <label>
            {t.sessions.targetFolder}
            <div className="input-row">
              <input
                value={targetPath}
                onChange={(e) => setTargetPath(e.target.value)}
                placeholder={t.sessions.targetPlaceholder}
                required
              />
              <button type="button" onClick={() => setPickerOpen("target")}>
                {t.common.selectFolder}
              </button>
            </div>
          </label>
          <div className="form-actions">
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? t.sessions.creating : t.sessions.createButton}
            </button>
          </div>
        </form>
      </section>

      {error ? <div className="message error">{error}</div> : null}

      <section className="panel">
        <h2>{t.sessions.title}</h2>
        {loading ? <p className="muted">{t.common.loading}</p> : null}
        {!loading && sessions.length === 0 ? <p className="muted">{t.sessions.noSessions}</p> : null}
        {!loading && sessions.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t.sessions.id}</th>
                  <th>{t.sessions.sourceFolder}</th>
                  <th>{t.sessions.targetFolder}</th>
                  <th>{t.sessions.status}</th>
                  <th>{t.sessions.created}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.id}>
                    <td>{s.id}</td>
                    <td>{s.source_path}</td>
                    <td>{s.target_path}</td>
                    <td>{s.status}</td>
                    <td>{formatDate(s.created_at)}</td>
                    <td>
                      <Link to={`/sessions/${s.id}`}>{t.sessions.openButton}</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <FolderPickerModal
        isOpen={pickerOpen === "source"}
        initialPath={sourcePath}
        onSelect={(p) => setSourcePath(p)}
        onClose={() => setPickerOpen(null)}
      />
      <FolderPickerModal
        isOpen={pickerOpen === "target"}
        initialPath={targetPath}
        onSelect={(p) => setTargetPath(p)}
        onClose={() => setPickerOpen(null)}
      />
    </div>
  );
}
