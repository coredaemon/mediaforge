import type { MediaItem, PlanOperation } from "../types";

export type PlanSummaryCounts = {
  movies: number;
  directories: number;
  moves: number;
  nfoWrites: number;
  imageDownloads: number;
  excluded: number;
  deferred: number;
  conflicts: number;
  totalOperations: number;
};

export function getMediaItemId(operation: PlanOperation): number | null {
  const id = operation.payload_json?.media_item_id;
  return typeof id === "number" ? id : null;
}

export function groupOperationsByItem(operations: PlanOperation[]): Map<number | null, PlanOperation[]> {
  const groups = new Map<number | null, PlanOperation[]>();
  for (const operation of operations) {
    const itemId = getMediaItemId(operation);
    const bucket = groups.get(itemId) ?? [];
    bucket.push(operation);
    groups.set(itemId, bucket);
  }
  return groups;
}

export function buildPlanSummary(
  operations: PlanOperation[],
  items: MediaItem[],
  conflictCount = 0,
): PlanSummaryCounts {
  const itemIds = new Set<number>();
  let directories = 0;
  let moves = 0;
  let nfoWrites = 0;
  let imageDownloads = 0;

  for (const operation of operations) {
    const itemId = getMediaItemId(operation);
    if (itemId !== null) itemIds.add(itemId);

    switch (operation.operation_type) {
      case "CREATE_DIR":
        directories += 1;
        break;
      case "MOVE_FILE":
        moves += 1;
        break;
      case "WRITE_TEXT_FILE":
        nfoWrites += 1;
        break;
      case "DOWNLOAD_FILE":
        imageDownloads += 1;
        break;
      default:
        break;
    }
  }

  const excluded = items.filter((item) => item.review_decision === "ignored").length;
  const deferred = items.filter((item) => item.review_decision === "deferred").length;
  const conflicts =
    conflictCount > 0
      ? conflictCount
      : operations.filter((op) => op.validation_status === "conflict").length;

  return {
    movies: itemIds.size,
    directories,
    moves,
    nfoWrites,
    imageDownloads,
    excluded,
    deferred,
    conflicts,
    totalOperations: operations.length,
  };
}

export function formatPlanSummaryLine(summary: PlanSummaryCounts): string {
  return [
    `Фильмов: ${summary.movies}`,
    `операций: ${summary.totalOperations}`,
    `папок: ${summary.directories}`,
    `перемещений: ${summary.moves}`,
    `NFO: ${summary.nfoWrites}`,
    `изображений: ${summary.imageDownloads}`,
    `конфликтов: ${summary.conflicts}`,
  ].join(" · ");
}
