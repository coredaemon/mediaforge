import { describe, expect, it } from "vitest";

import { labelPlanStatus, statusTone } from "./labels";

describe("labels", () => {
  it("maps known statuses to tones", () => {
    expect(statusTone("APPLIED")).toBe("success");
    expect(statusTone("APPLYING")).toBe("info");
    expect(statusTone("FAILED")).toBe("danger");
    expect(statusTone("ROLLED_BACK")).toBe("warning");
  });

  it("labels rolled back statuses", () => {
    expect(labelPlanStatus("ROLLED_BACK")).toBe("Откачено");
    expect(labelPlanStatus("rolled_back")).toBe("Откачено");
  });
});
