import { describe, expect, it } from "vitest";

import { candidateBackdropUrl, candidatePosterUrl, tmdbImageUrl } from "./tmdb";

describe("tmdb utils", () => {
  it("builds image urls from TMDB paths", () => {
    expect(tmdbImageUrl("/poster.jpg")).toBe("https://image.tmdb.org/t/p/w500/poster.jpg");
    expect(tmdbImageUrl("/backdrop.jpg", "w780")).toBe("https://image.tmdb.org/t/p/w780/backdrop.jpg");
  });

  it("prefers provided poster and backdrop urls", () => {
    expect(candidatePosterUrl({ poster_url: "https://cdn/poster.jpg", poster_path: "/poster.jpg" })).toBe("https://cdn/poster.jpg");
    expect(candidateBackdropUrl({ backdrop_url: "https://cdn/backdrop.jpg", backdrop_path: "/backdrop.jpg" })).toBe("https://cdn/backdrop.jpg");
  });

  it("returns null for missing image paths", () => {
    expect(tmdbImageUrl(null)).toBeNull();
    expect(candidatePosterUrl({})).toBeNull();
  });
});
