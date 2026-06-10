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
import type {
  MediaFile,
  MediaItem,
  OperationPlan,
  PlanOperation,
  ScanSession,
  TmdbMatchCandidate,
} from "../types";

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

function formatNumber(value: number | null): string {
  return value === null ? "—" : String(value);
}

export function SessionDetailPage() {
  const { sessionId } = useParams();
  const numericSessionId = Number(sessionId);

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

  const loadSessionData = useCallback(async () => {
    if (!Number.isFinite(numericSessionId)) {
      setError("Invalid session id");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [sessionData, filesData, itemsData, plansData] = await Promise.all([
        getScanSession(numericSessionId),
        listFiles(numericSessionId),
        listItems(numericSessionId),
        listPlans(numericSessionId),
      ]);
      setSession(sessionData);
      setFiles(filesData);
      setItems(itemsData);
      setPlans(plansData);
      if (selectedPlanId !== null) {
        const ops = await listPlanOperations(selectedPlanId);
        setOperations(ops);
      }
      if (selectedItemId !== null) {
        const itemCandidates = await listTmdbCandidates(selectedItemId);
        setCandidates(itemCandidates);
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load session details";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [numericSessionId, selectedItemId, selectedPlanId]);

  useEffect(() => {
    void loadSessionData();
  }, [loadSessionData]);

  async function runAction(actionName: string, action: () => Promise<unknown>, successMessage: string) {
    setActionLoading(actionName);
    setError(null);
    setInfo(null);
    try {
      await action();
      setInfo(successMessage);
      await loadSessionData();
    } catch (err) {
      const rawMessage = err instanceof ApiError ? err.message : `Failed to run ${actionName}`;
      setError(formatTmdbError(rawMessage));
    } finally {
      setActionLoading(null);
    }
  }

  async function handleShowCandidates(itemId: number) {
    setSelectedItemId(itemId);
    setError(null);
    try {
      const itemCandidates = await listTmdbCandidates(itemId);
      setCandidates(itemCandidates);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load TMDB candidates";
      setError(message);
      setCandidates([]);
    }
  }

  async function handleShowOperations(planId: number) {
    setSelectedPlanId(planId);
    setError(null);
    try {
      const ops = await listPlanOperations(planId);
      setOperations(ops);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load plan operations";
      setError(message);
      setOperations([]);
    }
  }

  if (!Number.isFinite(numericSessionId)) {
    return <div className="message error">Invalid session id.</div>;
  }

  return (
    <div>
      <p>
        <Link to="/">← Back to sessions</Link>
      </p>

      {error ? <div className="message error">{error}</div> : null}
      {info ? <div className="message info">{info}</div> : null}

      <section className="panel">
        <h2>Session #{numericSessionId}</h2>
        {loading && !session ? <p className="muted">Loading session...</p> : null}
        {session ? (
          <>
            <div className="summary-grid">
              <div className="summary-item">
                <strong>Source path</strong>
                <span>{session.source_path}</span>
              </div>
              <div className="summary-item">
                <strong>Target path</strong>
                <span>{session.target_path}</span>
              </div>
              <div className="summary-item">
                <strong>Status</strong>
                <span>{session.status}</span>
              </div>
              <div className="summary-item">
                <strong>Updated</strong>
                <span>{formatDate(session.updated_at)}</span>
              </div>
            </div>
            {session.error_message ? (
              <p className="message error" style={{ marginTop: "1rem" }}>
                {session.error_message}
              </p>
            ) : null}
            <div className="form-actions" style={{ marginTop: "1rem" }}>
              <button
                type="button"
                disabled={actionLoading !== null}
                onClick={() =>
                  void runAction("discover", () => discoverSession(numericSessionId), "Discovery completed.")
                }
              >
                {actionLoading === "discover" ? "Discovering..." : "Discover"}
              </button>
              <button
                type="button"
                disabled={actionLoading !== null}
                onClick={() =>
                  void runAction("parse", () => parseSession(numericSessionId), "Parsing completed.")
                }
              >
                {actionLoading === "parse" ? "Parsing..." : "Parse"}
              </button>
              <button
                type="button"
                disabled={actionLoading !== null}
                onClick={() =>
                  void runAction(
                    "match-tmdb",
                    () => matchTmdbSession(numericSessionId),
                    "TMDB matching completed.",
                  )
                }
              >
                {actionLoading === "match-tmdb" ? "Matching..." : "Match TMDB"}
              </button>
              <button
                type="button"
                disabled={actionLoading !== null}
                onClick={() =>
                  void runAction("create-plan", () => createPlan(numericSessionId), "Dry-run plan created.")
                }
              >
                {actionLoading === "create-plan" ? "Planning..." : "Create Plan"}
              </button>
            </div>
          </>
        ) : null}
      </section>

      <section className="panel">
        <h3>Files</h3>
        {loading ? <p className="muted">Loading files...</p> : null}
        {!loading && files.length === 0 ? <p className="muted">No files discovered yet.</p> : null}
        {files.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Kind</th>
                  <th>File name</th>
                  <th>Extension</th>
                  <th>Size</th>
                  <th>Media item</th>
                  <th>Scan error</th>
                </tr>
              </thead>
              <tbody>
                {files.map((file) => (
                  <tr key={file.id}>
                    <td>{file.id}</td>
                    <td>{file.kind}</td>
                    <td>{file.file_name}</td>
                    <td>{file.extension}</td>
                    <td>{formatNumber(file.size_bytes)}</td>
                    <td>{formatNumber(file.media_item_id)}</td>
                    <td>{file.scan_error ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <h3>Items</h3>
        {loading ? <p className="muted">Loading items...</p> : null}
        {!loading && items.length === 0 ? <p className="muted">No parsed items yet.</p> : null}
        {items.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Parsed title</th>
                  <th>Year</th>
                  <th>Season</th>
                  <th>Episode</th>
                  <th>TMDB ID</th>
                  <th>Matched title</th>
                  <th>Matched year</th>
                  <th>Confidence</th>
                  <th>Needs review</th>
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
                    <td>{formatNumber(item.year)}</td>
                    <td>{formatNumber(item.season_number)}</td>
                    <td>{formatNumber(item.episode_number)}</td>
                    <td>{formatNumber(item.tmdb_id)}</td>
                    <td>{item.matched_title ?? "—"}</td>
                    <td>{formatNumber(item.matched_year)}</td>
                    <td>{formatNumber(item.match_confidence)}</td>
                    <td>{item.needs_review ? "yes" : "no"}</td>
                    <td>
                      <button type="button" onClick={() => void handleShowCandidates(item.id)}>
                        Show TMDB candidates
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
            <h4>TMDB candidates for item #{selectedItemId}</h4>
            {candidates.length === 0 ? <p className="muted">No candidates loaded.</p> : null}
            {candidates.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>TMDB ID</th>
                      <th>Title</th>
                      <th>Year</th>
                      <th>Score</th>
                      <th>Selected</th>
                    </tr>
                  </thead>
                  <tbody>
                    {candidates.map((candidate) => (
                      <tr key={candidate.id}>
                        <td>{candidate.id}</td>
                        <td>{candidate.tmdb_id}</td>
                        <td>{candidate.title}</td>
                        <td>{formatNumber(candidate.year)}</td>
                        <td>{candidate.score}</td>
                        <td>{candidate.is_selected ? "yes" : "no"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="panel">
        <h3>Plans</h3>
        {loading ? <p className="muted">Loading plans...</p> : null}
        {!loading && plans.length === 0 ? <p className="muted">No dry-run plans yet.</p> : null}
        {plans.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Updated</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {plans.map((plan) => (
                  <tr key={plan.id}>
                    <td>{plan.id}</td>
                    <td>{plan.status}</td>
                    <td>{formatDate(plan.created_at)}</td>
                    <td>{formatDate(plan.updated_at)}</td>
                    <td>
                      <button type="button" onClick={() => void handleShowOperations(plan.id)}>
                        Show operations
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <h3>Operations</h3>
        {selectedPlanId === null ? (
          <p className="muted">Select a plan to view its operations.</p>
        ) : null}
        {selectedPlanId !== null && operations.length === 0 ? (
          <p className="muted">No operations loaded for plan #{selectedPlanId}.</p>
        ) : null}
        {operations.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Source path</th>
                  <th>Target path</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {operations.map((operation) => (
                  <tr key={operation.id}>
                    <td>{operation.id}</td>
                    <td>{operation.operation_type}</td>
                    <td>{operation.status}</td>
                    <td>{operation.source_path ?? "—"}</td>
                    <td>{operation.target_path ?? "—"}</td>
                    <td>{operation.error_message ?? "—"}</td>
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
