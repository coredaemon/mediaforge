import { describe, expect, it } from "vitest";

import { labelPlanStatus, statusTone, translateValidationError } from "./labels";

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

describe("translateValidationError", () => {
  it("translates known validation messages", () => {
    expect(translateValidationError("Target file already exists: D:/Movies/a.mkv")).toBe(
      "Целевой файл уже существует: D:/Movies/a.mkv",
    );
    expect(translateValidationError("Directory already exists: D:/Movies")).toBe(
      "Папка уже существует: D:/Movies",
    );
  });

  it("keeps unknown messages as-is and handles empty values", () => {
    expect(translateValidationError("Something unexpected")).toBe("Something unexpected");
    expect(translateValidationError(null)).toBe("Конфликт без описания");
  });
});
