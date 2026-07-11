import { labelOperationPreview, labelOperationStatus, labelPlanStatus } from "../../labels";
import type { ApplyRun, MediaItem, OperationPlan, PlanApplyResult, PlanOperation, PlanValidationResult } from "../../types";
import { canApplyPlan } from "../../utils/applyState";
import {
  buildPlanSummary,
  formatPlanSummaryLine,
  groupOperationsByItem,
  groupTvOperationsByShow,
  hasTvOperations,
  isTvOperation,
} from "../../utils/planSummary";

type Props = {
  plans: OperationPlan[];
  selectedPlanId: number | null;
  operations: PlanOperation[];
  items: MediaItem[];
  validation: PlanValidationResult | null;
  applyResult: PlanApplyResult | null;
  applyRuns: ApplyRun[];
  applyRunsError: string | null;
  busy: boolean;
  planStale: boolean;
  onSelectPlan: (planId: number) => void;
  onValidate: () => void;
  onApplyClick: () => void;
  onRollbackClick: () => void;
};

function itemTitle(item: MediaItem | undefined, itemId: number | null): string {
  if (!item) return itemId ? `Объект #${itemId}` : "Без привязки";
  return (
    item.localized_title ??
    item.matched_title ??
    item.parsed_title ??
    item.original_title ??
    `Объект #${item.id}`
  );
}

function renderOperation(op: PlanOperation) {
  return (
    <li key={op.id}>
      <span>{labelOperationPreview(op.operation_type)}</span>
      <span className={`status-badge ${op.status === "DONE" ? "success" : "neutral"}`}>
        {labelOperationStatus(op.status)}
      </span>
      {op.target_path ? <code>{op.target_path}</code> : null}
      {op.validation_status === "conflict" && op.validation_error ? (
        <small className="error-text">{op.validation_error}</small>
      ) : null}
    </li>
  );
}

function formatApplyResult(result: PlanApplyResult, summary: ReturnType<typeof buildPlanSummary>, tvPlan: boolean): string {
  const status = labelPlanStatus(result.status);
  const error = result.error_message ? ` · ${result.error_message}` : "";
  if (!tvPlan) {
    return `Выполнено ${result.done_operations} из ${result.total_operations}. Статус: ${status}${error}`;
  }
  return [
    `Сериалов: ${summary.tvShows}`,
    `перенесено серий: ${summary.moves}`,
    `NFO: ${summary.nfoWrites}`,
    `изображений: ${summary.imageDownloads}`,
    `выполнено операций: ${result.done_operations}/${result.total_operations}`,
    `статус: ${status}${error}`,
  ].join(" · ");
}

