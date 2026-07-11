import { describe, expect, it } from "vitest";

import type { MediaItem, PlanOperation } from "../types";
import { buildPlanSummary, groupOperationsByItem, groupTvOperationsByShow, hasTvOperations } from "./planSummary";

function op(id: number, operation_type: string, payload_json: Record<string, unknown> = {}): PlanOperation {
  return {
    id,
    plan_id: 1,
    operation_type,
    status: "PENDING",
    source_path: null,
    target_path: null,
    payload_json,
    error_message: null,
    validation_status: "ok",
    validation_error: null,
    validated_at: null,
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

function item(id: number, review_decision = "approved"): MediaItem {
  return { id, review_decision } as MediaItem;
}

describe("planSummary", () => {
  it("counts movie and operation totals", () => {
    const operations = [
      op(1, "CREATE_DIR", { media_item_id: 10 }),
      op(2, "MOVE_FILE", { media_item_id: 10 }),
      op(3, "WRITE_TEXT_FILE", { media_item_id: 10 }),
      op(4, "DOWNLOAD_FILE", { media_item_id: 10 }),
    ];

    const summary = buildPlanSummary(operations, [item(10), item(11, "ignored")]);

    expect(summary.movies).toBe(1);
    expect(summary.directories).toBe(1);
    expect(summary.moves).toBe(1);
    expect(summary.nfoWrites).toBe(1);
    expect(summary.imageDownloads).toBe(1);
    expect(summary.excluded).toBe(1);
  });

  it("groups tv operations by show and season", () => {
    const operations = [
      op(1, "MOVE_FILE", { media_type: "tv", tv_show_id: 7, tv_show_title: "Show", season_number: 1, episode_number: 1 }),
      op(2, "WRITE_TEXT_FILE", { media_type: "tv", tv_show_id: 7, tv_show_title: "Show", season_number: 1, episode_number: 1 }),
    ];

    expect(hasTvOperations(operations)).toBe(true);
    const groups = groupTvOperationsByShow(operations);
    expect(groups).toHaveLength(1);
    expect(groups[0]?.episodeCount).toBe(1);
    expect(groups[0]?.seasons[0]?.operations).toHaveLength(2);
  });

  it("groups operations by media item id", () => {
    const groups = groupOperationsByItem([op(1, "MOVE_FILE", { media_item_id: 1 }), op(2, "CREATE_DIR")]);

    expect(groups.get(1)).toHaveLength(1);
    expect(groups.get(null)).toHaveLength(1);
  });
});
