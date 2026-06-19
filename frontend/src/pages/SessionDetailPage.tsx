import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  analyzeTvSession,
  applyPlan,
  applyReviewDecision,
  applyTvReviewDecision,
  approveAllMatched,
  bulkReviewDecision,
  classifySession,
  createPlan,
  createTvPlan,
  createRecognitionCorrection,
  deleteScanSession,
  discoverSession,
  formatTmdbError,
  getScanSession,
  listFiles,
  listItems,
  listApplyRuns,
  listPlanOperations,
  listPlans,
  listTmdbCandidates,
  listTvShows,
  manualTmdbLookup,
  manualTmdbSearch,
  matchTmdbSession,
  normalizeLocalAi,
  parseSession,
  recognitionPreflight,
  resolveWithGemini,
  selectTmdbCandidate,
  validatePlan,
} from "../api";
import { ApplyConfirmModal } from "../components/plan/ApplyConfirmModal";
import { PlanApplyPanel } from "../components/plan/PlanApplyPanel";
import { BulkReviewToolbar } from "../components/review/BulkReviewToolbar";
import { CandidatesModal } from "../components/review/CandidatesModal";
import { CompactMediaItemRow } from "../components/review/CompactMediaItemRow";
import { formatPreflightStatusLabel, getPreflightShortMessage } from "../aiLabels";
import { t } from "../i18n";
import { validateIdLookupInput } from "../validation";
import {
  labelMediaItemStatus,
  labelMediaType,
  labelOperationStatus,
  labelOperationType,
  labelPlanStatus,
  labelScanSessionStatus,
  statusTone,
  type BadgeTone,
} from "../labels";
import type {
  BulkReviewResult,
  MediaFile,
  MediaClassificationResult,
  MediaItem,
  OperationPlan,
  ApplyRun,
  PlanApplyResult,
  PlanOperation,
  PlanValidationResult,
  RecognitionPreflightResult,
  ScanSession,
  TmdbMatchCandidate,
  TvShow,
} from "../types";
import { defaultSelectedIds, isBulkSelectable } from "../utils/bulkSelection";
import { buildPlanSummary } from "../utils/planSummary";
import { loadSection } from "../utils/sectionLoad";

type StepStatus = "pending" | "running" | "done" | "error";

const analysisSteps: { key: string; label: string }[] = [
  { key: "preflight", label: "Проверка AI" },
  { key: "discover", label: "Сканирование файлов" },
  { key: "classification", label: "Классификация папки" },
  { key: "parse", label: "Распознавание названий" },
  { key: "match", label: "Поиск в TMDB" },
  { key: "local-ai", label: "Быстрый AI-анализ" },
  { key: "gemini", label: "Умная AI-проверка" },
  { key: "tv", label: "Распознавание сериалов" },
  { key: "tv-plan", label: "План сериалов" },
  { key: "plan", label: "Построение безопасного плана" },
];

function formatDate(value: string): string {
  return new Date(value).toLocaleString("ru-RU");
}

