import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
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
  matchTmdbSession,
  normalizeLocalAi,
  parseSession,
  recognitionPreflight,
  resolveWithGemini,
  rollbackPlan,
  selectTmdbCandidate,
  validatePlan,
} from "../api";
import { ApplyConfirmModal } from "../components/plan/ApplyConfirmModal";
import { PlanApplyPanel } from "../components/plan/PlanApplyPanel";
import { BulkReviewToolbar } from "../components/review/BulkReviewToolbar";
import { CandidatesModal } from "../components/review/CandidatesModal";
import { PipelinePanel } from "../components/session/PipelinePanel";
import { ItemList, TechnicalTables, TvReviewSection } from "../components/session/ReviewSections";
import { SessionHeader } from "../components/session/SessionHeader";
import { tvShowReviewState } from "../components/session/tvReviewState";
import { getPreflightShortMessage } from "../aiLabels";
import { t } from "../i18n";
import { useSessionData } from "../hooks/useSessionData";
import { useSessionPipeline, type StepStatus } from "../hooks/useSessionPipeline";
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
import { defaultSelectedIds } from "../utils/bulkSelection";
import { buildPlanSummary, hasTvOperations } from "../utils/planSummary";
import { loadSection } from "../utils/sectionLoad";

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
  const { stepStatus, setStepStatus } = useSessionPipeline();
  const { loading, setLoading, error, setError } = useSessionData();
  const [actionLoading, setActionLoading] = useState<string | null>(null);
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
  const [showRollbackModal, setShowRollbackModal] = useState(false);
  const [rollbackConfirmChecked, setRollbackConfirmChecked] = useState(false);
  const [analysisCollapsed, setAnalysisCollapsed] = useState(false);
  const [candidatesModalOpen, setCandidatesModalOpen] = useState(false);

  const latestPlanId = plans[0]?.id ?? null;
  const activePlanHasTvOperations = hasTvOperations(operations);

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
  }, [numId, setError]);

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
  }, [numId, selectedItemId, loadSessionHeader, loadReview, loadPlan, setError, setLoading]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const isTvOnlySession = classification?.content_type === "tv";
  const movieFlowItems = useMemo(() => (isTvOnlySession ? [] : items), [isTvOnlySession, items]);
  const tvSeasonCount = tvShows.reduce((total, show) => total + show.seasons.length, 0);
  const tvEpisodeCount = tvShows.reduce(
    (total, show) => total + show.seasons.reduce((seasonTotal, season) => seasonTotal + season.episodes.length, 0),
    0,
  );

  const summary = useMemo(() => {
    const video = files.filter((f) => f.is_video).length;
    const subtitles = files.filter((f) => f.is_subtitle).length;
    if (isTvOnlySession) {
      const ignored = tvShows.filter((show) => show.review_decision === "ignored").length;
      const deferred = tvShows.filter((show) => show.review_decision === "deferred").length;
      const review = tvShows.filter((show) => tvShowReviewState(show) === "needs_review").length;
      return {
        totalFiles: files.length,
        video,
        subtitles,
        items: tvShows.length,
        matched: tvShows.length,
        review,
        reused: 0,
        fresh: tvShows.length,
        ignored,
        deferred,
        operations: operations.length,
        conflicts: buildPlanSummary(operations, movieFlowItems, validationResult?.conflict_count ?? 0).conflicts,
      };
    }
    const matched = movieFlowItems.filter((item) => item.status === "MATCHED").length;
    const review = movieFlowItems.filter((item) => item.status === "NEEDS_REVIEW" || item.media_type === "UNKNOWN").length;
    const reused = movieFlowItems.filter((item) => item.reused_from_memory).length;
    const fresh = movieFlowItems.filter((item) => !item.reused_from_memory).length;
    const ignored = movieFlowItems.filter((item) => item.review_decision === "ignored").length;
    const deferred = movieFlowItems.filter((item) => item.review_decision === "deferred").length;
    const planSummary = buildPlanSummary(operations, movieFlowItems, validationResult?.conflict_count ?? 0);
    return {
      totalFiles: files.length,
      video,
      subtitles,
      items: movieFlowItems.length,
      matched,
      review,
      reused,
      fresh,
      ignored,
      deferred,
      operations: operations.length,
      conflicts: planSummary.conflicts,
    };
  }, [files, isTvOnlySession, movieFlowItems, operations, validationResult, tvShows]);

  const planExcluded = useMemo(() => {
    const ignored = movieFlowItems.filter((item) => item.review_decision === "ignored").length;
    const deferred = movieFlowItems.filter((item) => item.review_decision === "deferred").length;
    const plannable = movieFlowItems.filter(
      (item) => item.status === "MATCHED" && !["ignored", "deferred"].includes(item.review_decision),
    ).length;
    return { ignored, deferred, plannable };
  }, [movieFlowItems]);

  const matchedItems = movieFlowItems.filter((item) => item.status === "MATCHED");
  const reviewItems = movieFlowItems.filter((item) => item.status === "NEEDS_REVIEW" || item.media_type === "UNKNOWN");
  const unmatchedItems = movieFlowItems.filter((item) => item.status === "UNMATCHED");
  const otherItems = movieFlowItems.filter(
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

    const runStep = async <T,>(key: string, action: () => Promise<T>) => {
      nextStatus[key] = "running";
      setStepStatus({ ...nextStatus });
      const result = await action();
      nextStatus[key] = "done";
      setStepStatus({ ...nextStatus });
      await loadAll();
      return result;
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
      const classificationResult = await runStep("classification", () => classifySession(numId));
      const contentType = classificationResult.content_type;
      if (classificationResult.needs_user_decision) {
        throw new ApiError(400, "Тип содержимого не определён уверенно. Выберите режим обработки вручную.");
      }

      if (contentType === "movies" || contentType === "mixed") {
        await runStep("parse", () => parseSession(numId));
        await runStep("local-ai", () => normalizeLocalAi(numId));
        await runStep("match", () => matchTmdbSession(numId));
        await runStep("gemini", async () => {
          await resolveWithGemini(numId);
          await matchTmdbSession(numId, true);
        });
        await runStep("plan", () => createPlan(numId, true));
      } else {
        nextStatus.parse = "done";
        nextStatus["local-ai"] = "done";
        nextStatus.match = "done";
        nextStatus.gemini = "done";
        nextStatus.plan = "done";
        setStepStatus({ ...nextStatus });
      }

      if (contentType === "tv" || contentType === "mixed") {
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
      } else {
        nextStatus.tv = "done";
        nextStatus["tv-plan"] = "done";
        setStepStatus({ ...nextStatus });
      }
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
    ) || tvShows.some((show) => new Date(show.updated_at).getTime() > planTime);
  }, [activePlan, items, tvShows]);

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
      setInfo(`Запущено применение ${result.total_operations} операций.`);
      setOperations(await listPlanOperations(planId));
      setPlans(await listPlans(numId));
      await loadApplyRuns(planId);
    }, "План запущен.");
  }

  async function handleRollbackPlan() {
    const planId = selectedPlanId ?? latestPlanId;
    if (planId === null) return;
    setShowRollbackModal(false);
    await runAction("rollback-plan", async () => {
      const result = await rollbackPlan(planId, { confirm: true });
      setApplyResult(null);
      setInfo(`Откачено ${result.rolled_back_operations} из ${result.total_operations} операций.`);
      setOperations(await listPlanOperations(planId));
      setPlans(await listPlans(numId));
      await loadApplyRuns(planId);
    }, "План откачен.");
  }

  function toggleItemSelection(itemId: number) {
    setSelectedItemIds((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  }

  const busy = actionLoading !== null;
  const nestingWarning = session ? detectPathNestingWarning(session.source_path, session.target_path) : null;

  useEffect(() => {
    const planId = selectedPlanId ?? latestPlanId;
    if (planId === null) return;
    const activePlan = plans.find((plan) => plan.id === planId) ?? null;
    const latestRun = applyRuns[0] ?? null;
    const applying = activePlan?.status === "APPLYING" || latestRun?.status === "running";
    if (!applying) return;

    const intervalId = window.setInterval(() => {
      void (async () => {
        await loadApplyRuns(planId);
        const nextPlans = await listPlans(numId);
        setPlans(nextPlans);
        const nextPlan = nextPlans.find((plan) => plan.id === planId) ?? null;
        if (nextPlan?.status !== "APPLYING") {
          setOperations(await listPlanOperations(planId));
        }
      })();
    }, 1500);

    return () => window.clearInterval(intervalId);
  }, [applyRuns, latestPlanId, loadApplyRuns, numId, plans, selectedPlanId]);

  if (!Number.isFinite(numId)) {
    return <div className="message error">Неверный ID сессии.</div>;
  }

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

      <SessionHeader
        session={session}
        sessionId={numId}
        busy={busy}
        actionLoading={actionLoading}
        loading={loading}
        sessionError={sessionError && !error ? sessionError : null}
        nestingWarning={nestingWarning}
        onDelete={() => void handleDeleteSession()}
      />
      <PipelinePanel
        busy={busy}
        actionLoading={actionLoading}
        analysisCollapsed={analysisCollapsed}
        preflightResult={preflightResult}
        stepStatus={stepStatus}
        onRunFullAnalysis={() => void runFullAnalysis()}
        onDiscover={() => void runAction("discover", () => discoverSession(numId), "Сканирование завершено.")}
        onParse={() => void runAction("parse", () => parseSession(numId), "Распознавание завершено.")}
        onLocalAi={() => void runAction("local-ai", () => normalizeLocalAi(numId), "Локальная AI-модель завершила нормализацию.")}
        onMatch={() => void runAction("match", () => matchTmdbSession(numId), "Поиск TMDB завершён.")}
        onGemini={() => void runAction("gemini", async () => {
          await resolveWithGemini(numId);
          await matchTmdbSession(numId, true);
        }, "Запасная облачная модель и повторный поиск в TMDB завершены.")}
        onTv={() => void runAction("tv", () => analyzeTvSession(numId, true), "Распознавание сериалов завершено.")}
        onTvPlan={() => void runAction("tv-plan", () => createTvPlan(numId, true), "План сериалов построен.")}
        onPlan={() => void runAction("plan", () => createPlan(numId), "План построен.")}
      />
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
          {classification.content_type === "tv" || classification.content_type === "mixed" ? (
            <p className="muted">
              Сериалов: {tvShows.length} · Сезонов: {tvSeasonCount} · Эпизодов: {tvEpisodeCount}
            </p>
          ) : null}
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

      {isTvOnlySession ? (
        <p className="muted compact-section-row">Фильмы: не обнаружены</p>
      ) : (
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
      )}

      <TvReviewSection
        shows={tvShows}
        busy={busy}
        planStale={planStale}
        onDecision={async (showId, decision) => {
          const messages: Record<string, string> = {
            approved: "Сериал включён в план. Пересоберите план сериалов.",
            ignored: "Сериал исключён из плана. Пересоберите план сериалов, чтобы обновить операции.",
            deferred: "Сериал отложен и не попадёт в текущий план.",
            manual_override: "Совпадение изменено. Пересоберите план сериалов.",
          };
          await runAction(`tv-${decision}-${showId}`, async () => {
            await applyTvReviewDecision(showId, { decision });
          }, messages[decision] ?? "Решение по сериалу сохранено.");
        }}
        onShowUpdated={async (message) => {
          setInfo(message);
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
        onRollbackClick={() => {
          setRollbackConfirmChecked(false);
          setShowRollbackModal(true);
        }}
      />

      <ApplyConfirmModal
        open={showApplyModal}
        busy={busy}
        checked={applyConfirmChecked}
        variant={activePlanHasTvOperations ? "tv" : "movie"}
        onCheckedChange={setApplyConfirmChecked}
        onConfirm={() => void handleApplyPlan()}
        onCancel={() => setShowApplyModal(false)}
      />

      <ApplyConfirmModal
        open={showRollbackModal}
        busy={busy}
        checked={rollbackConfirmChecked}
        variant="rollback"
        onCheckedChange={setRollbackConfirmChecked}
        onConfirm={() => void handleRollbackPlan()}
        onCancel={() => setShowRollbackModal(false)}
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





