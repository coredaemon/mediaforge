import type { BulkReviewResult } from "../../types";

type Props = {
  busy: boolean;
  selectedCount: number;
  plannable: number;
  ignored: number;
  deferred: number;
  lastResult: BulkReviewResult | null;
  onApproveAll: () => void;
  onApproveSelected: () => void;
  onIgnoreSelected: () => void;
  onDeferSelected: () => void;
  onClearSelection: () => void;
  onRebuildPlan: () => void;
};

export function BulkReviewToolbar({
  busy,
  selectedCount,
  plannable,
  ignored,
  deferred,
  lastResult,
  onApproveAll,
  onApproveSelected,
  onIgnoreSelected,
  onDeferSelected,
  onClearSelection,
  onRebuildPlan,
}: Props) {
  const hasSelection = selectedCount > 0;
  return (
    <div className="bulk-review-toolbar">
      <strong>Массовые действия</strong>
      <p className="muted bulk-selection-counters">
        Выбрано: {selectedCount} · в план: {plannable} · исключено: {ignored} · отложено: {deferred}
      </p>
      <div className="bulk-review-actions">
        <button type="button" disabled={busy} onClick={onApproveAll}>
          Одобрить всё найденное
        </button>
        <button type="button" disabled={busy || !hasSelection} onClick={onApproveSelected}>
          Одобрить выбранные
        </button>
        <button type="button" disabled={busy || !hasSelection} onClick={onIgnoreSelected}>
          Не добавлять выбранные
        </button>
        <button type="button" disabled={busy || !hasSelection} onClick={onDeferSelected}>
          Отложить выбранные
        </button>
        <button type="button" disabled={busy || !hasSelection} onClick={onClearSelection}>
          Сбросить выбор
        </button>
        <button type="button" disabled={busy} onClick={onRebuildPlan}>
          Пересобрать план
        </button>
      </div>
      {lastResult ? (
        <p className="muted bulk-result">
          Одобрено: {lastResult.approved_count} · пропущено: {lastResult.skipped_count}
          {lastResult.ignored_count > 0 ? ` · исключено: ${lastResult.ignored_count}` : ""}
          {lastResult.deferred_count > 0 ? ` · отложено: ${lastResult.deferred_count}` : ""}
        </p>
      ) : null}
    </div>
  );
}
