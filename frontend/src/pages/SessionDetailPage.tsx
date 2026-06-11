import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  applyPlan,
  applyReviewDecision,
  approveAllMatched,
  bulkReviewDecision,
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
import {
  formatAiStatusLabel,
  formatPreflightStatusLabel,
  getPreflightShortMessage,
  humanizeAiError,
} from "../aiLabels";
import { getItemBadges } from "../badges";
import { t } from "../i18n";
import { validateIdLookupInput } from "../validation";
import { candidateBackdropUrl, candidatePosterUrl, tmdbImageUrl } from "../utils/tmdb";
import {
  labelMediaItemStatus,
  labelMediaType,
  labelOperationStatus,
  labelOperationType,
  labelPlanStatus,
  labelReviewDecision,
  labelScanSessionStatus,
  statusTone,
  type BadgeTone,
} from "../labels";
import type {
  BulkReviewResult,
  MediaFile,
  MediaItem,
  OperationPlan,
  PlanApplyResult,
  PlanOperation,
  PlanValidationResult,
  RecognitionPreflightResult,
  ScanSession,
  TmdbMatchCandidate,
} from "../types";
import { defaultSelectedIds, isBulkSelectable } from "../utils/bulkSelection";
import { buildPlanSummary } from "../utils/planSummary";

type StepStatus = "pending" | "running" | "done" | "error";

