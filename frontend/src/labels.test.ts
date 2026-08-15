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

  it("translates in-plan collision messages", () => {
    expect(
      translateValidationError(
        "Two operations write the same target: D:/TV/Show S01E01.mkv (already claimed by operation 12)",
      ),
    ).toContain("Две операции пишут в один файл: D:/TV/Show S01E01.mkv");
    expect(
      translateValidationError(
        "Two operations move the same source file: D:/in/a.mkv (already claimed by operation 3)",
      ),
    ).toContain("Один исходный файл перемещают две операции: D:/in/a.mkv");
  });

  it("translates the path length message", () => {
    expect(
      translateValidationError(
        "Path is 305 characters, over the 260-character Windows limit: D:/x/y.mkv. " +
          "Shorten the library folder or enable long path support.",
      ),
    ).toContain("Путь длиной 305 символов превышает лимит Windows в 260 символов: D:/x/y.mkv");
  });

  it("keeps unknown messages as-is and handles empty values", () => {
    expect(translateValidationError("Something unexpected")).toBe("Something unexpected");
    expect(translateValidationError(null)).toBe("Конфликт без описания");
  });
});
