import { describe, expect, it } from "vitest";

import { canApplyPlan, conflictOperations } from "./applyState";
import type { OperationPlan, PlanOperation } from "../types";

const plan = { id: 1, status: "READY" } as OperationPlan;

function op(validation_status?: string): PlanOperation {
  return { id: 1, plan_id: 1, operation_type: "MOVE_FILE", status: "PENDING", validation_status } as PlanOperation;
}

describe("canApplyPlan", () => {
  it("allows a ready plan with clean operations", () => {
    expect(canApplyPlan(plan, null, [op("ok")])).toBe(true);
  });

  it("blocks when operations carry a stored conflict", () => {
    expect(canApplyPlan(plan, null, [op("ok"), op("conflict")])).toBe(false);
  });

  it("blocks when validation reports conflicts", () => {
    const validation = { ok_count: 1, warning_count: 0, conflict_count: 1, operations: [] } as never;
    expect(canApplyPlan(plan, validation, [op("ok")])).toBe(false);
  });

  it("blocks non-ready plans and empty plans", () => {
    expect(canApplyPlan({ ...plan, status: "APPLIED" } as OperationPlan, null, [op("ok")])).toBe(false);
    expect(canApplyPlan(plan, null, [])).toBe(false);
    expect(canApplyPlan(null, null, [op("ok")])).toBe(false);
  });
});

describe("conflictOperations", () => {
  it("returns only conflicting operations", () => {
    const conflicting = op("conflict");
    expect(conflictOperations([op("ok"), conflicting, op(undefined)])).toEqual([conflicting]);
  });
});
