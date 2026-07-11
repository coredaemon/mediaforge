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
    return "РџР°РїРєР° РјРµРґРёР°С‚РµРєРё РЅР°С…РѕРґРёС‚СЃСЏ РІРЅСѓС‚СЂРё РїР°РїРєРё СЃ С„Р°Р№Р»Р°РјРё. Р”Р»СЏ РЅРѕРІС‹С… СЃРµСЃСЃРёР№ С‚Р°РєРѕР№ РІР°СЂРёР°РЅС‚ Р±СѓРґРµС‚ Р·Р°РїСЂРµС‰С‘РЅ.";
  }
  if (s.startsWith(t + "/")) {
    return "РџР°РїРєР° СЃ С„Р°Р№Р»Р°РјРё РЅР°С…РѕРґРёС‚СЃСЏ РІРЅСѓС‚СЂРё РїР°РїРєРё РјРµРґРёР°С‚РµРєРё. Р”Р»СЏ РЅРѕРІС‹С… СЃРµСЃСЃРёР№ С‚Р°РєРѕР№ РІР°СЂРёР°РЅС‚ Р±СѓРґРµС‚ Р·Р°РїСЂРµС‰С‘РЅ.";
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
  if (value === "movies") return "С„РёР»СЊРјС‹";
  if (value === "tv") return "СЃРµСЂРёР°Р»С‹";
  if (value === "mixed") return "СЃРјРµС€Р°РЅРЅР°СЏ РїР°РїРєР°";
  return "РЅРµРёР·РІРµСЃС‚РЅРѕ";
}

