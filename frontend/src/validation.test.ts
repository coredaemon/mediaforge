import { describe, expect, it } from "vitest";

import { validateIdLookupInput, validateImdbId, validateTmdbId, validateTvdbId } from "./validation";

describe("validation", () => {
  it("accepts numeric TMDB and TVDB ids", () => {
    expect(validateTmdbId("123").valid).toBe(true);
    expect(validateTvdbId("456").valid).toBe(true);
  });

  it("rejects IMDb ids in the TMDB field", () => {
    expect(validateTmdbId("tt1234567").valid).toBe(false);
  });

  it("validates IMDb id shape", () => {
    expect(validateImdbId("tt1234567").valid).toBe(true);
    expect(validateImdbId("1234567").valid).toBe(false);
  });

  it("requires at least one lookup id", () => {
    expect(validateIdLookupInput("", "", "").valid).toBe(false);
    expect(validateIdLookupInput("", "tt1234567", "").valid).toBe(true);
  });
});
