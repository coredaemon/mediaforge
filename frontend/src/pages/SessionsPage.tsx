import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createScanSession, deleteScanSession, getSettings, listScanSessions } from "../api";
import { FolderPickerModal } from "../components/FolderPickerModal";
import { t } from "../i18n";
import { labelScanSessionStatus } from "../labels";
import type { ScanSession } from "../types";
import { formatPath } from "../utils/formatPath";

function formatDate(value: string): string {
  return new Date(value).toLocaleString("ru-RU");
}

/** Normalise slashes so D:\Foo and D:/Foo are treated as the same path. */
function normalisePath(p: string): string {
  return p.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
}

/** Returns a validation error message if paths conflict, otherwise null. */
function detectPathConflict(source: string, target: string): string | null {
  if (!source.trim() || !target.trim()) return null;
  const s = normalisePath(source);
  const tgt = normalisePath(target);
  if (s === tgt) {
    return "Папка с файлами и папка медиатеки не должны совпадать. Выберите отдельную папку для результата.";
  }
  if (tgt.startsWith(s + "/")) {
    return (
      "Папка медиатеки находится внутри папки с файлами. " +
      "Выберите отдельную папку, иначе MediaForge может повторно сканировать уже обработанные файлы."
    );
  }
  if (s.startsWith(tgt + "/")) {
    return "Папка с файлами находится внутри папки медиатеки. Выберите отдельную папку с исходниками.";
  }
  return null;
}

export function SessionsPage() {
  const [sessions, setSessions] = useState<ScanSession[]>([]);
  const [sourcePath, setSourcePath] = useState("");
  const [targetPath, setTargetPath] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState<"source" | "target" | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [data, settings] = await Promise.all([listScanSessions(), getSettings()]);
      setSessions(data);
      if (!sourcePath && settings.default_source_path) setSourcePath(settings.default_source_path);
      if (!targetPath && settings.default_target_path) setTargetPath(settings.default_target_path);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось загрузить сессии";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleDelete(session: ScanSession) {
    const confirmed = window.confirm(t.sessions.deleteConfirm.replace("#{id}", String(session.id)));
    if (!confirmed) return;

    setDeletingId(session.id);
    setError(null);
    setSuccessMsg(null);
    try {
      await deleteScanSession(session.id);
      setSuccessMsg(t.sessions.deleteSuccess.replace("#{id}", String(session.id)));
      await loadData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : t.sessions.deleteError;
      setError(msg);
    } finally {
      setDeletingId(null);
    }
  }

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setSuccessMsg(null);
    setError(null);

    // Client-side validation before sending to backend.
    if (!sourcePath.trim()) {
      setFormError("Укажите папку с исходными файлами.");
      return;
    }
    if (!targetPath.trim()) {
      setFormError("Укажите целевую папку медиатеки.");
      return;
    }
    const conflictMsg = detectPathConflict(sourcePath, targetPath);
    if (conflictMsg) {
      setFormError(conflictMsg);
      return;
    }

    setSubmitting(true);
    try {
      await createScanSession({ source_path: sourcePath, target_path: targetPath });
      setSuccessMsg("Сессия создана");
      await loadData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось создать сессию";
      setFormError(msg);
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
          {/* Real-time warning for path conflicts */}
          {sourcePath && targetPath && !formError && detectPathConflict(sourcePath, targetPath) ? (
            <div className="message warning">{detectPathConflict(sourcePath, targetPath)}</div>
          ) : null}
          {formError ? <div className="message error">{formError}</div> : null}
          {successMsg ? <div className="message success">{successMsg}</div> : null}
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
        {!loading && sessions.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">＋</div>
            <strong>{t.sessions.noSessions}</strong>
            <span>{t.sessions.quickStartHint}</span>
          </div>
        ) : null}
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
                    <td className="path-short" title={s.source_path}>{formatPath(s.source_path)}</td>
                    <td className="path-short" title={s.target_path}>{formatPath(s.target_path)}</td>
                    <td>{labelScanSessionStatus(s.status)}</td>
                    <td>{formatDate(s.created_at)}</td>
                    <td className="table-actions">
                      <Link to={`/sessions/${s.id}`}>{t.sessions.openButton}</Link>
                      <button
                        type="button"
                        className="btn-danger"
                        disabled={deletingId === s.id}
                        onClick={() => void handleDelete(s)}
                      >
                        {deletingId === s.id ? t.common.loading : t.sessions.deleteButton}
                      </button>
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