function fmt(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
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

function Badge({
  value,
  label,
  tone,
}: {
  value: string | null | undefined;
  label: string;
  tone?: BadgeTone;
}) {
  return <span className={`status-badge ${tone ?? statusTone(value)}`}>{label}</span>;
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

function labelContentType(value: MediaClassificationResult["content_type"] | undefined): string {
  if (value === "movies") return "фильмы";
  if (value === "tv") return "сериалы";
  if (value === "mixed") return "смешанная папка";
  return "неизвестно";
}

function formatPreflightError(result: RecognitionPreflightResult): string {
  if (result.message) {
    return result.message;
  }
  if (!result.local.ok) {
    return getPreflightShortMessage(result.local) ?? "Локальная AI-модель не отвечает. Проверьте Ollama и настройки модели.";
  }
  if (!result.cloud.ok && !result.cloud_fallback?.ok) {
    return getPreflightShortMessage(result.cloud) ?? "Облачные модели недоступны. Проверьте ключ и настройки.";
  }
  return "Проверка AI не пройдена.";
}

function PreflightCheckBlock({
  title,
  check,
}: {
  title: string;
  check: RecognitionPreflightResult["local"] | null | undefined;
}) {
  const shortMessage = getPreflightShortMessage(check);
  return (
    <div>
      <span>{title}</span>
      <strong>{formatPreflightStatusLabel(check)}</strong>
      {check?.model ? <small>{check.model}</small> : null}
      {check?.provider ? <small>{check.provider}</small> : null}
      {check && !check.ok ? (
        <small>
          Попыток: {check.attempts ?? 1} · {check.duration_ms} мс
        </small>
      ) : null}
      {shortMessage ? <small className="error-text">{shortMessage}</small> : null}
      {check?.attempted_models && check.attempted_models.length > 0 ? (
        <ul className="chain-attempts">
          {check.attempted_models.map((attempt, index) => (
            <li key={`${attempt.model}-${index}`} className={attempt.ok ? "ok" : "failed"}>
              <strong>{index + 1}.</strong> {attempt.model}
              <span className="muted">
                {" "}
                {attempt.http_status ? `${attempt.http_status} · ` : ""}
                {attempt.ok ? "успешно" : attempt.error_type ?? "ошибка"} · {attempt.duration_ms} мс
                {attempt.attempts && attempt.attempts > 1 ? ` · ${attempt.attempts} попытки` : ""}
              </span>
              {!attempt.ok && attempt.human_message ? <span> — {attempt.human_message}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {check?.error ? (
        <details className="technical-error">
          <summary>Технические детали</summary>
          <pre>{check.error}</pre>
        </details>
      ) : null}
    </div>
  );
}

function PreflightPanel({ result, status }: { result: RecognitionPreflightResult | null; status: StepStatus }) {
  return (
    <div className="preflight-panel">
      <div className="section-heading">
        <strong>Проверка AI</strong>
        <StepBadge status={status} />
      </div>
      <div className="preflight-grid">
        <PreflightCheckBlock title="Быстрый AI-анализ" check={result?.local} />
        <PreflightCheckBlock title="Умная AI-проверка" check={result?.cloud} />
        {result?.cloud_fallback ? (
          <PreflightCheckBlock title="Запасная AI-модель" check={result.cloud_fallback} />
        ) : null}
      </div>
      {result?.warning ? <div className="message warning">{result.warning}</div> : null}
    </div>
  );
}

export function SessionDetailPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const numId = Number(sessionId);

  const [session, setSession] = useState<ScanSession | null>(null);
  const [files, setFiles] = useState<MediaFile[]>([]);
  const [classification, setClassification] = useState<MediaClassificationResult | null>(null);
  const [items, setItems] = useState<MediaItem[]>([]);
  const [tvShows, setTvShows] = useState<TvShow[]>([]);
  const [plans, setPlans] = useState<OperationPlan[]>([]);
  const [operations, setOperations] = useState<PlanOperation[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [candidates, setCandidates] = useState<TmdbMatchCandidate[]>([]);
  const [stepStatus, setStepStatus] = useState<Record<string, StepStatus>>({
    preflight: "pending",
    discover: "pending",
    classification: "pending",
    parse: "pending",
    "local-ai": "pending",
    match: "pending",
    gemini: "pending",
    tv: "pending",
    "tv-plan": "pending",
    plan: "pending",
  });

  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [applyRunsError, setApplyRunsError] = useState<string | null>(null);
  const [applyRuns, setApplyRuns] = useState<ApplyRun[]>([]);
  const [info, setInfo] = useState<string | null>(null);
  const [preflightResult, setPreflightResult] = useState<RecognitionPreflightResult | null>(null);
  const [selectedItemIds, setSelectedItemIds] = useState<Set<number>>(new Set());
  const [bulkResult, setBulkResult] = useState<BulkReviewResult | null>(null);
  const [validationResult, setValidationResult] = useState<PlanValidationResult | null>(null);
  const [applyResult, setApplyResult] = useState<PlanApplyResult | null>(null);
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [applyConfirmChecked, setApplyConfirmChecked] = useState(false);
  const [analysisCollapsed, setAnalysisCollapsed] = useState(false);
  const [candidatesModalOpen, setCandidatesModalOpen] = useState(false);

  const latestPlanId = plans[0]?.id ?? null;

  const loadApplyRuns = useCallback(async (planId: number | null) => {
    if (planId === null) {
      setApplyRuns([]);
      setApplyRunsError(null);
      return;
    }
    await loadSection(
      () => listApplyRuns(planId),
      setApplyRuns,
      setApplyRunsError,
      "Не удалось загрузить журнал применения",
    );
  }, []);

  const loadPlan = useCallback(async () => {
    const loadedPlans = await loadSection(
      () => listPlans(numId),
      setPlans,
      setPlanError,
      "Не удалось загрузить план операций",
    );
    const planId = selectedPlanId ?? loadedPlans?.[0]?.id ?? null;
    if (planId !== null) {
      setSelectedPlanId(planId);
      const ops = await loadSection(
        () => listPlanOperations(planId),
        setOperations,
        setPlanError,
        "Не удалось загрузить операции плана",
      );
      if (ops !== null) {
        await loadApplyRuns(planId);
      }
    } else {
      setOperations([]);
      setApplyRuns([]);
      setApplyRunsError(null);
    }
  }, [numId, selectedPlanId, loadApplyRuns]);

  const loadReview = useCallback(async () => {
    const loadedFiles = await loadSection(
      () => listFiles(numId),
      setFiles,
      setReviewError,
      "Не удалось загрузить список файлов",
    );
    await loadSection(
      () => classifySession(numId),
      setClassification,
      setReviewError,
      "Не удалось классифицировать содержимое папки",
    );
    const loadedItems = await loadSection(
      () => listItems(numId),
      setItems,
      setReviewError,
      "Не удалось загрузить список фильмов",
    );
    const loadedTvShows = await loadSection(
      () => listTvShows(numId),
      setTvShows,
      setReviewError,
      "Не удалось загрузить список сериалов",
    );
    return loadedFiles !== null && loadedItems !== null && loadedTvShows !== null;
  }, [numId]);

  const loadSessionHeader = useCallback(async () => {
    try {
      const loadedSession = await getScanSession(numId);
      setSession(loadedSession);
      setSessionError(null);
      return loadedSession;
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Не удалось загрузить сессию";
      setSessionError(message);
      if (err instanceof ApiError && err.status === 404) {
        setError(message);
      }
      return null;
    }
  }, [numId]);

  const loadAll = useCallback(async () => {
    if (!Number.isFinite(numId)) return;
    setLoading(true);
    setError(null);

    const loadedSession = await loadSessionHeader();
    if (loadedSession === null) {
      setLoading(false);
      return;
    }

    await Promise.all([loadReview(), loadPlan()]);

    if (selectedItemId !== null) {
      try {
        const loaded = await listTmdbCandidates(selectedItemId);
        setCandidates([...loaded].sort((a, b) => b.id - a.id));
      } catch {
        // Candidate refresh is optional; modal shows its own errors.
      }
    }

    setLoading(false);
  }, [numId, selectedItemId, loadSessionHeader, loadReview, loadPlan]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const summary = useMemo(() => {
    const video = files.filter((f) => f.is_video).length;
    const subtitles = files.filter((f) => f.is_subtitle).length;
    const matched = items.filter((item) => item.status === "MATCHED").length;
    const review = items.filter((item) => item.status === "NEEDS_REVIEW" || item.media_type === "UNKNOWN").length;
    const reused = items.filter((item) => item.reused_from_memory).length;
    const fresh = items.filter((item) => !item.reused_from_memory).length;
    const ignored = items.filter((item) => item.review_decision === "ignored").length;
    const deferred = items.filter((item) => item.review_decision === "deferred").length;
    const planSummary = buildPlanSummary(operations, items, validationResult?.conflict_count ?? 0);
    return {
      totalFiles: files.length,
      video,
      subtitles,
      items: items.length,
      matched,
      review,
      reused,
      fresh,
      ignored,
      deferred,
      operations: operations.length,
      conflicts: planSummary.conflicts,
    };
  }, [files, items, operations, validationResult]);

  const planExcluded = useMemo(() => {
    const ignored = items.filter((item) => item.review_decision === "ignored").length;
    const deferred = items.filter((item) => item.review_decision === "deferred").length;
    const plannable = items.filter(
      (item) => item.status === "MATCHED" && !["ignored", "deferred"].includes(item.review_decision),
    ).length;
    return { ignored, deferred, plannable };
  }, [items]);

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
      classification: "pending",
      parse: "pending",
      "local-ai": "pending",
      match: "pending",
      gemini: "pending",
      tv: "pending",
      "tv-plan": "pending",
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
      await runStep("classification", () => classifySession(numId));
      await runStep("parse", () => parseSession(numId));
      await runStep("match", () => matchTmdbSession(numId));
      await runStep("local-ai", () => normalizeLocalAi(numId));
      await runStep("gemini", async () => {
        await resolveWithGemini(numId);
        await matchTmdbSession(numId, true);
      });
      let tvShowCount = 0;
      await runStep("tv", async () => {
        const result = await analyzeTvSession(numId, true);
        tvShowCount = result.show_count;
      });
      if (tvShowCount > 0) {
        await runStep("tv-plan", () => createTvPlan(numId, true));
      } else {
        nextStatus["tv-plan"] = "done";
        setStepStatus({ ...nextStatus });
      }
      await runStep("plan", () => createPlan(numId, true));
      setAnalysisCollapsed(true);
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
    setCandidatesModalOpen(true);
    setReviewError(null);
    try {
      const loaded = await listTmdbCandidates(itemId);
      setCandidates([...loaded].sort((a, b) => b.id - a.id));
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Не удалось загрузить кандидатов TMDB";
      setReviewError(msg);
      setCandidates([]);
    }
  }

  function closeCandidatesModal() {
    setCandidatesModalOpen(false);
    setSelectedItemId(null);
    setCandidates([]);
  }

  async function selectCandidate(candidateId: number) {
    if (selectedItemId === null) return;
    await runAction(
      "select-candidate",
      async () => {
        await selectTmdbCandidate(selectedItemId, candidateId);
        setCandidates(await listTmdbCandidates(selectedItemId));
        setItems(await listItems(numId));
      },
      "Кандидат выбран. Теперь можно пересобрать план.",
    );
  }

  async function showOperations(planId: number) {
    setSelectedPlanId(planId);
    setOperations(await listPlanOperations(planId));
    setValidationResult(null);
    setApplyResult(null);
    await loadApplyRuns(planId);
  }

  useEffect(() => {
    if (items.length > 0 && selectedItemIds.size === 0) {
      setSelectedItemIds(new Set(defaultSelectedIds(items)));
    }
  }, [items, selectedItemIds.size]);

  const activePlan = plans.find((p) => p.id === (selectedPlanId ?? latestPlanId)) ?? plans[0] ?? null;
  const planStale = useMemo(() => {
    if (!activePlan) return false;
    const planTime = new Date(activePlan.updated_at).getTime();
    return items.some(
      (item) => item.reviewed_at && new Date(item.reviewed_at).getTime() > planTime,
    );
  }, [activePlan, items]);

  async function handleBulkApproveAll() {
    await runAction("bulk-approve-all", async () => {
      const result = await approveAllMatched(numId, { scope: "matched" });
      setBulkResult(result);
      setInfo(`Одобрено: ${result.approved_count} · пропущено: ${result.skipped_count}`);
    }, "Массовое одобрение завершено.");
  }

  async function handleBulkApproveSelected() {
    const ids = [...selectedItemIds];
    if (ids.length === 0) return;
    await runAction("bulk-approve-selected", async () => {
      const result = await approveAllMatched(numId, { scope: "selected", item_ids: ids });
      setBulkResult(result);
      setInfo(`Одобрено: ${result.approved_count} · пропущено: ${result.skipped_count}`);
    }, "Выбранные объекты одобрены.");
  }

  async function handleBulkDecision(decision: "ignored" | "deferred") {
    const ids = [...selectedItemIds];
    if (ids.length === 0) return;
    const note = decision === "ignored" ? "Не добавлять" : "Отложено";
    await runAction(`bulk-${decision}`, async () => {
      const result = await bulkReviewDecision(numId, { item_ids: ids, decision, note });
      setBulkResult(result);
    }, decision === "ignored" ? "Выбранные объекты исключены." : "Выбранные объекты отложены.");
  }

  async function handleValidatePlan() {
    const planId = selectedPlanId ?? latestPlanId;
    if (planId === null) return;
    await runAction("validate-plan", async () => {
      const result = await validatePlan(planId);
      setValidationResult(result);
      setOperations(result.operations);
      setInfo(
        `Проверка: OK ${result.ok_count}, предупреждения ${result.warning_count}, конфликты ${result.conflict_count}`,
      );
    }, "План проверен.");
  }

  async function handleApplyPlan() {
    const planId = selectedPlanId ?? latestPlanId;
    if (planId === null) return;
    setShowApplyModal(false);
    await runAction("apply-plan", async () => {
      const result = await applyPlan(planId, { confirm: true });
      setApplyResult(result);
      setInfo(`Применено ${result.done_operations} из ${result.total_operations} операций.`);
      setOperations(await listPlanOperations(planId));
      setPlans(await listPlans(numId));
      await loadApplyRuns(planId);
    }, "План применён.");
  }

  function toggleItemSelection(itemId: number) {
    setSelectedItemIds((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
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

  const selectedCandidateItem = selectedItemId !== null ? items.find((i) => i.id === selectedItemId) ?? null : null;

  return (
    <div>
      {error ? <div className="message error">{error}</div> : null}
      {info ? <div className="message success">{info}</div> : null}
      <div className="safety-notice">
        План — предварительный просмотр. Файлы изменятся только после явного подтверждения «Применить план».
      </div>

      <section className="panel">
        <div className="session-header-row">
          <Link to="/">← Назад</Link>
          {session ? (
            <div className="session-header-actions">
              <Badge value={session.status} label={labelScanSessionStatus(session.status)} />
              <button
                type="button"
                className="btn-danger"
                disabled={busy}
                onClick={() => void handleDeleteSession()}
              >
                {actionLoading === "delete" ? t.common.loading : t.detail.deleteSessionButton}
              </button>
            </div>
          ) : null}
        </div>
        <div className="section-heading">
          <div>
            <h2>Сессия #{numId}</h2>
            {session ? (
              <p className="muted">
                {session.source_path} → {session.target_path}
              </p>
            ) : null}
          </div>
        </div>
        {loading && !session ? <p className="muted">Загрузка...</p> : null}
        {sessionError && !error ? <div className="message error">{sessionError}</div> : null}
        {nestingWarning ? <div className="message warning">{nestingWarning}</div> : null}
        {session?.error_message ? <div className="message error">{session.error_message}</div> : null}
      </section>

      <section className="panel analysis-panel">
        <div className="section-heading">
          <div>
            <h3>Анализ медиатеки</h3>
            {analysisCollapsed && preflightResult?.ok ? (
              <p className="muted compact-preflight-status">
                AI проверен
                {preflightResult.local.ok ? ": локальная модель работает" : ": локальная модель недоступна"}
                {preflightResult.cloud.ok ? ", основная облачная работает" : ", основная облачная недоступна"}
                {preflightResult.cloud_fallback?.ok ? ", использована запасная" : ""}
              </p>
            ) : (
              <p className="muted">
                MediaForge просканирует папку, распознает имена файлов, найдёт совпадения в TMDB и построит план.
              </p>
            )}
          </div>
          <button className="btn-primary analysis-button" disabled={busy} onClick={() => void runFullAnalysis()}>
            {actionLoading === "analysis" ? "Анализ выполняется..." : "Начать анализ"}
          </button>
        </div>
        {preflightResult?.warning ? <div className="message warning compact-ai-warning">{preflightResult.warning}</div> : null}
        <details className="analysis-details" open={!analysisCollapsed}>
          <summary>Статус pipeline и проверка AI</summary>
          <PreflightPanel result={preflightResult} status={stepStatus.preflight ?? "pending"} />
          <div className="analysis-steps compact-analysis-steps">
            {analysisSteps.map((step) => (
              <span key={step.key} className="analysis-step-chip">
                {step.label} <StepBadge status={stepStatus[step.key] ?? "pending"} />
              </span>
            ))}
          </div>
        </details>
        <details className="manual-mode">
          <summary>Ручной режим</summary>
          <div className="pipeline-actions">
            <button disabled={busy} onClick={() => void runAction("discover", () => discoverSession(numId), "Сканирование завершено.")}>
              Сканировать
            </button>
            <button disabled={busy} onClick={() => void runAction("parse", () => parseSession(numId), "Распознавание завершено.")}>
              Распознать
            </button>
            <button disabled={busy} onClick={() => void runAction("local-ai", () => normalizeLocalAi(numId), "Локальная AI-модель завершила нормализацию.")}>
              Локальная AI-модель
            </button>
            <button disabled={busy} onClick={() => void runAction("match", () => matchTmdbSession(numId), "Поиск TMDB завершён.")}>
              Найти в TMDB
            </button>
            <button disabled={busy} onClick={() => void runAction("gemini", async () => {
              await resolveWithGemini(numId);
              await matchTmdbSession(numId, true);
            }, "Запасная облачная модель и повторный поиск в TMDB завершены.")}>
              Запасная модель + TMDB
            </button>
            <button disabled={busy} onClick={() => void runAction("tv", () => analyzeTvSession(numId, true), "Распознавание сериалов завершено.")}>
              Распознать сериалы
            </button>
            <button disabled={busy} onClick={() => void runAction("tv-plan", () => createTvPlan(numId, true), "План сериалов построен.")}>
              Построить план сериалов
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
        <SummaryCard label="Новых" value={summary.fresh} />
        <SummaryCard label="Уже обработано" value={summary.reused} />
        <SummaryCard label="Найдено" value={summary.matched} />
        <SummaryCard label="Требуют проверки" value={summary.review} />
        <SummaryCard label="Исключено" value={summary.ignored} />
        <SummaryCard label="Отложено" value={summary.deferred} />
        <SummaryCard label="Операций в плане" value={summary.operations} />
        <SummaryCard label="Конфликтов" value={summary.conflicts} />
      </section>

      {classification ? (
        <section className="panel compact-review-section">
          <div className="section-heading">
            <h3>Тип содержимого: {labelContentType(classification.content_type)}</h3>
            <span className="muted">уверенность {Math.round(classification.confidence * 100)}%</span>
          </div>
          <p className="muted">{classification.reason}</p>
          <p className="muted">
            Видео: {classification.video_files} · Вложенных папок: {classification.nested_folder_count} · TV-признаков: {classification.tv_like_files} · Фильм-признаков: {classification.movie_like_files}
          </p>
          {classification.known_extensions.length > 0 ? (
            <p className="muted">
              Видео-расширения: {classification.known_extensions.map((item) => `${item.extension} (${item.count})`).join(", ")}
            </p>
          ) : null}
          {classification.ignored_extensions.length > 0 ? (
            <p className="muted">
              Игнорируются: {classification.ignored_extensions.map((item) => `${item.extension} (${item.count})`).join(", ")}
            </p>
          ) : null}
          {classification.warnings.map((warning) => (
            <div className="message warning" key={warning}>{warning}</div>
          ))}
          {classification.needs_user_decision ? (
            <div className="manual-review-actions">
              <button type="button" disabled={busy} onClick={() => void runAction("parse", () => parseSession(numId), "Папка будет обработана как фильмы.")}>Фильмы</button>
              <button type="button" disabled={busy} onClick={() => void runAction("tv", () => analyzeTvSession(numId, true), "Папка будет обработана как сериалы.")}>Сериалы</button>
              <button type="button" disabled={busy} onClick={() => void runAction("mixed", async () => {
                await parseSession(numId);
                await analyzeTvSession(numId, true);
              }, "Папка будет обработана как смешанная.")}>Смешанная папка</button>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="panel review-main-panel">
        <div className="section-heading">
          <h3>Проверка найденных фильмов</h3>
          <span className="muted">
            В план: {planExcluded.plannable} · исключено: {planExcluded.ignored} · отложено: {planExcluded.deferred}
          </span>
        </div>
        {reviewError ? <div className="message error">{reviewError}</div> : null}
        <BulkReviewToolbar
          busy={busy}
          selectedCount={selectedItemIds.size}
          plannable={planExcluded.plannable}
          ignored={planExcluded.ignored}
          deferred={planExcluded.deferred}
          lastResult={bulkResult}
          onApproveAll={() => void handleBulkApproveAll()}
          onApproveSelected={() => void handleBulkApproveSelected()}
          onIgnoreSelected={() => void handleBulkDecision("ignored")}
          onDeferSelected={() => void handleBulkDecision("deferred")}
          onClearSelection={() => setSelectedItemIds(new Set())}
          onRebuildPlan={() => void runAction("rebuild-plan", () => createPlan(numId, true), "План пересобран.")}
        />
        <ItemList
          variant="matched"
          items={matchedItems}
          busy={busy}
          selectable
          selectedIds={selectedItemIds}
          onToggleSelect={toggleItemSelection}
          onCandidates={showCandidates}
          onDecision={async (itemId, payload) => {
            await applyReviewDecision(itemId, payload);
            await loadAll();
          }}
          onCorrection={async (item, payload) => {
            await createRecognitionCorrection(item.id, payload);
            await matchTmdbSession(numId, true);
            await loadAll();
          }}
        />
      </section>

      <TvReviewSection
        shows={tvShows}
        busy={busy}
        onDecision={async (showId, decision) => {
          await applyTvReviewDecision(showId, { decision });
          await loadAll();
        }}
        onRebuildPlan={() => void runAction("tv-plan", () => createTvPlan(numId, true), "План сериалов пересобран.")}
      />

      {reviewItems.length > 0 ? (
        <section className="panel compact-review-section">
          <div className="section-heading">
            <h3>Требуют проверки</h3>
            <span className="muted">{reviewItems.length}</span>
          </div>
          <ItemList variant="review" items={reviewItems} busy={busy} onCandidates={showCandidates} onDecision={async (itemId, payload) => {
            await applyReviewDecision(itemId, payload);
            await loadAll();
          }} onCorrection={async (item, payload) => {
            await createRecognitionCorrection(item.id, payload);
            await matchTmdbSession(numId, true);
            await loadAll();
          }} />
        </section>
      ) : (
        <p className="muted compact-section-row">Требуют проверки: 0</p>
      )}

      {unmatchedItems.length > 0 ? (
        <section className="panel compact-review-section">
          <div className="section-heading">
            <h3>Не найдено</h3>
            <span className="muted">{unmatchedItems.length}</span>
          </div>
          <ItemList variant="review" items={unmatchedItems} busy={busy} onCandidates={showCandidates} onDecision={async (itemId, payload) => {
            await applyReviewDecision(itemId, payload);
            await loadAll();
          }} onCorrection={async (item, payload) => {
            await createRecognitionCorrection(item.id, payload);
            await matchTmdbSession(numId, true);
            await loadAll();
          }} />
        </section>
      ) : (
        <p className="muted compact-section-row">Не найдено: 0</p>
      )}

      {otherItems.length > 0 ? (
        <section className="panel">
          <h3>Другие объекты</h3>
          <ItemList variant="review" items={otherItems} busy={busy} onCandidates={showCandidates} onDecision={async (itemId, payload) => {
          await applyReviewDecision(itemId, payload);
          await loadAll();
        }} onCorrection={async (item, payload) => {
          await createRecognitionCorrection(item.id, payload);
          await matchTmdbSession(numId, true);
          await loadAll();
        }} />
        </section>
      ) : null}

      <CandidatesModal
        open={candidatesModalOpen}
        item={selectedCandidateItem}
        candidates={candidates}
        busy={busy}
        onClose={closeCandidatesModal}
        onSelect={(candidateId) => void selectCandidate(candidateId)}
        onCandidatesChange={setCandidates}
        onError={setReviewError}
      />

      {planError ? <div className="message error">{planError}</div> : null}
      <PlanApplyPanel
        plans={plans}
        selectedPlanId={selectedPlanId ?? latestPlanId}
        operations={operations}
        items={items}
        validation={validationResult}
        applyResult={applyResult}
        applyRuns={applyRuns}
        applyRunsError={applyRunsError}
        busy={busy}
        planStale={planStale}
        onSelectPlan={(planId) => void showOperations(planId)}
        onValidate={() => void handleValidatePlan()}
        onApplyClick={() => {
          setApplyConfirmChecked(false);
          setShowApplyModal(true);
        }}
      />

      <ApplyConfirmModal
        open={showApplyModal}
        busy={busy}
        checked={applyConfirmChecked}
        onCheckedChange={setApplyConfirmChecked}
        onConfirm={() => void handleApplyPlan()}
        onCancel={() => setShowApplyModal(false)}
      />

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

type ReviewPayload = {
  decision: string;
  note?: string | null;
  manual_title?: string | null;
  manual_year?: number | null;
  manual_tmdb_id?: number | null;
  manual_imdb_id?: string | null;
  manual_tvdb_id?: number | null;
  manual_media_type?: string | null;
};

function TvReviewSection({
  shows,
  busy,
  onDecision,
  onRebuildPlan,
}: {
  shows: TvShow[];
  busy: boolean;
  onDecision: (showId: number, decision: string) => Promise<void>;
  onRebuildPlan: () => void;
}) {
  const episodeCount = shows.reduce(
    (total, show) => total + show.seasons.reduce((seasonTotal, season) => seasonTotal + season.episodes.length, 0),
    0,
  );
  const needsReview = shows.filter((show) => show.needs_review || show.seasons.some((season) => season.episodes.some((episode) => episode.needs_review))).length;

  if (shows.length === 0) {
    return <p className="muted compact-section-row">Сериалы: не обнаружены</p>;
  }

  return (
    <section className="panel compact-review-section tv-review-section">
      <div className="section-heading">
        <h3>Проверка сериалов</h3>
        <span className="muted">
          Сериалов: {shows.length} · Эпизодов: {episodeCount} · Требуют проверки: {needsReview}
        </span>
      </div>
      <div className="review-item-list">
        {shows.map((show) => (
          <article className="compact-media-row tv-show-row" key={show.id}>
            {show.poster_url ? <img className="poster-thumb" src={show.poster_url} alt="" /> : <div className="poster-thumb placeholder" />}
            <div className="compact-media-main">
              <div className="compact-media-title-row">
                <strong>{show.title}{show.year ? ` (${show.year})` : ""}</strong>
                <span className={`status-badge ${show.needs_review ? "warning" : "success"}`}>
                  {show.needs_review ? "Требует проверки" : "Готово"}
                </span>
              </div>
              <p className="muted">
                Сериал · {show.tmdb_id ? "найдено в TMDB" : "TMDB не выбран"}
                {show.tvdb_id ? ` · TVDB ${show.tvdb_id}` : ""}
                {show.imdb_id ? ` · IMDb ${show.imdb_id}` : ""}
              </p>
              {show.overview ? <p className="compact-overview">{show.overview}</p> : null}
              {show.warnings?.length ? <p className="message warning">{show.warnings.join("; ")}</p> : null}
              <div className="manual-review-actions">
                <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "approved")}>Одобрить сериал</button>
                <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "ignored")}>Не добавлять</button>
                <button type="button" disabled={busy} onClick={() => void onDecision(show.id, "deferred")}>Отложить</button>
              </div>
              <div className="tv-season-list">
                {show.seasons.map((season) => (
                  <details key={season.id} open className="tv-season-details">
                    <summary>
                      Сезон {season.season_number} — {season.episodes.length} серий
                    </summary>
                    <div className="tv-episode-list">
                      {season.episodes.map((episode) => (
                        <div className="tv-episode-row" key={episode.id}>
                          <span>S{String(episode.season_number).padStart(2, "0")}E{String(episode.episode_number).padStart(2, "0")}</span>
                          <span className="path-text">{episode.source_path ?? "—"}</span>
                          <span>{episode.title ?? "Название будет уточнено"}</span>
                          {episode.issue || episode.warning ? <span className="status-badge warning">{episode.issue ?? episode.warning}</span> : null}
                        </div>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            </div>
          </article>
        ))}
      </div>
      <div className="pipeline-actions">
        <button type="button" disabled={busy || needsReview > 0} onClick={onRebuildPlan}>
          Пересобрать план сериалов
        </button>
      </div>
    </section>
  );
}

function ItemList({
  items,
  variant,
  busy,
  selectable = false,
  selectedIds,
  onToggleSelect,
  onCandidates,
  onCorrection,
  onDecision,
}: {
  items: MediaItem[];
  variant: "matched" | "review";
  busy: boolean;
  selectable?: boolean;
  selectedIds?: Set<number>;
  onToggleSelect?: (itemId: number) => void;
  onCandidates: (itemId: number) => Promise<void>;
  onCorrection: (item: MediaItem, payload: CorrectionPayload) => Promise<void>;
  onDecision: (itemId: number, payload: ReviewPayload) => Promise<void>;
}) {
  if (items.length === 0) {
    return <p className="muted">Нет объектов в этом разделе.</p>;
  }
  return (
    <div className="review-item-list">
      {items.map((item) => (
        <CompactMediaItemRow
          key={item.id}
          item={item}
          variant={variant}
          busy={busy}
          selectable={selectable && isBulkSelectable(item)}
          selected={selectedIds?.has(item.id) ?? false}
          onToggleSelect={onToggleSelect}
          onCandidates={onCandidates}
          onCorrection={onCorrection}
          onDecision={onDecision}
          renderManualReview={(rowItem) => (
            <ManualReviewPanel item={rowItem} busy={busy} onCandidates={onCandidates} onDecision={onDecision} />
          )}
        />
      ))}
    </div>
  );
}

function ManualReviewPanel({
  item,
  busy,
  onCandidates,
  onDecision,
}: {
  item: MediaItem;
  busy: boolean;
  onCandidates: (itemId: number) => Promise<void>;
  onDecision: (itemId: number, payload: ReviewPayload) => Promise<void>;
}) {
  const [title, setTitle] = useState(item.manual_title ?? item.parsed_title ?? "");
  const [year, setYear] = useState(String(item.manual_year ?? item.year ?? ""));
  const [mediaType, setMediaType] = useState(item.manual_media_type ?? item.media_type);
  const [tmdbId, setTmdbId] = useState(String(item.manual_tmdb_id ?? item.tmdb_id ?? ""));
  const [imdbId, setImdbId] = useState(item.manual_imdb_id ?? item.imdb_id ?? "");
  const [tvdbId, setTvdbId] = useState(String(item.manual_tvdb_id ?? item.tvdb_id ?? ""));
  const [idError, setIdError] = useState<string | null>(null);

  return (
    <div className="manual-review-panel">
      <h4>Найти по названию</h4>
      <div className="manual-review-grid">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Название" />
        <input value={year} onChange={(e) => setYear(e.target.value)} placeholder="Год" inputMode="numeric" />
        <select value={mediaType} onChange={(e) => setMediaType(e.target.value)}>
          <option value="MOVIE">Фильм</option>
          <option value="TV_SHOW">Сериал</option>
          <option value="TV_EPISODE">Серия</option>
        </select>
      </div>
      <div className="manual-review-actions">
        <button
          type="button"
          disabled={busy || !title.trim()}
          onClick={() =>
            void (async () => {
              await manualTmdbSearch(item.id, {
                query: title.trim(),
                year: year === "" ? null : Number(year),
                media_type: mediaType === "MOVIE" ? "movie" : "tv",
              });
              await onCandidates(item.id);
            })()
          }
        >
          Искать в TMDB
        </button>
      </div>
      <h4>Загрузить по ID</h4>
      <p className="muted manual-review-hint">
        Заполните один из ID. TMDB ID используется напрямую. IMDb/TVDB ищутся через TMDB Find.
      </p>
      <div className="manual-review-grid">
        <input value={tmdbId} onChange={(e) => setTmdbId(e.target.value)} placeholder="TMDB ID" inputMode="numeric" />
        <input value={imdbId} onChange={(e) => setImdbId(e.target.value)} placeholder="IMDb ID" />
        <input value={tvdbId} onChange={(e) => setTvdbId(e.target.value)} placeholder="TVDB ID" inputMode="numeric" />
      </div>
      {idError ? <p className="message error">{idError}</p> : null}
      <div className="manual-review-actions">
        <button
          type="button"
          disabled={busy || (!tmdbId && !imdbId && !tvdbId)}
          onClick={() =>
            void (async () => {
              const validation = validateIdLookupInput(tmdbId, imdbId, tvdbId);
              if (!validation.valid) {
                setIdError(validation.error ?? "Некорректный ID");
                return;
              }
              setIdError(null);
              await manualTmdbLookup(item.id, {
                tmdb_id: tmdbId.trim() ? Number(tmdbId) : null,
                imdb_id: imdbId.trim() || null,
                tvdb_id: tvdbId.trim() ? Number(tvdbId) : null,
                media_type: mediaType === "MOVIE" ? "movie" : "tv",
              });
              await onCandidates(item.id);
            })()
          }
        >
          Загрузить по ID
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void onDecision(item.id, {
              decision: "approved",
              note: "Подтверждено пользователем",
            })
          }
        >
          Подтвердить выбранный вариант
        </button>
        <button type="button" disabled={busy} onClick={() => void onDecision(item.id, { decision: "ignored", note: "Не добавлять" })}>
          Не добавлять
        </button>
        <button type="button" disabled={busy} onClick={() => void onDecision(item.id, { decision: "deferred", note: "Отложено" })}>
          Отложить
        </button>
        <button
          type="button"
          disabled={busy || (!tmdbId && !imdbId)}
          onClick={() =>
            void onDecision(item.id, {
              decision: "manual_override",
              manual_title: title.trim() || null,
              manual_year: year === "" ? null : Number(year),
              manual_tmdb_id: tmdbId ? Number(tmdbId) : null,
              manual_imdb_id: imdbId || null,
              manual_tvdb_id: tvdbId ? Number(tvdbId) : null,
              manual_media_type: mediaType,
              note: "Исправлено вручную",
            })
          }
        >
          Сохранить исправление
        </button>
      </div>
    </div>
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
      <details>
        <summary>Технический список операций</summary>
        <div className="table-wrap">
          <table>
            <tbody>
              {operations.map((op) => (
                <tr key={op.id}>
                  <td>{op.id}</td>
                  <td>{labelOperationType(op.operation_type)}</td>
                  <td>{labelOperationStatus(op.status)}</td>
                  <td>{op.validation_status ?? "—"}</td>
                  <td className="path-text">{op.source_path ?? "—"}</td>
                  <td className="path-text">{op.target_path ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
