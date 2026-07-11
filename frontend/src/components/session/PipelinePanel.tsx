import { formatPreflightStatusLabel, getPreflightShortMessage } from "../../aiLabels";
import type { BadgeTone } from "../../labels";
import type { RecognitionPreflightResult } from "../../types";
import type { StepStatus } from "../../hooks/useSessionPipeline";

const analysisSteps: { key: string; label: string }[] = [
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

function Badge({ label, tone }: { label: string; tone?: BadgeTone }) {
  return <span className={`status-badge ${tone ?? "neutral"}`}>{label}</span>;
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
  return <Badge label={labels[status]} tone={tones[status]} />;
}

function stepIcon(status: StepStatus): string {
  if (status === "done") return "✓";
  if (status === "running") return "•";
  if (status === "error") return "×";
  return "";
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
        <small className="error-text">{shortMessage ?? check.error ?? check.message ?? "Проверка не пройдена"}</small>
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

type Props = {
  busy: boolean;
  actionLoading: string | null;
  analysisCollapsed: boolean;
  preflightResult: RecognitionPreflightResult | null;
  stepStatus: Record<string, StepStatus>;
  onRunFullAnalysis: () => void;
  onDiscover: () => void;
  onParse: () => void;
  onLocalAi: () => void;
  onMatch: () => void;
  onGemini: () => void;
  onTv: () => void;
  onTvPlan: () => void;
  onPlan: () => void;
};

export function PipelinePanel({
  busy,
  actionLoading,
  analysisCollapsed,
  preflightResult,
  stepStatus,
  onRunFullAnalysis,
  onDiscover,
  onParse,
  onLocalAi,
  onMatch,
  onGemini,
  onTv,
  onTvPlan,
  onPlan,
}: Props) {
  return (
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
        <button className="btn-primary analysis-button" disabled={busy} onClick={onRunFullAnalysis}>
          {actionLoading === "analysis" ? "Анализ выполняется..." : "Начать анализ"}
        </button>
      </div>
      {preflightResult?.warning ? <div className="message warning compact-ai-warning">{preflightResult.warning}</div> : null}
      <details className="analysis-details" open={!analysisCollapsed}>
        <summary>Статус pipeline и проверка AI</summary>
        <PreflightPanel result={preflightResult} status={stepStatus.preflight ?? "pending"} />
        <div className="pipeline-stepper">
          {analysisSteps.map((step) => (
            <div key={step.key} className={`pipeline-step ${stepStatus[step.key] ?? "pending"}`}>
              <span className="pipeline-step-marker">{stepIcon(stepStatus[step.key] ?? "pending")}</span>
              <span>{step.label}</span>
              <StepBadge status={stepStatus[step.key] ?? "pending"} />
            </div>
          ))}
        </div>
      </details>
      <details className="manual-mode">
        <summary>Ручной режим</summary>
        <div className="pipeline-actions">
          <button disabled={busy} onClick={onDiscover}>Сканировать</button>
          <button disabled={busy} onClick={onParse}>Распознать</button>
          <button disabled={busy} onClick={onLocalAi}>Локальная AI-модель</button>
          <button disabled={busy} onClick={onMatch}>Найти в TMDB</button>
          <button disabled={busy} onClick={onGemini}>Запасная модель + TMDB</button>
          <button disabled={busy} onClick={onTv}>Распознать сериалы</button>
          <button disabled={busy} onClick={onTvPlan}>Построить план сериалов</button>
          <button disabled={busy} onClick={onPlan}>Построить план</button>
        </div>
      </details>
    </section>
  );
}
