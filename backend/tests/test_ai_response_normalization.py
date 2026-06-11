import json

import pytest

from backend.app.utils.ai_response_normalization import (
    coerce_normalized_title,
    normalize_confidence,
    normalize_junk_tokens,
    normalize_media_type,
    normalize_tmdb_queries,
)


def test_tmdb_queries_list_str_accepted() -> None:
    queries, coerced = normalize_tmdb_queries(["In the Grey 2026", "In the Grey"])
    assert queries == ["In the Grey 2026", "In the Grey"]
    assert coerced is False


def test_tmdb_queries_list_dict_normalized() -> None:
    queries, coerced = normalize_tmdb_queries(
        [
            {"query": "In the Grey", "year": 2026},
            {"query": "In the Grey", "type": "movie"},
        ],
        clean_title="In the Grey",
        year=2026,
    )
    assert queries == ["In the Grey 2026", "In the Grey"]
    assert coerced is True


def test_tmdb_queries_dict_normalized() -> None:
    queries, coerced = normalize_tmdb_queries(
        {"title": "In the Grey", "year": 2026},
        clean_title="In the Grey",
        year=2026,
    )
    assert queries == ["In the Grey 2026"]
    assert coerced is True


def test_tmdb_queries_string_normalized() -> None:
    queries, coerced = normalize_tmdb_queries("In the Grey 2026")
    assert queries == ["In the Grey 2026"]
    assert coerced is False


def test_tmdb_queries_null_fallback() -> None:
    queries, coerced = normalize_tmdb_queries(
        None,
        clean_title="In the Grey",
        year=2026,
        parser_title="In The Grey2026 AMZN New Team",
    )
    assert queries == ["In the Grey 2026"]
    assert coerced is True


def test_confidence_accepts_multiple_formats() -> None:
    assert normalize_confidence(0.9) == 0.9
    assert normalize_confidence(90) == 0.9
    assert normalize_confidence("90%") == 0.9
    assert normalize_confidence("0.9") == 0.9


def test_junk_tokens_accepts_string_and_list() -> None:
    tokens, coerced = normalize_junk_tokens(["AMZN", "New Team"])
    assert tokens == ["AMZN", "New Team"]
    assert coerced is False

    tokens, coerced = normalize_junk_tokens("AMZN, New Team")
    assert tokens == ["AMZN", "New Team"]
    assert coerced is True


def test_useful_ai_response_with_malformed_tmdb_queries_becomes_success_with_warning() -> None:
    title, warnings = coerce_normalized_title(
        {
            "clean_title": "In the Grey",
            "year": 2026,
            "media_type": "movie",
            "confidence": 0.82,
            "junk_tokens": ["AMZN", "New Team"],
            "tmdb_queries": [{"query": "In the Grey", "year": 2026}],
            "explanation": "Removed release tags.",
        },
        parser_title="In The Grey2026 AMZN New Team",
        parser_year=2026,
    )

    assert title.clean_title == "In the Grey"
    assert title.year == 2026
    assert title.media_type == "MOVIE"
    assert title.tmdb_queries == ["In the Grey 2026"]
    assert "tmdb_queries format auto-normalized" in warnings


def test_bad_ai_response_with_no_useful_title_raises() -> None:
    with pytest.raises(ValueError, match="usable title"):
        coerce_normalized_title(
            {
                "clean_title": "",
                "year": None,
                "tmdb_queries": None,
            },
            parser_title=None,
            parser_year=None,
        )


def test_media_type_aliases_normalized() -> None:
    assert normalize_media_type("movie") == "MOVIE"
    assert normalize_media_type("film") == "MOVIE"
    assert normalize_media_type("фильм") == "MOVIE"
    assert normalize_media_type("MOVIE") == "MOVIE"
    assert normalize_media_type("series") == "TV_SHOW"