const analysisSteps: { key: string; label: string }[] = [
  { key: "preflight", label: "Проверка AI" },
  { key: "discover", label: "Сканирование файлов" },
  { key: "parse", label: "Распознавание названий" },
  { key: "match", label: "Поиск в TMDB" },
  { key: "local-ai", label: "Локальная AI-модель" },
  { key: "gemini", label: "Распознавание запасной облачной моделью" },
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
        <PreflightCheckBlock title="Локальная AI-модель" check={result?.local} />
        <PreflightCheckBlock title="Облачная AI-модель (основная)" check={result?.cloud} />
        {result?.cloud_fallback ? (
          <PreflightCheckBlock title="Облачная AI-модель (запасная)" check={result.cloud_fallback} />
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
  const [selectedItemIds, setSelectedItemIds] = useState<Set<number>>(new Set());
  const [bulkResult, setBulkResult] = useState<BulkReviewResult | null>(null);
  const [validationResult, setValidationResult] = useState<PlanValidationResult | null>(null);
  const [applyResult, setApplyResult] = useState<PlanApplyResult | null>(null);
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [applyConfirmChecked, setApplyConfirmChecked] = useState(false);
  const [analysisCollapsed, setAnalysisCollapsed] = useState(false);
  const candidatesPanelRef = useRef<HTMLElement | null>(null);

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
      await runStep("match", () => matchTmdbSession(numId));
      await runStep("local-ai", () => normalizeLocalAi(numId));
      await runStep("gemini", async () => {
        await resolveWithGemini(numId);
        await matchTmdbSession(numId, true);
      });
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
    setError(null);
    try {
      const loaded = await listTmdbCandidates(itemId);
      setCandidates([...loaded].sort((a, b) => b.id - a.id));
      requestAnimationFrame(() => {
        candidatesPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Не удалось загрузить кандидатов TMDB";
      setError(msg);
      setCandidates([]);
    }
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

  return (
    <div>
      <p>
        <Link to="/">← К списку сессий</Link>
      </p>

      {error ? <div className="message error">{error}</div> : null}
      {info ? <div className="message success">{info}</div> : null}
      <div className="safety-notice">
        План — предварительный просмотр. Файлы изменятся только после явного подтверждения «Применить план».
      </div>

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
          <summary>Статус pipeline и AI preflight</summary>
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
            <button disabled={busy} onClick={() => void runAction("local-ai", () => normalizeLocalAi(numId), "Local AI normalization finished.")}>
              Local AI
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

      <section className="panel review-main-panel">
        <div className="section-heading">
          <h3>Проверка найденных фильмов</h3>
          <span className="muted">
            В план: {planExcluded.plannable} · исключено: {planExcluded.ignored} · отложено: {planExcluded.deferred}
          </span>
        </div>
        <BulkReviewToolbar
          busy={busy}
          selectedCount={selectedItemIds.size}
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

      {selectedItemId !== null ? (
        <section className="panel candidate-panel" ref={candidatesPanelRef}>
          <div className="section-heading">
            <h3>
              Кандидаты TMDB:{" "}
              {items.find((i) => i.id === selectedItemId)?.localized_title ??
                items.find((i) => i.id === selectedItemId)?.matched_title ??
                items.find((i) => i.id === selectedItemId)?.parsed_title ??
                `#${selectedItemId}`}
            </h3>
            <button type="button" onClick={() => setSelectedItemId(null)}>Закрыть</button>
          </div>
          <ManualCandidateSearch
            itemId={selectedItemId}
            busy={busy}
            onResults={setCandidates}
            onError={setError}
          />
          {candidates.length === 0 ? <p className="muted">Кандидатов пока нет. Сначала запустите поиск в TMDB.</p> : null}
          <div className="candidate-list">
            {candidates.map((candidate) => (
              <CandidateReviewCard
                key={candidate.id}
                candidate={candidate}
                busy={busy}
                onSelect={() => void selectCandidate(candidate.id)}
              />
            ))}
          </div>
        </section>
      ) : null}

      <PlanApplyPanel
        plans={plans}
        selectedPlanId={selectedPlanId ?? latestPlanId}
        operations={operations}
        items={items}
        validation={validationResult}
        applyResult={applyResult}
        busy={busy}
        planStale={planStale}
        onSelectPlan={(planId) => void showOperations(planId)}
        onValidate={() => void handleValidatePlan()}
        onApplyClick={() => {
          setApplyConfirmChecked(false);
          setShowApplyModal(true);
        }}
        onRebuildPlan={() => void runAction("rebuild-plan", () => createPlan(numId, true), "План пересобран.")}
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
    <div className={`item-list ${selectable ? "item-list-selectable" : ""}`}>
      {items.map((item) => (
        <MediaItemCard
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
        />
      ))}
    </div>
  );
}

function MediaItemCard({
  item,
  variant,
  busy,
  selectable = false,
  selected = false,
  onToggleSelect,
  onCandidates,
  onCorrection,
  onDecision,
}: {
  item: MediaItem;
  variant: "matched" | "review";
  busy: boolean;
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: (itemId: number) => void;
  onCandidates: (itemId: number) => Promise<void>;
  onCorrection: (item: MediaItem, payload: CorrectionPayload) => Promise<void>;
  onDecision: (itemId: number, payload: ReviewPayload) => Promise<void>;
}) {
  const localPoster = item.local_poster_path ?? item.sidecar_poster_path;
  const poster = item.poster_url ?? tmdbImageUrl(item.poster_path) ?? (localPoster ? `file:///${localPoster.replace(/\\/g, "/")}` : null);
  const title = item.localized_title ?? item.matched_title ?? item.parsed_title ?? item.original_title ?? `Объект #${item.id}`;
  const badges = getItemBadges(item);
  const isIgnored = item.review_decision === "ignored";
  const isDeferred = item.review_decision === "deferred";
  const isApproved = item.review_decision === "approved" || item.review_decision === "manual_override";
  return (
    <div
      className={`item-card visual-item-card ${item.reused_from_memory ? "memory-reused" : ""} ${isIgnored || isDeferred ? "review-muted" : ""}`}
    >
      <div className="visual-item-layout">
        {selectable ? (
          <label className="item-select-checkbox">
            <input
              type="checkbox"
              checked={selected}
              disabled={busy}
              onChange={() => onToggleSelect?.(item.id)}
            />
          </label>
        ) : null}
        <div className="visual-item-poster">
          {poster ? <img src={poster} alt={title} loading="lazy" /> : <div className="poster-placeholder">Нет постера</div>}
        </div>
        <div className="visual-item-content">
          <div className="section-heading">
            <div>
              <strong>{title}</strong>
              <p className="muted">
                {labelMediaType(item.media_type)}
                {item.year ? ` · ${item.year}` : ""}
                {item.season_number && item.episode_number
                  ? ` · S${String(item.season_number).padStart(2, "0")}E${String(item.episode_number).padStart(2, "0")}`
                  : ""}
              </p>
            </div>
            <div className="item-badges">
              {badges.map((badge) => (
                <Badge key={badge.key} value={badge.key} label={badge.label} tone={badge.tone} />
              ))}
            </div>
          </div>
          {variant === "review" ? <p className="muted">Файл: {item.original_title}</p> : null}
          <div className="item-meta">
            <span>TMDB ID: {fmt(item.tmdb_id)}</span>
            <span>IMDb: {fmt(item.imdb_id)}</span>
            {item.tvdb_id ? <span>TVDB: {fmt(item.tvdb_id)}</span> : null}
            <span>Уверенность: {formatPercent(item.match_confidence ?? item.ai_confidence ?? item.confidence)}</span>
          </div>
          {item.localized_overview ? <p className="item-overview">{item.localized_overview}</p> : null}
          <div className="item-review-actions">
            {isApproved ? (
              <button type="button" disabled className="btn-muted">
                Одобрено
              </button>
            ) : (
              <button
                type="button"
                disabled={busy}
                onClick={() => void onDecision(item.id, { decision: "approved", note: "Подтверждено пользователем" })}
              >
                Добавить
              </button>
            )}
            {isIgnored || isDeferred ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void onDecision(item.id, { decision: "approved", note: "Вернуть в план" })}
              >
                Вернуть в план
              </button>
            ) : (
              <>
                <button type="button" disabled={busy} onClick={() => void onDecision(item.id, { decision: "ignored", note: "Не добавлять" })}>
                  Не добавлять
                </button>
                <button type="button" disabled={busy} onClick={() => void onDecision(item.id, { decision: "deferred", note: "Отложено" })}>
                  Отложить
                </button>
              </>
            )}
            <button type="button" onClick={() => void onCandidates(item.id)}>
              Кандидаты TMDB
            </button>
          </div>
          <details className="manual-review-panel-wrap">
            <summary>Ручная проверка</summary>
            <ManualReviewPanel item={item} busy={busy} onCandidates={onCandidates} onDecision={onDecision} />
          </details>
          <details className="recognition-tech-details">
            <summary>Технические детали распознавания</summary>
            <RecognitionEvidence item={item} />
            {variant === "review" ? <CorrectionForm item={item} busy={busy} onSubmit={onCorrection} /> : null}
          </details>
          {isIgnored ? <Badge value="ignored" label="Исключено" tone="warning" /> : null}
          {isDeferred ? <Badge value="deferred" label="Отложено" tone="warning" /> : null}
          {isApproved ? <Badge value="approved" label={labelReviewDecision(item.review_decision)} tone="success" /> : null}
        </div>
      </div>
    </div>
  );
}

function CandidateReviewCard({
  candidate,
  busy,
  onSelect,
}: {
  candidate: TmdbMatchCandidate;
  busy: boolean;
  onSelect: () => void;
}) {
  const poster = candidatePosterUrl(candidate);
  const backdrop = candidateBackdropUrl(candidate);
  return (
    <div className={`candidate-card visual-candidate-card ${candidate.is_selected ? "selected" : ""}`}>
      <div className="candidate-visuals">
        {poster ? <img className="candidate-poster" src={poster} alt={candidate.title} loading="lazy" /> : <div className="poster-placeholder">Нет постера</div>}
        {backdrop ? <img className="candidate-backdrop" src={backdrop} alt="" loading="lazy" /> : null}
      </div>
      <div className="candidate-content">
        <div className="section-heading">
          <div>
            <strong>{candidate.title}</strong>
            <p className="muted">
              {fmt(candidate.original_title)} · {labelMediaType(candidate.media_type)} · {fmt(candidate.year)}
            </p>
          </div>
          {candidate.is_selected ? <Badge value="MATCHED" label="Выбранный вариант" tone="success" /> : null}
        </div>
        {candidate.overview_is_fallback ? (
          <p className="message warning">Описание на русском не найдено, показан английский вариант.</p>
        ) : null}
        <p>{candidate.overview ?? "Описание отсутствует."}</p>
        <div className="candidate-meta">
          <span>TMDB ID: {candidate.tmdb_id}</span>
          <span>IMDb: {fmt(candidate.imdb_id)}</span>
          {candidate.tvdb_id ? <span>TVDB: {candidate.tvdb_id}</span> : null}
          {candidate.wikidata_id ? <span>Wikidata: {candidate.wikidata_id}</span> : null}
          <span>Язык: {fmt(candidate.metadata_language)}</span>
          <span>Score: {candidate.score.toFixed(2)}</span>
          <span>Рейтинг: {fmt(candidate.vote_average)}</span>
          <span>Популярность: {fmt(candidate.popularity)}</span>
        </div>
        <button
          type="button"
          className="btn-primary"
          disabled={busy || candidate.is_selected || candidate.id < 0}
          onClick={onSelect}
        >
          {candidate.is_selected ? "Этот вариант выбран" : "Выбрать этот вариант"}
        </button>
      </div>
    </div>
  );
}

function AiDiagnosticMessage({
  provider,
  status,
  validJson,
  error,
}: {
  provider: "Локальная AI-модель" | "Облачная AI-модель";
  status: string | null;
  validJson: boolean | null;
  error: string | null;
}) {
  const label = formatAiStatusLabel(status, validJson, Boolean(error));
  const humanError = error ? humanizeAiError(error) : null;
  return (
    <div className="ai-diagnostic">
      <span>
        {provider}: {label}
      </span>
      {humanError ? <small className="error-text">Ошибка: {humanError}</small> : null}
      {error ? (
        <details className="technical-error">
          <summary>Технические детали</summary>
          <pre>{error}</pre>
        </details>
      ) : null}
    </div>
  );
}

function RecognitionEvidence({ item }: { item: MediaItem }) {
  return (
    <div className="recognition-evidence">
      <span>Парсер: {fmt(item.parsed_title)} {item.year ? `(${item.year})` : ""}</span>
      {item.sidecar_source_path ? <span>Источник NFO: {item.sidecar_source_path}</span> : null}
      {item.match_source ? <span>Источник совпадения: {item.match_source}</span> : null}
      <AiDiagnosticMessage
        provider="Локальная AI-модель"
        status={item.local_ai_status}
        validJson={item.local_ai_response_valid_json}
        error={item.local_ai_error}
      />
      <span>Локальная AI: {fmt(item.local_ai_duration_ms)} мс</span>
      <span>Модель: {fmt(item.local_ai_model)}</span>
      <span>Результат: {fmt(item.ai_clean_title)} {formatPercent(item.ai_confidence)}</span>
      <AiDiagnosticMessage
        provider="Облачная AI-модель"
        status={item.gemini_status}
        validJson={item.gemini_response_valid_json}
        error={item.gemini_error}
      />
      <span>Облачная AI: {fmt(item.gemini_duration_ms)} мс</span>
      <span>Модель: {fmt(item.gemini_model)}</span>
      <span>Результат: {fmt(item.gemini_clean_title)} {formatPercent(item.gemini_confidence)}</span>
      {item.tmdb_queries?.length ? <span>Запросы TMDB: {item.tmdb_queries.join(", ")}</span> : null}
      {item.ai_junk_tokens?.length ? <span>Удалённые токены: {item.ai_junk_tokens.join(", ")}</span> : null}
      {item.ai_explanation ? <span>{item.ai_explanation}</span> : null}
      {item.gemini_explanation ? <span>{item.gemini_explanation}</span> : null}
    </div>
  );
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
      <summary>Ручное исправление</summary>
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

function ManualCandidateSearch({
  itemId,
  busy,
  onResults,
  onError,
}: {
  itemId: number;
  busy: boolean;
  onResults: (candidates: TmdbMatchCandidate[]) => void;
  onError: (message: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [year, setYear] = useState("");
  const [mediaType, setMediaType] = useState("movie");
  const [tmdbId, setTmdbId] = useState("");
  const [imdbId, setImdbId] = useState("");
  const [tvdbId, setTvdbId] = useState("");

  return (
    <div className="manual-candidate-search">
      <strong>Найти другой вариант</strong>
      <div className="manual-review-grid">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Название" />
        <input value={year} onChange={(e) => setYear(e.target.value)} placeholder="Год" inputMode="numeric" />
        <select value={mediaType} onChange={(e) => setMediaType(e.target.value)}>
          <option value="movie">Фильм</option>
          <option value="tv">Сериал</option>
        </select>
        <input value={tmdbId} onChange={(e) => setTmdbId(e.target.value)} placeholder="TMDB ID" inputMode="numeric" />
        <input value={imdbId} onChange={(e) => setImdbId(e.target.value)} placeholder="IMDb ID" />
        <input value={tvdbId} onChange={(e) => setTvdbId(e.target.value)} placeholder="TVDB ID" inputMode="numeric" />
      </div>
      <div className="manual-review-actions">
        <button
          type="button"
          disabled={busy || !title.trim()}
          onClick={() =>
            void (async () => {
              try {
                onResults(
                  await manualTmdbSearch(itemId, {
                    query: title.trim(),
                    year: year === "" ? null : Number(year),
                    media_type: mediaType,
                  }),
                );
              } catch (err) {
                onError(err instanceof ApiError ? err.message : "Поиск не удался");
              }
            })()
          }
        >
          Искать
        </button>
        <button
          type="button"
          disabled={busy || (!tmdbId && !imdbId && !tvdbId)}
          onClick={() =>
            void (async () => {
              try {
                const candidate = await manualTmdbLookup(itemId, {
                  tmdb_id: tmdbId ? Number(tmdbId) : null,
                  imdb_id: imdbId || null,
                  tvdb_id: tvdbId ? Number(tvdbId) : null,
                  media_type: mediaType,
                });
                onResults([candidate]);
              } catch (err) {
                onError(err instanceof ApiError ? err.message : "Загрузка по ID не удалась");
              }
            })()
          }
        >
          Загрузить по ID
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