export function PlanApplyPanel({
  plans,
  selectedPlanId,
  operations,
  items,
  validation,
  applyResult,
  applyRuns,
  applyRunsError,
  busy,
  planStale,
  onSelectPlan,
  onValidate,
  onApplyClick,
  onRollbackClick,
}: Props) {
  const activePlan = plans.find((p) => p.id === selectedPlanId) ?? plans[0] ?? null;
  const summary = buildPlanSummary(operations, items, validation?.conflict_count ?? 0);
  const tvPlan = hasTvOperations(operations);
  const tvOnly = tvPlan && summary.movies === 0;
  const applyAllowed = canApplyPlan(activePlan, validation, operations.length);
  const rollbackAllowed = activePlan?.status === "APPLIED" || activePlan?.status === "FAILED";
  const grouped = groupOperationsByItem(operations.filter((op) => !isTvOperation(op)));
  const tvGroups = groupTvOperationsByShow(operations);
  const itemMap = new Map(items.map((item) => [item.id, item]));
  const latestRun = applyRuns[0] ?? null;
  const runProgressTotal = latestRun?.total_operations ?? 0;
  const runProgressDone = (latestRun?.done_operations ?? 0) + (latestRun?.failed_operations ?? 0);
  const runProgressPercent = runProgressTotal > 0 ? Math.round((runProgressDone / runProgressTotal) * 100) : 0;

  return (
    <section className="panel plan-apply-panel">
      <div className="section-heading">
        <div>
          <h3>{tvOnly ? "План сериалов" : "План применения"}</h3>
          <p className="muted plan-summary-line">{formatPlanSummaryLine(summary)}</p>
          {tvPlan ? (
            <p className="muted">
              Проверьте сериалный план. После подтверждения MediaForge создаст папки, перенесёт серии, запишет metadata и скачает изображения.
            </p>
          ) : (
            <p className="muted">
              Это всё ещё предварительный план. Файлы изменятся только после нажатия «Применить план».
            </p>
          )}
          {planStale ? (
            <p className="message warning">Решения по объектам изменились. Пересоберите план перед применением.</p>
          ) : null}
          {summary.excluded + summary.deferred > 0 ? (
            <p className="message warning">
              Исключено: {summary.excluded} · отложено: {summary.deferred}
            </p>
          ) : null}
          {tvPlan ? (
            <p className={applyAllowed && !planStale ? "message success" : "message warning"}>
              {activePlan?.status === "APPLIED"
                ? "План сериалов уже применён."
                : applyAllowed && !planStale
                  ? "План сериалов готов к применению."
                  : "Перед применением устраните конфликты, обновите устаревший план или выполните проверку."}
            </p>
          ) : null}
        </div>
        <div className="plan-apply-actions">
          <button type="button" disabled={busy || !activePlan} onClick={onValidate}>
            Проверить план
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={busy || !applyAllowed || planStale}
            onClick={onApplyClick}
          >
            Применить план
          </button>
          {rollbackAllowed ? (
            <button type="button" disabled={busy} onClick={onRollbackClick}>
              Откатить изменения
            </button>
          ) : null}
        </div>
      </div>

      {validation ? (
        <p className="muted">
          Проверка: OK {validation.ok_count} · предупреждения {validation.warning_count} · конфликты{" "}
          {validation.conflict_count}
        </p>
      ) : null}

      {applyResult ? (
        <p className={applyResult.failed_operations > 0 ? "message error" : "message success"}>
          {formatApplyResult(applyResult, summary, tvPlan)}
        </p>
      ) : null}

      {latestRun?.status === "running" ? (
        <div className="apply-progress" aria-label="Прогресс применения">
          <div className="apply-progress-label">
            <span>Применение выполняется</span>
            <span>
              {runProgressDone} из {runProgressTotal} операций
            </span>
          </div>
          <div className="apply-progress-track">
            <div className="apply-progress-bar" style={{ width: `${runProgressPercent}%` }} />
          </div>
        </div>
      ) : null}

      {plans.length > 0 ? (
        <div className="plan-tabs">
          {plans.map((plan) => (
            <button
              key={plan.id}
              type="button"
              className={plan.id === (selectedPlanId ?? plans[0]?.id) ? "active" : ""}
              onClick={() => onSelectPlan(plan.id)}
            >
              План #{plan.id} · {labelPlanStatus(plan.status)}
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">План ещё не построен.</p>
      )}

      {applyRunsError ? <p className="message error">{applyRunsError}</p> : null}

      {applyRuns.length > 0 ? (
        <div className="apply-runs-block">
          <h4>Журнал применения</h4>
          <div className="table-wrap">
            <table className="apply-runs-table">
              <thead>
                <tr>
                  <th>Запуск</th>
                  <th>Статус</th>
                  <th>Операций</th>
                  <th>Ошибка</th>
                </tr>
              </thead>
              <tbody>
                {applyRuns.map((run) => (
                  <tr key={run.id}>
                    <td>{new Date(run.started_at).toLocaleString("ru-RU")}</td>
                    <td>{labelPlanStatus(run.status)}</td>
                    <td>
                      {run.done_operations}/{run.total_operations}
                      {run.failed_operations > 0 ? ` (${run.failed_operations} ошибок)` : ""}
                    </td>
                    <td>{run.error_message ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {operations.length > 0 ? (
        <div className="plan-grouped-operations">
          <details className="plan-details-summary">
            <summary>Детали плана</summary>
            <ul className="plan-ready-summary">
              {summary.movies > 0 || !tvOnly ? <li>Фильмов: {summary.movies}</li> : null}
              {tvPlan ? <li>Сериалов: {summary.tvShows}</li> : null}
              {tvPlan ? <li>Сезонов: {summary.tvSeasons}</li> : null}
              {tvPlan ? <li>Эпизодов: {summary.tvEpisodes}</li> : null}
              <li>Будет создано папок: {summary.directories}</li>
              <li>Будет перемещено файлов: {summary.moves}</li>
              <li>Будет записано NFO: {summary.nfoWrites}</li>
              <li>Будет скачано изображений: {summary.imageDownloads}</li>
              <li>Исключено: {summary.excluded}</li>
              <li>Отложено: {summary.deferred}</li>
              <li>Конфликты: {summary.conflicts}</li>
            </ul>
          </details>

          {tvGroups.map((show) => (
            <details key={show.showKey} className="plan-tv-group" open={tvGroups.length === 1}>
              <summary>
                {show.title}{show.year ? ` (${show.year})` : ""} — {show.operations.length} операций
              </summary>
              <p className="muted plan-tv-group-summary">
                Сезонов: {show.seasons.filter((season) => season.seasonNumber !== null).length} · Эпизодов: {show.episodeCount}
              </p>
              {show.seasons.map((season) => (
                <details key={season.seasonNumber ?? "unknown"} className="plan-tv-season-group">
                  <summary>
                    {season.seasonNumber === null ? "Операции сериала" : `Season ${String(season.seasonNumber).padStart(2, "0")}`} —{" "}
                    {season.operations.length} операций
                    {season.episodeCount > 0 ? ` · ${season.episodeCount} эпизодов` : ""}
                  </summary>
                  <ul className="plan-op-list">{season.operations.map(renderOperation)}</ul>
                </details>
              ))}
            </details>
          ))}

          {[...grouped.entries()].map(([itemId, ops]) => (
            <details key={itemId ?? "unassigned"} className="plan-movie-group">
              <summary>
                {itemTitle(itemId ? itemMap.get(itemId) : undefined, itemId)} — {ops.length} операций
              </summary>
              <ul className="plan-op-list">{ops.map(renderOperation)}</ul>
            </details>
          ))}
        </div>
      ) : null}
    </section>
  );
}
