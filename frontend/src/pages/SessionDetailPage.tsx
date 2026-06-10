import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  createPlan,
  discoverSession,
  formatTmdbError,
  getScanSession,
  listFiles,
  listItems,
  listPlanOperations,
  listPlans,
  listTmdbCandidates,
  matchTmdbSession,
  parseSession,
} from "../api";
import { t } from "../i18n";
import type {
  MediaFile,
  MediaItem,
  OperationPlan,
  PlanOperation,
  ScanSession,
  TmdbMatchCandidate,
} from "../types";

function formatDate(value: string): string {
  return new Date(value).toLocaleString("ru-RU");
}

function fmt(value: string | number | null | undefined): string {
  return value === null || value === undefined ? "—" : String(value);
}

export function SessionDetailPage() {
  const { sessionId } = useParams();
  const numId = Number(sessionId);

  const [session, setSession] = useState<ScanSession | null>(null);
  const [files, setFiles] = useState<MediaFile[]>([]);
  const [items, setItems] = useState<MediaItem[]>([]);
  const [plans, setPlans] = useState<OperationPlan[]>([]);
  const [operations, setOperations] = useState<PlanOperation[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [candidates, setCandidates] = useState<TmdbMatchCandidate[]>([]);

  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    if (!Number.isFinite(numId)) return;
    setLoading(true);
    setError(null);
    try {
      const [s, f, i, p] = await Promise.all([
        getScanSession(numId),
        listFiles(numId),
        listItems(numId),
        listPlans(numId),
      ]);
      setSession(s);
      setFiles(f);
      setItems(i);
      setPlans(p);
      if (selectedPlanId !== null) {
        setOperations(await listPlanOperations(selectedPlanId));
      }
      if (selectedItemId !== null) {
        setCandidates(await listTmdbCandidates(selectedItemId));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ошибка загрузки сессии");
    } finally {
      setLoading(false);
    }
  }, [numId, selectedPlanId, selectedItemId]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  async function runAction(key: string, action: () => Promise<unknown>, msg: string) {
    setActionLoading(key);
    setError(null);
    setInfo(null);
    try {
      await action();
      setInfo(msg);
      await loadAll();
    } catch (err) {
      const raw = err instanceof ApiError ? err.message : `Ошибка: ${key}`;
      setError(formatTmdbError(raw));
    } finally {
      setActionLoading(null);
    }
  }

  async function showCandidates(itemId: number) {
    setSelectedItemId(itemId);
    try {
      setCandidates(await listTmdbCandidates(itemId));
    } catch {
      setCandidates([]);
    }
  }

  async function showOperations(planId: number) {
    setSelectedPlanId(planId);
    try {
      setOperations(await listPlanOperations(planId));
    } catch {
      setOperations([]);
    }
  }

  if (!Number.isFinite(numId)) {
    return <div className="message error">Неверный ID сессии.</div>;
  }

  const busy = actionLoading !== null;

  return (
    <div>
      <p>
        <Link to="/">{t.detail.backToSessions}</Link>
      </p>

      {error ? <div className="message error">{error}</div> : null}
      {info ? <div className="message info">{info}</div> : null}

      <div className="safety-notice">🛡 {t.detail.safetyNotice}</div>

      <section className="panel">
        <h2>
          {t.detail.sessionTitle}
          {numId}
        </h2>
        {loading && !session ? <p className="muted">{t.common.loading}</p> : null}
        {session ? (
          <>
            <div className="summary-grid">
              <div className="summary-item">
                <strong>{t.detail.sourceFolder}</strong>
                <span>{session.source_path}</span>
              </div>
              <div className="summary-item">
                <strong>{t.detail.targetFolder}</strong>
                <span>{session.target_path}</span>
              </div>
              <div className="summary-item">
                <strong>{t.detail.status}</strong>
                <span>{session.status}</span>
              </div>
              <div className="summary-item">
                <strong>{t.detail.updated}</strong>
                <span>{formatDate(session.updated_at)}</span>
              </div>
            </div>
            {session.error_message ? (
              <div className="message error" style={{ marginTop: "1rem" }}>
                {session.error_message}
              </div>
            ) : null}

            {/* Pipeline action buttons */}
            <div style={{ marginTop: "1.25rem" }}>
              <div className="pipeline-actions">
                <span className="step-label">1.</span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void runAction("discover", () => discoverSession(numId), "Сканирование завершено.")
                  }
                >
                  {actionLoading === "discover" ? t.detail.discovering : t.detail.discover}
                </button>
                <span className="step-label">2.</span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void runAction("parse", () => parseSession(numId), "Распознавание завершено.")
                  }
                >
                  {actionLoading === "parse" ? t.detail.parsing : t.detail.parse}
                </button>
                <span className="step-label">3.</span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void runAction("match-tmdb", () => matchTmdbSession(numId), "Поиск TMDB завершён.")
                  }
                >
                  {actionLoading === "match-tmdb" ? t.detail.matchingTmdb : t.detail.matchTmdb}
                </button>
                <span className="step-label">4.</span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void runAction("create-plan", () => createPlan(numId), "План построен.")
                  }
                >
                  {actionLoading === "create-plan" ? t.detail.planning : t.detail.createPlan}
                </button>
              </div>
            </div>
          </>
        ) : null}
      </section>

      {/* Files */}
      <section className="panel">
        <h3>{t.detail.filesSection}</h3>
        {loading ? <p className="muted">{t.common.loading}</p> : null}
        {!loading && files.length === 0 ? <p className="muted">{t.detail.noFiles}</p> : null}
        {files.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>{t.detail.kind}</th>
                  <th>{t.detail.fileName}</th>
                  <th>{t.detail.extension}</th>
                  <th>{t.detail.size}</th>
                  <th>{t.detail.mediaItem}</th>
                  <th>{t.detail.scanError}</th>
                </tr>
              </thead>
              <tbody>
                {files.map((f) => (
                  <tr key={f.id}>
                    <td>{f.id}</td>
                    <td>{f.kind}</td>
                    <td>{f.file_name}</td>
                    <td>{f.extension}</td>
                    <td>{fmt(f.size_bytes)}</td>
                    <td>{fmt(f.media_item_id)}</td>
                    <td>{f.scan_error ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      {/* Items */}
      <section className="panel">
        <h3>{t.detail.itemsSection}</h3>
        {loading ? <p className="muted">{t.common.loading}</p> : null}
        {!loading && items.length === 0 ? <p className="muted">{t.detail.noItems}</p> : null}
        {items.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>{t.detail.mediaType}</th>
                  <th>{t.detail.status}</th>
                  <th>{t.detail.parsedTitle}</th>
                  <th>{t.detail.year}</th>
                  <th>{t.detail.season}</th>
                  <th>{t.detail.episode}</th>
                  <th>{t.detail.tmdbId}</th>
                  <th>{t.detail.matchedTitle}</th>
                  <th>{t.detail.confidence}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.id}</td>
                    <td>{item.media_type}</td>
                    <td>{item.status}</td>
                    <td>{item.parsed_title ?? "—"}</td>
                    <td>{fmt(item.year)}</td>
                    <td>{fmt(item.season_number)}</td>
                    <td>{fmt(item.episode_number)}</td>
                    <td>{fmt(item.tmdb_id)}</td>
                    <td>{item.matched_title ?? "—"}</td>
                    <td>{fmt(item.match_confidence)}</td>
                    <td>
                      <button type="button" onClick={() => void showCandidates(item.id)}>
                        {t.detail.showCandidates}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {selectedItemId !== null ? (
          <div className="candidates-block">
            <h4>
              {t.detail.tmdbCandidatesFor}
              {selectedItemId}
            </h4>
            {candidates.length === 0 ? <p className="muted">{t.detail.noCandidates}</p> : null}
            {candidates.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>TMDB ID</th>
                      <th>{t.detail.matchedTitle}</th>
                      <th>{t.detail.year}</th>
                      <th>{t.detail.score}</th>
                      <th>{t.detail.selected}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {candidates.map((c) => (
                      <tr key={c.id}>
                        <td>{c.tmdb_id}</td>
                        <td>{c.title}</td>
                        <td>{fmt(c.year)}</td>
                        <td>{c.score.toFixed(2)}</td>
                        <td>{c.is_selected ? "✓" : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      {/* Plans */}
      <section className="panel">
        <h3>{t.detail.plansSection}</h3>
        {loading ? <p className="muted">{t.common.loading}</p> : null}
        {!loading && plans.length === 0 ? <p className="muted">{t.detail.noPlans}</p> : null}
        {plans.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>{t.detail.planStatus}</th>
                  <th>{t.sessions.created}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {plans.map((plan) => (
                  <tr key={plan.id}>
                    <td>{plan.id}</td>
                    <td>{plan.status}</td>
                    <td>{formatDate(plan.created_at)}</td>
                    <td>
                      <button type="button" onClick={() => void showOperations(plan.id)}>
                        {t.detail.showOperations}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      {/* Operations */}
      <section className="panel">
        <h3>{t.detail.operationsSection}</h3>
        {selectedPlanId === null ? (
          <p className="muted">{t.detail.noOperations}</p>
        ) : operations.length === 0 ? (
          <p className="muted">
            {t.detail.operationsForPlan}
            {selectedPlanId} — нет операций.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>{t.detail.operationType}</th>
                  <th>{t.detail.status}</th>
                  <th>{t.detail.sourcePath}</th>
                  <th>{t.detail.targetPath}</th>
                  <th>{t.detail.scanError}</th>
                </tr>
              </thead>
              <tbody>
                {operations.map((op) => (
                  <tr key={op.id}>
                    <td>{op.id}</td>
                    <td>{op.operation_type}</td>
                    <td>{op.status}</td>
                    <td className="path-text">{op.source_path ?? "—"}</td>
                    <td className="path-text">{op.target_path ?? "—"}</td>
                    <td>{op.error_message ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
