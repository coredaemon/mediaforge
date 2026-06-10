from backend.app.schemas.tmdb import TmdbSearchResult
from backend.app.services.tmdb_scoring import normalize_title, score_tmdb_candidate


def test_scoring_exact_title_and_year_is_high() -> None:
    candidate = TmdbSearchResult(tmdb_id=1, media_type="movie", title="The Matrix", year=1999, popularity=80)

    score = score_tmdb_candidate("The Matrix", 1999, candidate)

    assert score >= 0.80


def test_scoring_wrong_year_is_lower_than_exact_year() -> None:
    exact = TmdbSearchResult(tmdb_id=1, media_type="movie", title="The Matrix", year=1999)
    wrong_year = TmdbSearchResult(tmdb_id=2, media_type="movie", title="The Matrix", year=2003)

    assert score_tmdb_candidate("The Matrix", 2003, wrong_year) > score_tmdb_candidate("The Matrix", 1999, wrong_year)
    assert score_tmdb_candidate("The Matrix", 1999, wrong_year) < score_tmdb_candidate("The Matrix", 1999, exact)


def test_scoring_different_title_is_lower() -> None:
    exact = TmdbSearchResult(tmdb_id=1, media_type="movie", title="The Matrix", year=1999)
    different = TmdbSearchResult(tmdb_id=2, media_type="movie", title="Alien", year=1979)

    assert score_tmdb_candidate("The Matrix", 1999, different) < score_tmdb_candidate("The Matrix", 1999, exact)


def test_normalize_title_handles_case_dots_and_underscores() -> None:
    assert normalize_title("The.Matrix_1999") == normalize_title("the matrix 1999")