function formatPreflightError(result: RecognitionPreflightResult): string {
  if (result.message) {
    return result.message;
  }
  if (!result.local.ok) {
    return getPreflightShortMessage(result.local) ?? "Р›РѕРєР°Р»СЊРЅР°СЏ AI-РјРѕРґРµР»СЊ РЅРµ РѕС‚РІРµС‡Р°РµС‚. РџСЂРѕРІРµСЂСЊС‚Рµ Ollama Рё РЅР°СЃС‚СЂРѕР№РєРё РјРѕРґРµР»Рё.";
  }
  if (!result.cloud.ok && !result.cloud_fallback?.ok) {
    return getPreflightShortMessage(result.cloud) ?? "РћР±Р»Р°С‡РЅС‹Рµ РјРѕРґРµР»Рё РЅРµРґРѕСЃС‚СѓРїРЅС‹. РџСЂРѕРІРµСЂСЊС‚Рµ РєР»СЋС‡ Рё РЅР°СЃС‚СЂРѕР№РєРё.";
  }
  return "РџСЂРѕРІРµСЂРєР° AI РЅРµ РїСЂРѕР№РґРµРЅР°.";
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
      "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ Р¶СѓСЂРЅР°Р» РїСЂРёРјРµРЅРµРЅРёСЏ",
    );
  }, []);

  const loadPlan = useCallback(async () => {
    const loadedPlans = await loadSection(
      () => listPlans(numId),
      setPlans,
      setPlanError,
      "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РїР»Р°РЅ РѕРїРµСЂР°С†РёР№",
    );
    const planId = selectedPlanId ?? loadedPlans?.[0]?.id ?? null;
    if (planId !== null) {
      setSelectedPlanId(planId);
      const ops = await loadSection(
        () => listPlanOperations(planId),
        setOperations,
        setPlanError,
        "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РѕРїРµСЂР°С†РёРё РїР»Р°РЅР°",
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
      "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЃРїРёСЃРѕРє С„Р°Р№Р»РѕРІ",
    );
    await loadSection(
      () => classifySession(numId),
      setClassification,
      setReviewError,
      "РќРµ СѓРґР°Р»РѕСЃСЊ РєР»Р°СЃСЃРёС„РёС†РёСЂРѕРІР°С‚СЊ СЃРѕРґРµСЂР¶РёРјРѕРµ РїР°РїРєРё",
    );
    const loadedItems = await loadSection(
      () => listItems(numId),
      setItems,
      setReviewError,
      "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЃРїРёСЃРѕРє С„РёР»СЊРјРѕРІ",
    );
    const loadedTvShows = await loadSection(
      () => listTvShows(numId),
      setTvShows,
      setReviewError,
      "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЃРїРёСЃРѕРє СЃРµСЂРёР°Р»РѕРІ",
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
      const message = err instanceof ApiError ? err.message : "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ СЃРµСЃСЃРёСЋ";
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
      const raw = err instanceof ApiError ? err.message : `РћС€РёР±РєР°: ${key}`;
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
        throw new ApiError(400, "РўРёРї СЃРѕРґРµСЂР¶РёРјРѕРіРѕ РЅРµ РѕРїСЂРµРґРµР»С‘РЅ СѓРІРµСЂРµРЅРЅРѕ. Р’С‹Р±РµСЂРёС‚Рµ СЂРµР¶РёРј РѕР±СЂР°Р±РѕС‚РєРё РІСЂСѓС‡РЅСѓСЋ.");
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
      setInfo("РђРЅР°Р»РёР· Р·Р°РІРµСЂС€С‘РЅ. РџСЂРѕРІРµСЂСЊС‚Рµ РЅР°Р№РґРµРЅРЅС‹Рµ РѕР±СЉРµРєС‚С‹ Рё Р±РµР·РѕРїР°СЃРЅС‹Р№ РїР»Р°РЅ.");
    } catch (err) {
      const failed = Object.entries(nextStatus).find(([, status]) => status === "running")?.[0];
      if (failed) nextStatus[failed] = "error";
      setStepStatus({ ...nextStatus });
      const raw = err instanceof ApiError ? err.message : "РђРЅР°Р»РёР· РѕСЃС‚Р°РЅРѕРІР»РµРЅ РёР·-Р·Р° РѕС€РёР±РєРё.";
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
      const msg = err instanceof ApiError ? err.message : "РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ РєР°РЅРґРёРґР°С‚РѕРІ TMDB";
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
      "РљР°РЅРґРёРґР°С‚ РІС‹Р±СЂР°РЅ. РўРµРїРµСЂСЊ РјРѕР¶РЅРѕ РїРµСЂРµСЃРѕР±СЂР°С‚СЊ РїР»Р°РЅ.",
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
      setInfo(`РћРґРѕР±СЂРµРЅРѕ: ${result.approved_count} В· РїСЂРѕРїСѓС‰РµРЅРѕ: ${result.skipped_count}`);
    }, "РњР°СЃСЃРѕРІРѕРµ РѕРґРѕР±СЂРµРЅРёРµ Р·Р°РІРµСЂС€РµРЅРѕ.");
  }

  async function handleBulkApproveSelected() {
    const ids = [...selectedItemIds];
    if (ids.length === 0) return;
    await runAction("bulk-approve-selected", async () => {
      const result = await approveAllMatched(numId, { scope: "selected", item_ids: ids });
      setBulkResult(result);
      setInfo(`РћРґРѕР±СЂРµРЅРѕ: ${result.approved_count} В· РїСЂРѕРїСѓС‰РµРЅРѕ: ${result.skipped_count}`);
    }, "Р’С‹Р±СЂР°РЅРЅС‹Рµ РѕР±СЉРµРєС‚С‹ РѕРґРѕР±СЂРµРЅС‹.");
  }

  async function handleBulkDecision(decision: "ignored" | "deferred") {
    const ids = [...selectedItemIds];
    if (ids.length === 0) return;
    const note = decision === "ignored" ? "РќРµ РґРѕР±Р°РІР»СЏС‚СЊ" : "РћС‚Р»РѕР¶РµРЅРѕ";
    await runAction(`bulk-${decision}`, async () => {
      const result = await bulkReviewDecision(numId, { item_ids: ids, decision, note });
      setBulkResult(result);
    }, decision === "ignored" ? "Р’С‹Р±СЂР°РЅРЅС‹Рµ РѕР±СЉРµРєС‚С‹ РёСЃРєР»СЋС‡РµРЅС‹." : "Р’С‹Р±СЂР°РЅРЅС‹Рµ РѕР±СЉРµРєС‚С‹ РѕС‚Р»РѕР¶РµРЅС‹.");
  }

  async function handleValidatePlan() {
    const planId = selectedPlanId ?? latestPlanId;
    if (planId === null) return;
    await runAction("validate-plan", async () => {
      const result = await validatePlan(planId);
      setValidationResult(result);
      setOperations(result.operations);
      setInfo(
        `РџСЂРѕРІРµСЂРєР°: OK ${result.ok_count}, РїСЂРµРґСѓРїСЂРµР¶РґРµРЅРёСЏ ${result.warning_count}, РєРѕРЅС„Р»РёРєС‚С‹ ${result.conflict_count}`,
      );
    }, "РџР»Р°РЅ РїСЂРѕРІРµСЂРµРЅ.");
  }

  async function handleApplyPlan() {
    const planId = selectedPlanId ?? latestPlanId;
    if (planId === null) return;
    setShowApplyModal(false);
    await runAction("apply-plan", async () => {
      const result = await applyPlan(planId, { confirm: true });
      setApplyResult(result);
      setInfo(`Р—Р°РїСѓС‰РµРЅРѕ РїСЂРёРјРµРЅРµРЅРёРµ ${result.total_operations} РѕРїРµСЂР°С†РёР№.`);
      setOperations(await listPlanOperations(planId));
      setPlans(await listPlans(numId));
      await loadApplyRuns(planId);
    }, "РџР»Р°РЅ Р·Р°РїСѓС‰РµРЅ.");
  }

  async function handleRollbackPlan() {
    const planId = selectedPlanId ?? latestPlanId;
    if (planId === null) return;
    setShowRollbackModal(false);
    await runAction("rollback-plan", async () => {
      const result = await rollbackPlan(planId, { confirm: true });
      setApplyResult(null);
      setInfo(`РћС‚РєР°С‡РµРЅРѕ ${result.rolled_back_operations} РёР· ${result.total_operations} РѕРїРµСЂР°С†РёР№.`);
      setOperations(await listPlanOperations(planId));
      setPlans(await listPlans(numId));
      await loadApplyRuns(planId);
    }, "РџР»Р°РЅ РѕС‚РєР°С‡РµРЅ.");
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
    return <div className="message error">РќРµРІРµСЂРЅС‹Р№ ID СЃРµСЃСЃРёРё.</div>;
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
        РџР»Р°РЅ вЂ” РїСЂРµРґРІР°СЂРёС‚РµР»СЊРЅС‹Р№ РїСЂРѕСЃРјРѕС‚СЂ. Р¤Р°Р№Р»С‹ РёР·РјРµРЅСЏС‚СЃСЏ С‚РѕР»СЊРєРѕ РїРѕСЃР»Рµ СЏРІРЅРѕРіРѕ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ В«РџСЂРёРјРµРЅРёС‚СЊ РїР»Р°РЅВ».
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
        <SummaryCard label="Р’СЃРµРіРѕ С„Р°Р№Р»РѕРІ" value={summary.totalFiles} />
        <SummaryCard label="Р’РёРґРµРѕ" value={summary.video} />
        <SummaryCard label="РќРѕРІС‹С…" value={summary.fresh} />
        <SummaryCard label="РЈР¶Рµ РѕР±СЂР°Р±РѕС‚Р°РЅРѕ" value={summary.reused} />
        <SummaryCard label="РќР°Р№РґРµРЅРѕ" value={summary.matched} />
        <SummaryCard label="РўСЂРµР±СѓСЋС‚ РїСЂРѕРІРµСЂРєРё" value={summary.review} />
        <SummaryCard label="РСЃРєР»СЋС‡РµРЅРѕ" value={summary.ignored} />
        <SummaryCard label="РћС‚Р»РѕР¶РµРЅРѕ" value={summary.deferred} />
        <SummaryCard label="РћРїРµСЂР°С†РёР№ РІ РїР»Р°РЅРµ" value={summary.operations} />
        <SummaryCard label="РљРѕРЅС„Р»РёРєС‚РѕРІ" value={summary.conflicts} />
      </section>

      {classification ? (
        <section className="panel compact-review-section">
          <div className="section-heading">
            <h3>РўРёРї СЃРѕРґРµСЂР¶РёРјРѕРіРѕ: {labelContentType(classification.content_type)}</h3>
            <span className="muted">СѓРІРµСЂРµРЅРЅРѕСЃС‚СЊ {Math.round(classification.confidence * 100)}%</span>
          </div>
          <p className="muted">{classification.reason}</p>
          {classification.content_type === "tv" || classification.content_type === "mixed" ? (
            <p className="muted">
              РЎРµСЂРёР°Р»РѕРІ: {tvShows.length} В· РЎРµР·РѕРЅРѕРІ: {tvSeasonCount} В· Р­РїРёР·РѕРґРѕРІ: {tvEpisodeCount}
            </p>
          ) : null}
          <p className="muted">
            Р’РёРґРµРѕ: {classification.video_files} В· Р’Р»РѕР¶РµРЅРЅС‹С… РїР°РїРѕРє: {classification.nested_folder_count} В· TV-РїСЂРёР·РЅР°РєРѕРІ: {classification.tv_like_files} В· Р¤РёР»СЊРј-РїСЂРёР·РЅР°РєРѕРІ: {classification.movie_like_files}
          </p>
          {classification.known_extensions.length > 0 ? (
            <p className="muted">
              Р’РёРґРµРѕ-СЂР°СЃС€РёСЂРµРЅРёСЏ: {classification.known_extensions.map((item) => `${item.extension} (${item.count})`).join(", ")}
            </p>
          ) : null}
          {classification.ignored_extensions.length > 0 ? (
            <p className="muted">
              РРіРЅРѕСЂРёСЂСѓСЋС‚СЃСЏ: {classification.ignored_extensions.map((item) => `${item.extension} (${item.count})`).join(", ")}
            </p>
          ) : null}
          {classification.warnings.map((warning) => (
            <div className="message warning" key={warning}>{warning}</div>
          ))}
          {classification.needs_user_decision ? (
            <div className="manual-review-actions">
              <button type="button" disabled={busy} onClick={() => void runAction("parse", () => parseSession(numId), "РџР°РїРєР° Р±СѓРґРµС‚ РѕР±СЂР°Р±РѕС‚Р°РЅР° РєР°Рє С„РёР»СЊРјС‹.")}>Р¤РёР»СЊРјС‹</button>
              <button type="button" disabled={busy} onClick={() => void runAction("tv", () => analyzeTvSession(numId, true), "РџР°РїРєР° Р±СѓРґРµС‚ РѕР±СЂР°Р±РѕС‚Р°РЅР° РєР°Рє СЃРµСЂРёР°Р»С‹.")}>РЎРµСЂРёР°Р»С‹</button>
              <button type="button" disabled={busy} onClick={() => void runAction("mixed", async () => {
                await parseSession(numId);
                await analyzeTvSession(numId, true);
              }, "РџР°РїРєР° Р±СѓРґРµС‚ РѕР±СЂР°Р±РѕС‚Р°РЅР° РєР°Рє СЃРјРµС€Р°РЅРЅР°СЏ.")}>РЎРјРµС€Р°РЅРЅР°СЏ РїР°РїРєР°</button>
            </div>
          ) : null}
        </section>
      ) : null}

      {isTvOnlySession ? (
        <p className="muted compact-section-row">Р¤РёР»СЊРјС‹: РЅРµ РѕР±РЅР°СЂСѓР¶РµРЅС‹</p>
      ) : (
      <section className="panel review-main-panel">
        <div className="section-heading">
          <h3>РџСЂРѕРІРµСЂРєР° РЅР°Р№РґРµРЅРЅС‹С… С„РёР»СЊРјРѕРІ</h3>
          <span className="muted">
            Р’ РїР»Р°РЅ: {planExcluded.plannable} В· РёСЃРєР»СЋС‡РµРЅРѕ: {planExcluded.ignored} В· РѕС‚Р»РѕР¶РµРЅРѕ: {planExcluded.deferred}
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
          onRebuildPlan={() => void runAction("rebuild-plan", () => createPlan(numId, true), "РџР»Р°РЅ РїРµСЂРµСЃРѕР±СЂР°РЅ.")}
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
            approved: "РЎРµСЂРёР°Р» РІРєР»СЋС‡С‘РЅ РІ РїР»Р°РЅ. РџРµСЂРµСЃРѕР±РµСЂРёС‚Рµ РїР»Р°РЅ СЃРµСЂРёР°Р»РѕРІ.",
            ignored: "РЎРµСЂРёР°Р» РёСЃРєР»СЋС‡С‘РЅ РёР· РїР»Р°РЅР°. РџРµСЂРµСЃРѕР±РµСЂРёС‚Рµ РїР»Р°РЅ СЃРµСЂРёР°Р»РѕРІ, С‡С‚РѕР±С‹ РѕР±РЅРѕРІРёС‚СЊ РѕРїРµСЂР°С†РёРё.",
            deferred: "РЎРµСЂРёР°Р» РѕС‚Р»РѕР¶РµРЅ Рё РЅРµ РїРѕРїР°РґС‘С‚ РІ С‚РµРєСѓС‰РёР№ РїР»Р°РЅ.",
            manual_override: "РЎРѕРІРїР°РґРµРЅРёРµ РёР·РјРµРЅРµРЅРѕ. РџРµСЂРµСЃРѕР±РµСЂРёС‚Рµ РїР»Р°РЅ СЃРµСЂРёР°Р»РѕРІ.",
          };
          await runAction(`tv-${decision}-${showId}`, async () => {
            await applyTvReviewDecision(showId, { decision });
          }, messages[decision] ?? "Р РµС€РµРЅРёРµ РїРѕ СЃРµСЂРёР°Р»Сѓ СЃРѕС…СЂР°РЅРµРЅРѕ.");
        }}
        onShowUpdated={async (message) => {
          setInfo(message);
          await loadAll();
        }}
        onRebuildPlan={() => void runAction("tv-plan", () => createTvPlan(numId, true), "РџР»Р°РЅ СЃРµСЂРёР°Р»РѕРІ РїРµСЂРµСЃРѕР±СЂР°РЅ.")}
      />

      {reviewItems.length > 0 ? (
        <section className="panel compact-review-section">
          <div className="section-heading">
            <h3>РўСЂРµР±СѓСЋС‚ РїСЂРѕРІРµСЂРєРё</h3>
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
        <p className="muted compact-section-row">РўСЂРµР±СѓСЋС‚ РїСЂРѕРІРµСЂРєРё: 0</p>
      )}

      {unmatchedItems.length > 0 ? (
        <section className="panel compact-review-section">
          <div className="section-heading">
            <h3>РќРµ РЅР°Р№РґРµРЅРѕ</h3>
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
        <p className="muted compact-section-row">РќРµ РЅР°Р№РґРµРЅРѕ: 0</p>
      )}

      {otherItems.length > 0 ? (
        <section className="panel">
          <h3>Р”СЂСѓРіРёРµ РѕР±СЉРµРєС‚С‹</h3>
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
        <summary>РўРµС…РЅРёС‡РµСЃРєРёРµ РґРµС‚Р°Р»Рё</summary>
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





