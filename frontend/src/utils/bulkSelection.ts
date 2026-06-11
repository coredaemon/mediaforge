import type { MediaItem } from "../types";

export function isBulkSelectable(item: MediaItem): boolean {
  return item.status === "MATCHED" && !["ignored", "deferred"].includes(item.review_decision);
}

export function defaultSelectedIds(items: MediaItem[]): number[] {
  return items.filter(isBulkSelectable).map((item) => item.id);
}

export function toggleSelection(selected: Set<number>, itemId: number): Set<number> {
  const next = new Set(selected);
  if (next.has(itemId)) {
    next.delete(itemId);
  } else {
    next.add(itemId);
  }
  return next;
}
