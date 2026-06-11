import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  applyReviewDecision,
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
} from "../api";
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
    return {
      totalFiles: files.length,
      video,
      subtitles,
      items: items.length,
      matched,
      review,
      reused,
      fresh,
      operations: operations.length,
    };
  }, [files, items, operations]);

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
            }, "Запасная облачная модель и повторный поиск в TMDB завершены.")}>
              Запасная модель + TMDB
            </button>
            <button disabled={busy} onClick={() => void runAction("plan", () => createPlan(numId), "План построен.")}>
              Построить план
            </button>
          </div>
        </details>
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>Решение по найденным объектам</h3>
          <span className="muted">
            В план: {planExcluded.plannable} · исключено: {planExcluded.ignored} · отложено: {planExcluded.deferred}
          </span>
        </div>
        <ReviewDecisionsList
          items={items}
          busy={busy}
          onDecision={async (itemId, payload) => {
            await applyReviewDecision(itemId, payload);
            await loadAll();
          }}
          onRebuildPlan={() => runAction("rebuild-plan", () => createPlan(numId, true), "План пересобран.")}
        />
      </section>

      <section className="summary-dashboard">
        <SummaryCard label="Всего файлов" value={summary.totalFiles} />
        <SummaryCard label="Видео" value={summary.video} />
        <SummaryCard label="Субтитры" value={summary.subtitles} />
        <SummaryCard label="Распознано объектов" value={summary.items} />
        <SummaryCard label="Новых файлов" value={summary.fresh} />
        <SummaryCard label="Уже обработано ранее" value={summary.reused} />
        <SummaryCard label="Найдено в TMDB" value={summary.matched} />
        <SummaryCard label="Требуют проверки" value={summary.review} />
        <SummaryCard label="Операций в плане" value={summary.operations} />
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>Найдено в TMDB</h3>
          <span className="muted">{matchedItems.length}</span>
        </div>
        <ItemList variant="matched" items={matchedItems} busy={busy} onCandidates={showCandidates} onDecision={async (itemId, payload) => {
          await applyReviewDecision(itemId, payload);
          await loadAll();
        }} onCorrection={async (item, payload) => {
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
        <ItemList variant="review" items={reviewItems} busy={busy} onCandidates={showCandidates} onDecision={async (itemId, payload) => {
          await applyReviewDecision(itemId, payload);
          await loadAll();
        }} onCorrection={async (item, payload) => {
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
        <ItemList variant="review" items={unmatchedItems} busy={busy} onCandidates={showCandidates} onDecision={async (itemId, payload) => {
          await applyReviewDecision(itemId, payload);
          await loadAll();
        }} onCorrection={async (item, payload) => {
          await createRecognitionCorrection(item.id, payload);
          await matchTmdbSession(numId, true);
          await loadAll();
        }} />
      </section>

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

      <section className="panel">
        <div className="section-heading">
          <div>
            <h3>План операций</h3>
            <p className="muted">Это только план. Файлы пока не изменяются.</p>
            {planExcluded.ignored + planExcluded.deferred > 0 ? (
              <p className="message warning">
                {planExcluded.ignored + planExcluded.deferred} объект(ов) исключено из плана
                ({planExcluded.ignored} не добавлять, {planExcluded.deferred} отложено).
              </p>
            ) : null}
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
  onCandidates,
  onCorrection,
  onDecision,
}: {
  items: MediaItem[];
  variant: "matched" | "review";
  busy: boolean;
  onCandidates: (itemId: number) => Promise<void>;
  onCorrection: (item: MediaItem, payload: CorrectionPayload) => Promise<void>;
  onDecision: (itemId: number, payload: ReviewPayload) => Promise<void>;
}) {
  if (items.length === 0) {
    return <p className="muted">Нет объектов в этом разделе.</p>;
  }
  return (
    <div className="item-list">
      {items.map((item) => (
        <MediaItemCard
          key={item.id}
          item={item}
          variant={variant}
          busy={busy}
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
  onCandidates,
  onCorrection,
  onDecision,
}: {
  item: MediaItem;
  variant: "matched" | "review";
  busy: boolean;
  onCandidates: (itemId: number) => Promise<void>;
  onCorrection: (item: MediaItem, payload: CorrectionPayload) => Promise<void>;
  onDecision: (itemId: number, payload: ReviewPayload) => Promise<void>;
}) {
  const localPoster = item.local_poster_path ?? item.sidecar_poster_path;
  const poster = item.poster_url ?? tmdbImageUrl(item.poster_path) ?? (localPoster ? `file:///${localPoster.replace(/\\/g, "/")}` : null);
  const title = item.localized_title ?? item.matched_title ?? item.parsed_title ?? item.original_title ?? `Объект #${item.id}`;
  const badges = getItemBadges(item);
  return (
    <div className={`item-card visual-item-card ${item.reused_from_memory ? "memory-reused" : ""}`}>
      <div className="visual-item-layout">
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
          <details className="recognition-tech-details">
            <summary>Технические детали распознавания</summary>
            <RecognitionEvidence item={item} />
            {variant === "review" ? <CorrectionForm item={item} busy={busy} onSubmit={onCorrection} /> : null}
          </details>
          <ManualReviewPanel item={item} busy={busy} onCandidates={onCandidates} onDecision={onDecision} />
          <div className="item-actions">
            <button type="button" onClick={() => void onCandidates(item.id)}>
              Кандидаты TMDB
            </button>
          </div>
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
    <details className="manual-review-panel" open={item.status !== "MATCHED"}>
      <summary>Ручная проверка</summary>
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
    </details>
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

function ReviewDecisionsList({
  items,
  busy,
  onDecision,
  onRebuildPlan,
}: {
  items: MediaItem[];
  busy: boolean;
  onDecision: (itemId: number, payload: ReviewPayload) => Promise<void>;
  onRebuildPlan: () => void;
}) {
  if (items.length === 0) return <p className="muted">Объектов пока нет.</p>;
  return (
    <div className="review-decisions-list">
      {items.map((item) => {
        const title = item.localized_title ?? item.matched_title ?? item.parsed_title ?? item.original_title ?? `#${item.id}`;
        const badges = getItemBadges(item);
        return (
          <div key={item.id} className="review-decision-row">
            <div>
              <strong>{title}</strong>
              {badges.map((badge) => (
                <Badge key={badge.key} value={badge.key} label={badge.label} tone={badge.tone} />
              ))}
            </div>
            <div className="review-decision-actions">
              <button type="button" disabled={busy} onClick={() => void onDecision(item.id, { decision: "approved" })}>
                Добавить
              </button>
              <button type="button" disabled={busy} onClick={() => void onDecision(item.id, { decision: "ignored" })}>
                Не добавлять
              </button>
              <button type="button" disabled={busy} onClick={() => void onDecision(item.id, { decision: "deferred" })}>
                Отложить
              </button>
            </div>
          </div>
        );
      })}
      <button type="button" disabled={busy} onClick={onRebuildPlan}>
        Пересобрать план
      </button>
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
