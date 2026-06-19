import type { MediaItem, PlanOperation } from "../types";

export type PlanSummaryCounts = {
  movies: number;
  tvShows: number;
  tvSeasons: number;
  tvEpisodes: number;
  hasTvOperations: boolean;
  directories: number;
  moves: number;
  nfoWrites: number;
  imageDownloads: number;
  excluded: number;
  deferred: number;
  conflicts: number;
  totalOperations: number;
};

export type TvPlanSeasonGroup = {
  seasonNumber: number | null;
  operations: PlanOperation[];
  episodeCount: number;
};

export type TvPlanShowGroup = {
  showKey: string;
  showId: number | null;
  title: string;
  year: number | null;
  operations: PlanOperation[];
  seasons: TvPlanSeasonGroup[];
  episodeCount: number;
};

export function getMediaItemId(operation: PlanOperation): number | null {
  const id = operation.payload_json?.media_item_id;
  return typeof id === "number" ? id : null;
}

function payloadNumber(operation: PlanOperation, key: string): number | null {
  const value = operation.payload_json?.[key];
  return typeof value === "number" ? value : null;
}

function payloadString(operation: PlanOperation, key: string): string | null {
  const value = operation.payload_json?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

export function isTvOperation(operation: PlanOperation): boolean {
  const payload = operation.payload_json ?? {};
  return payload.media_type === "tv" || payload.tv_apply_disabled === true || typeof payload.tv_show_id === "number";
}

export function hasTvOperations(operations: PlanOperation[]): boolean {
  return operations.some(isTvOperation);
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
  const tvShowKeys = new Set<string>();
  const tvSeasonKeys = new Set<string>();
  const tvEpisodeKeys = new Set<string>();
  let directories = 0;
  let moves = 0;
  let nfoWrites = 0;
  let imageDownloads = 0;

  for (const operation of operations) {
    const itemId = getMediaItemId(operation);
    if (itemId !== null) itemIds.add(itemId);
    if (isTvOperation(operation)) {
      const showKey = tvShowGroupKey(operation);
      tvShowKeys.add(showKey);
      const seasonNumber = payloadNumber(operation, "season_number");
      if (seasonNumber !== null) tvSeasonKeys.add(`${showKey}:${seasonNumber}`);
      const episodeId = payloadNumber(operation, "tv_episode_id");
      const episodeNumber = payloadNumber(operation, "episode_number");
      if (episodeId !== null) tvEpisodeKeys.add(`id:${episodeId}`);
      else if (seasonNumber !== null && episodeNumber !== null) tvEpisodeKeys.add(`${showKey}:${seasonNumber}:${episodeNumber}`);
    }

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
    tvShows: tvShowKeys.size,
    tvSeasons: tvSeasonKeys.size,
    tvEpisodes: tvEpisodeKeys.size,
    hasTvOperations: tvShowKeys.size > 0,
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
  const parts = [
    `операций: ${summary.totalOperations}`,
    `папок: ${summary.directories}`,
    `перемещений: ${summary.moves}`,
    `NFO: ${summary.nfoWrites}`,
    `изображений: ${summary.imageDownloads}`,
    `конфликтов: ${summary.conflicts}`,
  ];
  if (summary.hasTvOperations) {
    parts.unshift(`Сериалов: ${summary.tvShows}`, `сезонов: ${summary.tvSeasons}`, `эпизодов: ${summary.tvEpisodes}`);
  }
  if (!summary.hasTvOperations || summary.movies > 0) {
    parts.unshift(`Фильмов: ${summary.movies}`);
  }
  return parts.join(" · ");
}

function tvShowGroupKey(operation: PlanOperation): string {
  const showId = payloadNumber(operation, "tv_show_id");
  if (showId !== null) return `show:${showId}`;
  const title = payloadString(operation, "tv_show_title") ?? "Сериал";
  return `title:${title}`;
}

function tvSeasonSortValue(seasonNumber: number | null): number {
  return seasonNumber ?? Number.MAX_SAFE_INTEGER;
}

export function groupTvOperationsByShow(operations: PlanOperation[]): TvPlanShowGroup[] {
  const groups = new Map<string, TvPlanShowGroup>();
  for (const operation of operations.filter(isTvOperation)) {
    const showKey = tvShowGroupKey(operation);
    const showId = payloadNumber(operation, "tv_show_id");
    const title = payloadString(operation, "tv_show_title") ?? (showId ? `Сериал #${showId}` : "Сериал");
    const year = payloadNumber(operation, "tv_show_year");
    const group = groups.get(showKey) ?? {
      showKey,
      showId,
      title,
      year,
      operations: [],
      seasons: [],
      episodeCount: 0,
    };
    group.operations.push(operation);
    groups.set(showKey, group);
  }

  for (const group of groups.values()) {
    const seasonMap = new Map<string, TvPlanSeasonGroup>();
    const episodeKeys = new Set<string>();
    for (const operation of group.operations) {
      const seasonNumber = payloadNumber(operation, "season_number");
      const seasonKey = seasonNumber === null ? "unknown" : String(seasonNumber);
      const seasonGroup = seasonMap.get(seasonKey) ?? { seasonNumber, operations: [], episodeCount: 0 };
      seasonGroup.operations.push(operation);
      seasonMap.set(seasonKey, seasonGroup);

      const episodeId = payloadNumber(operation, "tv_episode_id");
      const episodeNumber = payloadNumber(operation, "episode_number");
      if (episodeId !== null) episodeKeys.add(`id:${episodeId}`);
      else if (seasonNumber !== null && episodeNumber !== null) episodeKeys.add(`${seasonNumber}:${episodeNumber}`);
    }
    for (const seasonGroup of seasonMap.values()) {
      const seasonEpisodeKeys = new Set<string>();
      for (const operation of seasonGroup.operations) {
        const episodeId = payloadNumber(operation, "tv_episode_id");
        const episodeNumber = payloadNumber(operation, "episode_number");
        if (episodeId !== null) seasonEpisodeKeys.add(`id:${episodeId}`);
        else if (episodeNumber !== null) seasonEpisodeKeys.add(String(episodeNumber));
      }
      seasonGroup.episodeCount = seasonEpisodeKeys.size;
    }
    group.episodeCount = episodeKeys.size;
    group.seasons = [...seasonMap.values()].sort((a, b) => tvSeasonSortValue(a.seasonNumber) - tvSeasonSortValue(b.seasonNumber));
  }

  return [...groups.values()].sort((a, b) => a.title.localeCompare(b.title, "ru"));
}
