import { describe, expect, it } from "vitest";

import type { MediaItem } from "../types";
import { defaultSelectedIds, isBulkSelectable, toggleSelection } from "./bulkSelection";

function item(id: number, status: string, review_decision = "approved"): MediaItem {
  return { id, status, review_decision } as MediaItem;
}

describe("bulkSelection", () => {
  it("selects only matched non-excluded items by default", () => {
    const ids = defaultSelectedIds([
      item(1, "MATCHED"),
      item(2, "MATCHED", "ignored"),
      item(3, "UNMATCHED"),
    ]);

    expect(ids).toEqual([1]);
    expect(isBulkSelectable(item(4, "MATCHED", "deferred"))).toBe(false);
  });

  it("toggles selection immutably", () => {
    const selected = new Set([1]);
    const removed = toggleSelection(selected, 1);
    const added = toggleSelection(selected, 2);

    expect([...removed]).toEqual([]);
    expect([...added].sort()).toEqual([1, 2]);
    expect([...selected]).toEqual([1]);
  });
});
