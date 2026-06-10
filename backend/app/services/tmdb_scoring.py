from difflib import SequenceMatcher
import re

from ..schemas.tmdb import TmdbSearchResult


def normalize_title(value: str) -> str:
    normalized = re.sub(r"[\W_]+", " ", value.casefold(), flags=re.UNICODE)
    return " ".join(normalized.split())


def score_tmdb_candidate(parsed_title: str, parsed_year: int | None, candidate: TmdbSearchResult) -> float:
    parsed_normalized = normalize_title(parsed_title)
    candidate_normalized = normalize_title(candidate.title)
    if not parsed_normalized or not candidate_normalized:
        return 0.0

    similarity = SequenceMatcher(None, parsed_normalized, candidate_normalized).ratio()
    score = similarity * 0.72

    if parsed_year is not None and candidate.year is not None:
        score += 0.15 if parsed_year == candidate.year else -0.08

    if parsed_normalized == candidate_normalized:
        score += 0.08

    if candidate.popularity:
        score += min(candidate.popularity, 100.0) / 100.0 * 0.05

    return max(0.0, min(score, 1.0))
