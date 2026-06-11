from __future__ import annotations

import re
from typing import Any

from ..schemas.recognition import NormalizedTitle

_MOVIE_ALIASES = {"movie", "film", "фильм", "кино"}
_TV_SHOW_ALIASES = {"tv", "tv_show", "series", "show", "сериал", "serial"}
_TV_EPISODE_ALIASES = {"tv_episode", "episode", "ep", "эпизод"}


def normalize_tmdb_queries(
    value: Any,
    *,
    clean_title: str | None = None,
    year: int | None = None,
    parser_title: str | None = None,
) -> tuple[list[str], bool]:
    """Return normalized query strings and whether coercion was needed."""
    coerced = False

    if value is None:
        coerced = True
        return _fallback_queries(clean_title=clean_title, year=year, parser_title=parser_title), coerced

    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return [stripped], False
        coerced = True
        return _fallback_queries(clean_title=clean_title, year=year, parser_title=parser_title), coerced

    if isinstance(value, dict):
        coerced = True
        query = _dict_to_query(value)
        if query:
            return [query], coerced
        return _fallback_queries(clean_title=clean_title, year=year, parser_title=parser_title), coerced

    if isinstance(value, list):
        if not value:
            coerced = True
            return _fallback_queries(clean_title=clean_title, year=year, parser_title=parser_title), coerced

        if all(isinstance(item, str) for item in value):
            queries = [item.strip() for item in value if isinstance(item, str) and item.strip()]
            if queries:
                return queries, False
            coerced = True
            return _fallback_queries(clean_title=clean_title, year=year, parser_title=parser_title), coerced

        if all(isinstance(item, dict) for item in value):
            coerced = True
            queries: list[str] = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                query = _dict_to_query(item)
                if query:
                    queries.append(query)
            if queries:
                return _dedupe_queries(queries), coerced
            return _fallback_queries(clean_title=clean_title, year=year, parser_title=parser_title), coerced

    coerced = True
    return _fallback_queries(clean_title=clean_title, year=year, parser_title=parser_title), coerced


def normalize_media_type(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None

    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        return None

    if normalized in _MOVIE_ALIASES or normalized == "movie":
        return "MOVIE"
    if normalized in _TV_SHOW_ALIASES or normalized == "tv_show":
        return "TV_SHOW"
    if normalized in _TV_EPISODE_ALIASES or normalized == "tv_episode":
        return "TV_EPISODE"
    if normalized == "unknown":
        return "UNKNOWN"
    if normalized in {"movie", "tv_show", "tv_episode", "unknown", "extra"}:
        return normalized.upper()
    return None


def normalize_confidence(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, str):
        stripped = value.strip().replace("%", "").strip()
        if not stripped:
            return None
        try:
            value = float(stripped)
        except ValueError:
            return None

    if not isinstance(value, (int, float)):
        return None

    numeric = float(value)
    if numeric > 1.0:
        numeric /= 100.0
    return max(0.0, min(1.0, numeric))


def normalize_junk_tokens(value: Any) -> tuple[list[str], bool]:
    if value is None:
        return [], False

    if isinstance(value, list):
        tokens = [str(item).strip() for item in value if str(item).strip()]
        return tokens, False

    if isinstance(value, str):
        if not value.strip():
            return [], False
        tokens = [part.strip() for part in re.split(r"[,;]", value) if part.strip()]
        return tokens, True

    return [], True


def coerce_normalized_title(
    data: dict[str, Any],
    *,
    parser_title: str | None = None,
    parser_year: int | None = None,
) -> tuple[NormalizedTitle, list[str]]:
    warnings: list[str] = []
    payload = dict(data)

    clean_title = _as_optional_str(payload.get("clean_title"))
    year = _as_optional_int(payload.get("year")) or parser_year

    raw_media_type = payload.get("media_type")
    media_type = normalize_media_type(raw_media_type)
    if raw_media_type is not None and media_type is None and str(raw_media_type).strip():
        warnings.append("media_type format auto-normalized")

    raw_confidence = payload.get("confidence")
    confidence = normalize_confidence(raw_confidence)
    if raw_confidence is not None and confidence is None:
        warnings.append("confidence format could not be parsed")

    junk_tokens, junk_coerced = normalize_junk_tokens(payload.get("junk_tokens"))
    if junk_coerced:
        warnings.append("junk_tokens format auto-normalized")

    raw_queries = payload.get("tmdb_queries")
    tmdb_queries, queries_coerced = normalize_tmdb_queries(
        raw_queries,
        clean_title=clean_title,
        year=year,
        parser_title=parser_title,
    )
    if queries_coerced:
        warnings.append("tmdb_queries format auto-normalized")

    if not clean_title and not tmdb_queries:
        raise ValueError("AI response did not contain a usable title.")

    title = NormalizedTitle.model_validate(
        {
            "clean_title": clean_title,
            "year": year,
            "media_type": media_type,
            "confidence": confidence,
            "junk_tokens": junk_tokens,
            "explanation": _as_optional_str(payload.get("explanation")),
            "tmdb_queries": tmdb_queries,
        }
    )
    return title, warnings


def _dict_to_query(value: dict[str, Any]) -> str | None:
    title = _as_optional_str(value.get("query")) or _as_optional_str(value.get("title"))
    if not title:
        return None
    year = _as_optional_int(value.get("year"))
    if year is not None and str(year) not in title:
        return f"{title} {year}"
    return title


def _fallback_queries(
    *,
    clean_title: str | None,
    year: int | None,
    parser_title: str | None,
) -> list[str]:
    if clean_title and year:
        return [f"{clean_title} {year}"]
    if clean_title:
        return [clean_title]
    if parser_title:
        return [parser_title]
    return []


def _dedupe_queries(values: list[str]) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if normalized and key not in seen:
            queries.append(normalized)
            seen.add(key)
    return queries


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None
