import type { OperationPlan, PlanValidationResult } from "../types";

export function canApplyPlan(
  plan: OperationPlan | null,
  validation: PlanValidationResult | null,
  operationCount: number,
): boolean {
  if (!plan) return false;
  if (plan.status !== "READY") return false;
  if (operationCount === 0) return false;
  if (validation && validation.conflict_count > 0) return false;
  return true;
}

export function isPlanApplied(plan: OperationPlan | null): boolean {
  return plan?.status === "APPLIED" || plan?.status === "COMPLETED" || plan?.status === "APPLYING";
}
