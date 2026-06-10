import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, createScanSession, listScanSessions } from "../api";
import type { ScanSession } from "../types";

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

export function SessionsPage() {
  const [sessions, setSessions] = useState<ScanSession[]>([]);
  const [sourcePath, setSourcePath] = useState("");
  const [targetPath, setTargetPath] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadSessions() {
    setLoading(true);
    setError(null);
    try {
      const data = await listScanSessions();
      setSessions(data);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load scan sessions";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSessions();
  }, []);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await createScanSession({ source_path: sourcePath, target_path: targetPath });
      setSourcePath("");
      setTargetPath("");
      await loadSessions();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to create scan session";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <section className="panel">
        <h2>Create Scan Session</h2>
        <form className="form-grid" onSubmit={handleCreate}>
          <label>
            Source path
            <input
              value={sourcePath}
              onChange={(event) => setSourcePath(event.target.value)}
              placeholder="D:/Media/Inbox"
              required
            />
          </label>
          <label>
            Target path
            <input
              value={targetPath}
              onChange={(event) => setTargetPath(event.target.value)}
              placeholder="D:/Media/Library"
              required
            />
          </label>
          <div className="form-actions">
            <button type="submit" disabled={submitting}>
              {submitting ? "Creating..." : "Create"}
            </button>
          </div>
        </form>
      </section>

      {error ? <div className="message error">{error}</div> : null}

      <section className="panel">
        <h2>Scan Sessions</h2>
        {loading ? <p className="muted">Loading sessions...</p> : null}
        {!loading && sessions.length === 0 ? <p className="muted">No scan sessions yet.</p> : null}
        {!loading && sessions.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Source path</th>
                  <th>Target path</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {sessions.map((session) => (
                  <tr key={session.id}>
                    <td>{session.id}</td>
                    <td>{session.source_path}</td>
                    <td>{session.target_path}</td>
                    <td>{session.status}</td>
                    <td>{formatDate(session.created_at)}</td>
                    <td>
                      <Link to={`/sessions/${session.id}`}>Open</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
