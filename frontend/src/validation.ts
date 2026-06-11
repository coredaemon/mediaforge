export interface IdValidationResult {
  valid: boolean;
  error?: string;
}

export function validateTmdbId(value: string): IdValidationResult {
  const trimmed = value.trim();
  if (!trimmed) return { valid: true };
  if (/^tt\d+/i.test(trimmed)) {
    return {
      valid: false,
      error: "TMDB ID должен быть числом. IMDb ID нужно вводить в поле IMDb ID.",
    };
  }
  if (!/^\d+$/.test(trimmed)) {
    return { valid: false, error: "TMDB ID должен быть числом." };
  }
  return { valid: true };
}

export function validateImdbId(value: string): IdValidationResult {
  const trimmed = value.trim();
  if (!trimmed) return { valid: true };
  if (/^tt\d{7,8}$/i.test(trimmed)) return { valid: true };
  return { valid: false, error: "IMDb ID должен быть в формате tt1234567." };
}

export function validateTvdbId(value: string): IdValidationResult {
  const trimmed = value.trim();
  if (!trimmed) return { valid: true };
  if (!/^\d+$/.test(trimmed)) {
    return { valid: false, error: "TVDB ID должен быть числом." };
  }
  return { valid: true };
}

export function validateIdLookupInput(
  tmdbId: string,
  imdbId: string,
  tvdbId: string,
): IdValidationResult {
  const checks = [validateTmdbId(tmdbId), validateImdbId(imdbId), validateTvdbId(tvdbId)];
  const failed = checks.find((c) => !c.valid);
  if (failed) return failed;
  if (!tmdbId.trim() && !imdbId.trim() && !tvdbId.trim()) {
    return { valid: false, error: "Укажите TMDB ID, IMDb ID или TVDB ID." };
  }
  return { valid: true };
}
