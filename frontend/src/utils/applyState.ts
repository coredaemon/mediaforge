import type { OperationPlan, PlanOperation, PlanValidationResult } from "../types";

export function conflictOperations(operations: PlanOperation[]): PlanOperation[] {
  return operations.filter((op) => op.validation_status === "conflict");
}

export function canApplyPlan(
  plan: OperationPlan | null,
  validation: PlanValidationResult | null,
  operations: PlanOperation[],
): boolean {
  if (!plan) return false;
  if (plan.status !== "READY") return false;
  if (operations.length === 0) return false;
  if (validation && validation.conflict_count > 0) return false;
  if (conflictOperations(operations).length > 0) return false;
  return true;
}

export function isPlanApplied(plan: OperationPlan | null): boolean {
  return plan?.status === "APPLIED" || plan?.status === "COMPLETED" || plan?.status === "APPLYING";
}
