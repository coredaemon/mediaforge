import type { MediaItem } from "./types";
import type { BadgeTone } from "./labels";

export interface ItemBadge {
  key: string;
  label: string;
  tone: BadgeTone;
}

export function getItemBadges(item: MediaItem): ItemBadge[] {
  const badges: ItemBadge[] = [];
  const seen = new Set<string>();

  const add = (key: string, label: string, tone: BadgeTone) => {
    if (seen.has(label)) return;
    seen.add(label);
    badges.push({ key, label, tone });
  };

  if (item.review_decision === "ignored") {
    add("ignored", "Не добавлять", "danger");
    return badges;
  }
  if (item.review_decision === "deferred") {
    add("deferred", "Отложено", "warning");
    return badges;
  }

  if (item.review_decision === "manual_override") {
    add("manual", "Исправлено вручную", "info");
  } else if (item.review_decision === "approved") {
    add("approved", "Подтверждено", "success");
  }

  if (item.reused_from_memory) {
    add("memory", "Уже обработано ранее", "info");
  }

  const sidecarSources = ["sidecar_tmdb_id", "sidecar_imdb_id", "sidecar_tvdb_id"];
  if (item.match_source && sidecarSources.includes(item.match_source)) {
    add("sidecar-id", "Найдено по локальному ID", "success");
  }

  if (item.tmdb_id) {
    add("tmdb", "Найдено в TMDB", "success");
  } else if (item.local_poster_path || item.sidecar_poster_path) {
    add("local-poster", "Локальный постер", "warning");
    if (item.status === "UNMATCHED" || item.needs_review) {
      add("needs-review", "Требует проверки", "warning");
    }
  } else if (item.status === "UNMATCHED") {
    add("unmatched", "Не найдено", "danger");
  } else if (item.status === "NEEDS_REVIEW" || item.needs_review) {
    add("needs-review", "Требует проверки", "warning");
  } else if (item.status === "MATCHED" && !item.tmdb_id) {
    add("needs-review", "Требует проверки", "warning");
  }

  if (
    item.sidecar_metadata_status === "found" &&
    !sidecarSources.includes(item.match_source ?? "")
  ) {
    add("sidecar-meta", "Локальные метаданные", "info");
  }

  return badges;
}
