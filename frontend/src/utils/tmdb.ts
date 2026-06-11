const TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p";

export function tmdbImageUrl(path: string | null | undefined, size = "w500"): string | null {
  if (!path) return null;
  return `${TMDB_IMAGE_BASE}/${size}${path}`;
}

export function candidatePosterUrl(candidate: {
  poster_url?: string | null;
  poster_path?: string | null;
}): string | null {
  return candidate.poster_url ?? tmdbImageUrl(candidate.poster_path);
}

export function candidateBackdropUrl(candidate: {
  backdrop_url?: string | null;
  backdrop_path?: string | null;
}): string | null {
  return candidate.backdrop_url ?? tmdbImageUrl(candidate.backdrop_path, "w780");
}
