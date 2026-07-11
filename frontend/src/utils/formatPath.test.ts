import { describe, expect, it } from "vitest";

import { formatPath } from "./formatPath";

describe("formatPath", () => {
  it("keeps short paths unchanged", () => {
    expect(formatPath("D:\\Media")).toBe("D:\\Media");
  });

  it("shortens the middle of long paths", () => {
    expect(formatPath("D:\\Downloads\\Incoming\\Unsorted\\Movies\\Films")).toBe("D:\\…\\Films");
  });
});
