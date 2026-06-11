import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  createPlan,
  createRecognitionCorrection,
  deleteScanSession,
  discoverSession,
  formatTmdbError,
  getScanSession,
  listFiles,
  listItems,
  listPlanOperations,
  listPlans,
  listTmdbCandidates,
  matchTmdbSession,
  normalizeLocalAi,
  parseSession,
  recognitionPreflight,
  resolveWithGemini,
  selectTmdbCandidate,
} from "../api";
import { t } from "../i18n";
import {
  labelMediaItemStatus,
  labelMediaType,
  labelOperationPreview,
  labelOperationStatus,
  labelOperationType,
  labelPlanStatus,
  labelScanSessionStatus,
  statusTone,
  type BadgeTone,
} from "../labels";
import type {
  MediaFile,
  MediaItem,
  OperationPlan,
  PlanOperation,
  RecognitionPreflightResult,
  ScanSession,
  TmdbMatchCandidate,
} from "../types";

type StepStatus = "pending" | "running" | "done" | "error";

const analysisSteps: { key: string; label: string }[] = [
  { key: "preflight", label: "AI preflight" },
  { key: "discover", label: "Сканирование файлов" },
  { key: "parse", label: "Распознавание названий" },
  { key: "local-ai", label: "Local AI cleanup" },
  { key: "match", label: "Поиск в TMDB" },
  { key: "gemini", label: "Gemini fallback" },
  { key: "plan", label: "Построение безопасного плана" },
];

function formatDate(value: string): string {
  return new Date(value).toLocaleString("ru-RU");
}

function fmt(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
}

function normalisePath(p: string): string {
  return p.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
}

function detectPathNestingWarning(source: string, target: string): string | null {
  const s = normalisePath(source);
  const t = normalisePath(target);
  if (s === t) return null;
  if (t.startsWith(s + "/")) {
    return "Папка медиатеки находится внутри папки с файлами. Для новых сессий такой вариант будет запрещён.";
  }
  if (s.startsWith(t + "/")) {
    return "Папка с файлами находится внутри папки медиатеки. Для новых сессий такой вариант будет запрещён.";
  }
  return null;
}

function Badge({ value, label }: { value: string | null | undefined; label: string }) {
  return <span className={`status-badge ${statusTone(value)}`}>{label}</span>;
}

function StepBadge({ status }: { status: StepStatus }) {
  const labels: Record<StepStatus, string> = {
    pending: "Ожидает",
    running: "Выполняется",
    done: "Готово",
    error: "Ошибка",
  };
  const tones: Record<StepStatus, BadgeTone> = {
    pending: "neutral",
    running: "info",
    done: "success",
    error: "danger",
  };
  return <span className={`status-badge ${tones[status]}`}>{labels[status]}</span>;
}

function SummaryCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="summary-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function OperationPreview({ operation }: { operation: PlanOperation }) {
  return (
    <div className="operation-preview">
      <div>
        <strong>{labelOperationPreview(operation.operation_type)}</strong>
        <Badge value={operation.status} label={labelOperationStatus(operation.status)} />
      </div>
      <div className="operation-paths">
        {operation.source_path ? (
          <div>
            <span>Откуда</span>
            <code>{operation.source_path}</code>
          </div>
        ) : null}
        {operation.target_path ? (
          <div>
            <span>Куда</span>
            <code>{operation.target_path}</code>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function formatPreflightError(result: RecognitionPreflightResult): string {
  if (!result.local.ok) {
    return result.local.error ?? "Local LLM did not respond. Check that Ollama is running, the model is selected, and the endpoint is reachable.";
  }
  if (!result.cloud.ok) {
    return result.cloud.error ?? "Gemini did not respond. Check the API key and cloud AI settings.";
  }
  return "AI preflight failed.";
}

function formatCheckStatus(check: RecognitionPreflightResult["local"] | null | undefined): string {
  if (!check) return "not run";
  if (check.ok) return `works, ${check.duration_ms} ms`;
  if (check.error_type === "invalid_json") return "response received, JSON invalid";
  return check.error_type ? `error: ${check.error_type}` : "error";
}

function PreflightPanel({ result, status }: { result: RecognitionPreflightResult | null; status: StepStatus }) {
  return (
    <div className="preflight-panel">
      <div className="section-heading">
        <strong>AI preflight</strong>
        <StepBadge status={status} />
      </div>
      <div className="preflight-grid">
        <div>
          <span>Local LLM</span>
          <strong>{formatCheckStatus(result?.local)}</strong>
          {result?.local.model ? <small>{result.local.model}</small> : null}
          {result?.local.endpoint ? <small>{result.local.endpoint}</small> : null}
          {result?.local.error ? <small className="error-text">{result.local.error}</small> : null}
        </div>
        <div>
          <span>Cloud LLM</span>
          <strong>{formatCheckStatus(result?.cloud)}</strong>
          {result?.cloud.model ? <small>{result.cloud.model}</small> : null}
          {result?.cloud.provider ? <small>{result.cloud.provider}</small> : null}
          {result?.cloud.error ? <small className="error-text">{result.cloud.error}</small> : null}
        </div>
      </div>
    </div>
  );
}

export function SessionDetailPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const numId = Number(sessionId);

  const [session, setSession] = useState<ScanSession | null>(null);
  const [files, setFiles] = useState<MediaFile[]>([]);
  const [items, setItems] = useState<MediaItem[]>([]);
  const [plans, setPlans] = useState<OperationPlan[]>([]);
  const [operations, setOperations] = useState<PlanOperation[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [candidates, setCandidates] = useState<TmdbMatchCandidate[]>([]);
  const [stepStatus, setStepStatus] = useState<Record<string, StepStatus>>({
    preflight: "pending",
    discover: "pending",
    parse: "pending",
    "local-ai": "pending",
    match: "pending",
    gemini: "pending",
    plan: "pending",
  });

  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [preflightResult, setPreflightResult] = useState<RecognitionPreflightResult | null>(null);

  const latestPlanId = plans[0]?.id ?? null;

  const loadAll = useCallback(async () => {
    if (!Number.isFinite(numId)) return;
    setLoading(true);
    setError(null);

    try {
      const loadedSession = await getScanSession(numId);
      setSession(loadedSession);

      const [loadedFiles, loadedItems, loadedPlans] = await Promise.all([
        listFiles(numId),
        listItems(numId),
        listPlans(numId),
      ]);
      setFiles(loadedFiles);
      setItems(loadedItems);
      setPlans(loadedPlans);

      const planId = selectedPlanId ?? loadedPlans[0]?.id ?? null;
      if (planId !== null) {
        setSelectedPlanId(planId);
        setOperations(await listPlanOperations(planId));
      } else {
        setOperations([]);
      }

      if (selectedItemId !== null) {
        setCandidates(await listTmdbCandidates(selectedItemId));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки сессии");
    } finally {
      setLoading(false);
    }
  }, [numId, selectedItemId, selectedPlanId]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const summary = useMemo(() => {
    const video = files.filter((f) => f.is_video).length;
    const subtitles = files.filter((f) => f.is_subtitle).length;
    const matched = items.filter((item) => item.status === "MATCHED").length;
    const review = items.filter((item) => item.status === "NEEDS_REVIEW" || item.media_type === "UNKNOWN").length;
    return {
      totalFiles: files.length,
      video,
      subtitles,
      items: items.length,
      matched,
      review,
      operations: operations.length,
    };
  }, [files, items, operations]);

  const matchedItems = items.filter((item) => item.status === "MATCHED");
  const reviewItems = items.filter((item) => item.status === "NEEDS_REVIEW" || item.media_type === "UNKNOWN");
  const unmatchedItems = items.filter((item) => item.status === "UNMATCHED");
  const otherItems = items.filter(
    (item) => !matchedItems.includes(item) && !reviewItems.includes(item) && !unmatchedItems.includes(item),
  );

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

  async function runFullAnalysis() {
    setInfo(null);
    setError(null);
    setActionLoading("analysis");
    const nextStatus: Record<string, StepStatus> = {
      preflight: "pending",
      discover: "pending",
      parse: "pending",
      "local-ai": "pending",
      match: "pending",
      gemini: "pending",
      plan: "pending",
    };
    setStepStatus(nextStatus);

    const runStep = async (key: string, action: () => Promise<unknown>) => {
      nextStatus[key] = "running";
      setStepStatus({ ...nextStatus });
      await action();
      nextStatus[key] = "done";
      setStepStatus({ ...nextStatus });
      await loadAll();
    };

    try {
      await runStep("preflight", async () => {
        const result = await recognitionPreflight();
        setPreflightResult(result);
        if (!result.ok) {
          throw new ApiError(400, formatPreflightError(result));
        }
      });
      await runStep("discover", () => discoverSession(numId));
      await runStep("parse", () => parseSession(numId));
      await runStep("local-ai", () => normalizeLocalAi(numId));
      await runStep("match", () => matchTmdbSession(numId));
      await runStep("gemini", async () => {
        await resolveWithGemini(numId);
        await matchTmdbSession(numId, true);
      });
      await runStep("plan", () => createPlan(numId, true));
      setInfo("Анализ завершён. Проверьте найденные объекты и безопасный план.");
    } catch (err) {
      const failed = Object.entries(nextStatus).find(([, status]) => status === "running")?.[0];
      if (failed) nextStatus[failed] = "error";
      setStepStatus({ ...nextStatus });
      const raw = err instanceof ApiError ? err.message : "Анализ остановлен из-за ошибки.";
      setError(formatTmdbError(raw));
    } finally {
      setActionLoading(null);
      await loadAll();
    }
  }

  async function showCandidates(itemId: number) {
    setSelectedItemId(itemId);
    setCandidates(await listTmdbCandidates(itemId));
  }

  async function selectCandidate(candidateId: number) {
    if (selectedItemId === null) return;
    await runAction(
      "select-candidate",
      async () => {
        await selectTmdbCandidate(selectedItemId, candidateId);
        setCandidates(await listTmdbCandidates(selectedItemId));
      },
      "Кандидат выбран. Теперь можно пересобрать план.",
    );
  }

  async function showOperations(planId: number) {
    setSelectedPlanId(planId);
    setOperations(await listPlanOperations(planId));
  }

  if (!Number.isFinite(numId)) {
    return <div className="message error">Неверный ID сессии.</div>;
  }

  const busy = actionLoading !== null;
  const nestingWarning = session ? detectPathNestingWarning(session.source_path, session.target_path) : null;

  async function handleDeleteSession() {
    if (!session) return;
    const confirmed = window.confirm(t.sessions.deleteConfirm.replace("#{id}", String(session.id)));
    if (!confirmed) return;

    setActionLoading("delete");
    setError(null);
    setInfo(null);
    try {
      await deleteScanSession(session.id);
      navigate("/");
    } catch (err) {
      const msg = err instanceof Error ? err.message : t.sessions.deleteError;
      setError(msg);
    } finally {
      setActionLoading(null);
    }
  }

  return (
    <div>
      <p>
        <Link to="/">← К списку сессий</Link>
      </p>

      {error ? <div className="message error">{error}</div> : null}
      {info ? <div className="message success">{info}</div> : null}
      <div className="safety-notice">Это режим предварительного просмотра. Файлы пока не изменяются.</div>

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Сессия #{numId}</h2>
            {session ? (
              <p className="muted">
                {session.source_path} → {session.target_path}
              </p>
            ) : null}
          </div>
          <div className="section-actions">
            {session ? <Badge value={session.status} label={labelScanSessionStatus(session.status)} /> : null}
            {session ? (
              <button
                type="button"
                className="btn-danger"
                disabled={busy}
                onClick={() => void handleDeleteSession()}
              >
                {actionLoading === "delete" ? t.common.loading : t.detail.deleteSessionButton}
              </button>
            ) : null}
          </div>
        </div>
        {loading && !session ? <p className="muted">Загрузка...</p> : null}
        {nestingWarning ? <div className="message warning">{nestingWarning}</div> : null}
        {session?.error_message ? <div className="message error">{session.error_message}</div> : null}
      </section>

      <section className="panel analysis-panel">
        <div className="section-heading">
          <div>
            <h3>Анализ медиатеки</h3>
            <p>
              MediaForge просканирует папку, распознает имена файлов, найдёт совпадения в TMDB и построит
              безопасный план. Файлы не будут изменены.
            </p>
          </div>
          <button className="btn-primary analysis-button" disabled={busy} onClick={() => void runFullAnalysis()}>
            {actionLoading === "analysis" ? "Анализ выполняется..." : "Начать анализ"}
          </button>
        </div>
        <PreflightPanel result={preflightResult} status={stepStatus.preflight ?? "pending"} />
        <div className="analysis-steps">
          {analysisSteps.map((step) => (
            <div key={step.key} className="analysis-step">
              <span>{step.label}</span>
              <StepBadge status={stepStatus[step.key] ?? "pending"} />
            </div>
          ))}
        </div>
        <details className="manual-mode">
          <summary>Ручной режим</summary>
          <div className="pipeline-actions">
            <button disabled={busy} onClick={() => void runAction("discover", () => discoverSession(numId), "Сканирование завершено.")}>
              Сканировать
            </button>
            <button disabled={busy} onClick={() => void runAction("parse", () => parseSession(numId), "Распознавание завершено.")}>
              Распознать
            </button>
            <button disabled={busy} onClick={() => void runAction("local-ai", () => normalizeLocalAi(numId), "Local AI normalization finished.")}>
              Local AI
            </button>
            <button disabled={busy} onClick={() => void runAction("match", () => matchTmdbSession(numId), "Поиск TMDB завершён.")}>
              Найти в TMDB
            </button>
            <button disabled={busy} onClick={() => void runAction("gemini", async () => {
              await resolveWithGemini(numId);
              await matchTmdbSession(numId, true);
            }, "Gemini fallback and second TMDB pass finished.")}>
              Gemini + TMDB
            </button>
            <button disabled={busy} onClick={() => void runAction("plan", () => createPlan(numId), "План построен.")}>
              Построить план
            </button>
          </div>
        </details>
      </section>

      <section className="summary-dashboard">
        <SummaryCard label="Всего файлов" value={summary.totalFiles} />
        <SummaryCard label="Видео" value={summary.video} />
        <SummaryCard label="Субтитры" value={summary.subtitles} />
        <SummaryCard label="Распознано объектов" value={summary.items} />
        <SummaryCard label="Найдено в TMDB" value={summary.matched} />
        <SummaryCard label="Требуют проверки" value={summary.review} />
        <SummaryCard label="Операций в плане" value={summary.operations} />
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>Найдено в TMDB</h3>
          <span className="muted">{matchedItems.length}</span>
        </div>
        <ItemList items={matchedItems} busy={busy} onCandidates={showCandidates} onCorrection={async (item, payload) => {
          await createRecognitionCorrection(item.id, payload);
          await matchTmdbSession(numId, true);
          await loadAll();
        }} />
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>Требуют проверки</h3>
          <span className="muted">{reviewItems.length}</span>
        </div>
        <ItemList items={reviewItems} busy={busy} onCandidates={showCandidates} onCorrection={async (item, payload) => {
          await createRecognitionCorrection(item.id, payload);
          await matchTmdbSession(numId, true);
          await loadAll();
        }} />
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>Не найдено</h3>
          <span className="muted">{unmatchedItems.length}</span>
        </div>
        <ItemList items={unmatchedItems} busy={busy} onCandidates={showCandidates} onCorrection={async (item, payload) => {
          await createRecognitionCorrection(item.id, payload);
          await matchTmdbSession(numId, true);
          await loadAll();
        }} />
      </section>

      {otherItems.length > 0 ? (
        <section className="panel">
          <h3>Другие объекты</h3>
          <ItemList items={otherItems} busy={busy} onCandidates={showCandidates} onCorrection={async (item, payload) => {
          await createRecognitionCorrection(item.id, payload);
          await matchTmdbSession(numId, true);
          await loadAll();
        }} />
        </section>
      ) : null}

      {selectedItemId !== null ? (
        <section className="panel">
          <div className="section-heading">
            <h3>Кандидаты TMDB для объекта #{selectedItemId}</h3>
            <button type="button" onClick={() => setSelectedItemId(null)}>Закрыть</button>
          </div>
          {candidates.length === 0 ? <p className="muted">Кандидатов пока нет.</p> : null}
          <div className="candidate-list">
            {candidates.map((candidate) => (
              <div key={candidate.id} className={`candidate-card ${candidate.is_selected ? "selected" : ""}`}>
                <div className="section-heading">
                  <div>
                    <strong>{candidate.title}</strong>
                    <p className="muted">
                      {fmt(candidate.original_title)} · {labelMediaType(candidate.media_type)} · {fmt(candidate.year)}
                    </p>
                  </div>
                  {candidate.is_selected ? <Badge value="MATCHED" label="Выбран" /> : null}
                </div>
                <p>{candidate.overview ?? "Описание отсутствует."}</p>
                <div className="candidate-meta">
                  <span>Score: {candidate.score.toFixed(2)}</span>
                  <span>Рейтинг: {fmt(candidate.vote_average)}</span>
                  <span>Популярность: {fmt(candidate.popularity)}</span>
                </div>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={busy || candidate.is_selected}
                  onClick={() => void selectCandidate(candidate.id)}
                >
                  {candidate.is_selected ? "Этот вариант выбран" : "Выбрать этот вариант"}
                </button>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="panel">
        <div className="section-heading">
          <div>
            <h3>План операций</h3>
            <p className="muted">Это только план. Файлы пока не изменяются.</p>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() => void runAction("rebuild-plan", () => createPlan(numId, true), "План пересобран.")}
          >
            Пересобрать план
          </button>
        </div>
        {plans.length > 0 ? (
          <div className="plan-tabs">
            {plans.map((plan) => (
              <button
                key={plan.id}
                type="button"
                className={plan.id === (selectedPlanId ?? latestPlanId) ? "active" : ""}
                onClick={() => void showOperations(plan.id)}
              >
                План #{plan.id} · {labelPlanStatus(plan.status)}
              </button>
            ))}
          </div>
        ) : (
          <p className="muted">План ещё не построен.</p>
        )}
        <div className="operation-list">
          {operations.map((operation) => (
            <OperationPreview key={operation.id} operation={operation} />
          ))}
        </div>
      </section>

      <details className="panel">
        <summary>Технические детали</summary>
        <TechnicalTables
          files={files}
          items={items}
          plans={plans}
          operations={operations}
          onCandidates={showCandidates}
          onOperations={showOperations}
        />
      </details>
    </div>
  );
}


type CorrectionPayload = {
  corrected_title: string;
  corrected_year?: number | null;
  corrected_media_type?: string | null;
  removed_tokens?: string[];
  confidence?: number | null;
};

function ItemList({
  items,
  busy,
  onCandidates,
  onCorrection,
}: {
  items: MediaItem[];
  busy: boolean;
  onCandidates: (itemId: number) => Promise<void>;
  onCorrection: (item: MediaItem, payload: CorrectionPayload) => Promise<void>;
}) {
  if (items.length === 0) {
    return <p className="muted">Нет объектов в этом разделе.</p>;
  }
  return (
    <div className="item-list">
      {items.map((item) => (
        <div key={item.id} className="item-card">
          <div className="section-heading">
            <div>
              <strong>{item.parsed_title ?? item.original_title ?? `Object #${item.id}`}</strong>
              <p className="muted">
                {labelMediaType(item.media_type)}
                {item.year ? ` · ${item.year}` : ""}
                {item.season_number && item.episode_number ? ` · S${String(item.season_number).padStart(2, "0")}E${String(item.episode_number).padStart(2, "0")}` : ""}
              </p>
            </div>
            <Badge value={item.status} label={labelMediaItemStatus(item.status)} />
          </div>
          <div className="item-meta">
            <span>TMDB: {fmt(item.matched_title ?? item.tmdb_id)}</span>
            <span>Confidence: {formatPercent(item.match_confidence ?? item.ai_confidence ?? item.confidence)}</span>
          </div>
          <RecognitionEvidence item={item} />
          <CorrectionForm item={item} busy={busy} onSubmit={onCorrection} />
          <button type="button" onClick={() => void onCandidates(item.id)}>
            TMDB candidates
          </button>
        </div>
      ))}
    </div>
  );
}

function AiDiagnosticMessage({
  provider,
  status,
  validJson,
  error,
}: {
  provider: "Local AI" | "Gemini";
  status: string | null;
  validJson: boolean | null;
  error: string | null;
}) {
  const label = formatAiStatusLabel(status, validJson, Boolean(error));
  return (
    <div className="ai-diagnostic">
      <span>
        {provider}: {label}
      </span>
      {error ? (
        <details className="technical-error">
          <summary>Техническая ошибка</summary>
          <pre>{error}</pre>
        </details>
      ) : null}
    </div>
  );
}

function RecognitionEvidence({ item }: { item: MediaItem }) {
  return (
    <div className="recognition-evidence">
      <span>Parser: {fmt(item.parsed_title)} {item.year ? `(${item.year})` : ""}</span>
      <AiDiagnosticMessage
        provider="Local AI"
        status={item.local_ai_status}
        validJson={item.local_ai_response_valid_json}
        error={item.local_ai_error}
      />
      <span>Local AI duration: {fmt(item.local_ai_duration_ms)} ms</span>
      <span>Local AI model: {fmt(item.local_ai_model)}</span>
      <span>Local AI result: {fmt(item.ai_clean_title)} {formatPercent(item.ai_confidence)}</span>
      <AiDiagnosticMessage
        provider="Gemini"
        status={item.gemini_status}
        validJson={item.gemini_response_valid_json}
        error={item.gemini_error}
      />
      <span>Gemini duration: {fmt(item.gemini_duration_ms)} ms</span>
      <span>Gemini model: {fmt(item.gemini_model)}</span>
      <span>Gemini result: {fmt(item.gemini_clean_title)} {formatPercent(item.gemini_confidence)}</span>
      {item.tmdb_queries?.length ? <span>TMDB queries: {item.tmdb_queries.join(", ")}</span> : null}
      {item.ai_junk_tokens?.length ? <span>Removed tokens: {item.ai_junk_tokens.join(", ")}</span> : null}
      {item.ai_explanation ? <span>{item.ai_explanation}</span> : null}
      {item.gemini_explanation ? <span>{item.gemini_explanation}</span> : null}
    </div>
  );
}

function formatAiStatusLabel(status: string | null, validJson: boolean | null, hasError: boolean): string {
  if (!status || status === "not_run") return "not run";
  if (status === "success" && hasError) return "ответ получен, формат был исправлен автоматически";
  if (status === "success") return "success";
  if (status === "skipped") return "skipped";
  if (status === "failed" && validJson === false) return "response received, JSON invalid or call failed";
  if (status === "failed") return "ошибка формата ответа";
  return status;
}

function CorrectionForm({
  item,
  busy,
  onSubmit,
}: {
  item: MediaItem;
  busy: boolean;
  onSubmit: (item: MediaItem, payload: CorrectionPayload) => Promise<void>;
}) {
  const [title, setTitle] = useState(item.ai_clean_title ?? item.parsed_title ?? "");
  const [year, setYear] = useState<string>(String(item.ai_year ?? item.year ?? ""));
  const [mediaType, setMediaType] = useState(item.ai_media_type ?? item.media_type);
  const [tokens, setTokens] = useState((item.ai_junk_tokens ?? []).join(", "));

  useEffect(() => {
    setTitle(item.ai_clean_title ?? item.parsed_title ?? "");
    setYear(String(item.ai_year ?? item.year ?? ""));
    setMediaType(item.ai_media_type ?? item.media_type);
    setTokens((item.ai_junk_tokens ?? []).join(", "));
  }, [item]);

  return (
    <details className="correction-form">
      <summary>Manual correction</summary>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!title.trim()) return;
          void onSubmit(item, {
            corrected_title: title.trim(),
            corrected_year: year === "" ? null : Number(year),
            corrected_media_type: mediaType,
            removed_tokens: tokens.split(",").map((token) => token.trim()).filter(Boolean),
            confidence: 1,
          });
        }}
      >
        <div className="correction-grid">
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Clean title" />
          <input value={year} onChange={(e) => setYear(e.target.value)} placeholder="Year" inputMode="numeric" />
          <select value={mediaType} onChange={(e) => setMediaType(e.target.value)}>
            <option value="MOVIE">{labelMediaType("MOVIE")}</option>
            <option value="TV_EPISODE">{labelMediaType("TV_EPISODE")}</option>
            <option value="TV_SHOW">{labelMediaType("TV_SHOW")}</option>
            <option value="UNKNOWN">{labelMediaType("UNKNOWN")}</option>
          </select>
          <input value={tokens} onChange={(e) => setTokens(e.target.value)} placeholder="Tokens to remove" />
        </div>
        <button type="submit" disabled={busy || !title.trim()}>Save and retry TMDB</button>
      </form>
    </details>
  );
}
function TechnicalTables({
  files,
  items,
  plans,
  operations,
  onCandidates,
  onOperations,
}: {
  files: MediaFile[];
  items: MediaItem[];
  plans: OperationPlan[];
  operations: PlanOperation[];
  onCandidates: (itemId: number) => Promise<void>;
  onOperations: (planId: number) => Promise<void>;
}) {
  return (
    <div className="technical-tables">
      <h4>Файлы</h4>
      <div className="table-wrap">
        <table>
          <tbody>
            {files.map((f) => (
              <tr key={f.id}>
                <td>{f.id}</td>
                <td>{f.kind}</td>
                <td>{f.file_name}</td>
                <td>{fmt(f.media_item_id)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4>Объекты</h4>
      <div className="table-wrap">
        <table>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>{labelMediaType(item.media_type)}</td>
                <td>{labelMediaItemStatus(item.status)}</td>
                <td>{item.parsed_title ?? "—"}</td>
                <td>
                  <button type="button" onClick={() => void onCandidates(item.id)}>Кандидаты</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4>Планы</h4>
      <div className="table-wrap">
        <table>
          <tbody>
            {plans.map((plan) => (
              <tr key={plan.id}>
                <td>{plan.id}</td>
                <td>{labelPlanStatus(plan.status)}</td>
                <td>{formatDate(plan.created_at)}</td>
                <td>
                  <button type="button" onClick={() => void onOperations(plan.id)}>Операции</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4>Операции</h4>
      <div className="table-wrap">
        <table>
          <tbody>
            {operations.map((op) => (
              <tr key={op.id}>
                <td>{op.id}</td>
                <td>{labelOperationType(op.operation_type)}</td>
                <td>{labelOperationStatus(op.status)}</td>
                <td className="path-text">{op.source_path ?? "—"}</td>
                <td className="path-text">{op.target_path ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
