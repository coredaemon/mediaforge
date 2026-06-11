import { useCallback, useEffect, useMemo, useState } from "react";
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
  selectTmdbCandidate,
} from "../api";
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
  ScanSession,
  TmdbMatchCandidate,
} from "../types";

type StepStatus = "pending" | "running" | "done" | "error";

const analysisSteps: { key: string; label: string }[] = [
  { key: "discover", label: "Сканирование файлов" },
  { key: "parse", label: "Распознавание названий" },
  { key: "match", label: "Поиск в TMDB" },
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
  const [stepStatus, setStepStatus] = useState<Record<string, StepStatus>>({
    discover: "pending",
    parse: "pending",
    match: "pending",
    plan: "pending",
  });

  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

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
      discover: "pending",
      parse: "pending",
      match: "pending",
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
      await runStep("discover", () => discoverSession(numId));
      await runStep("parse", () => parseSession(numId));
      await runStep("match", () => matchTmdbSession(numId));
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
          {session ? <Badge value={session.status} label={labelScanSessionStatus(session.status)} /> : null}
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
            <button disabled={busy} onClick={() => void runAction("match", () => matchTmdbSession(numId), "Поиск TMDB завершён.")}>
              Найти в TMDB
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
        <ItemList items={matchedItems} onCandidates={showCandidates} />
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>Требуют проверки</h3>
          <span className="muted">{reviewItems.length}</span>
        </div>
        <ItemList items={reviewItems} onCandidates={showCandidates} />
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>Не найдено</h3>
          <span className="muted">{unmatchedItems.length}</span>
        </div>
        <ItemList items={unmatchedItems} onCandidates={showCandidates} />
      </section>

      {otherItems.length > 0 ? (
        <section className="panel">
          <h3>Другие объекты</h3>
          <ItemList items={otherItems} onCandidates={showCandidates} />
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

function ItemList({ items, onCandidates }: { items: MediaItem[]; onCandidates: (itemId: number) => Promise<void> }) {
  if (items.length === 0) {
    return <p className="muted">Нет объектов в этом разделе.</p>;
  }
  return (
    <div className="item-list">
      {items.map((item) => (
        <div key={item.id} className="item-card">
          <div className="section-heading">
            <div>
              <strong>{item.parsed_title ?? item.original_title ?? `Объект #${item.id}`}</strong>
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
            <span>Уверенность: {formatPercent(item.match_confidence ?? item.confidence)}</span>
          </div>
          <button type="button" onClick={() => void onCandidates(item.id)}>
            Кандидаты TMDB
          </button>
        </div>
      ))}
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
