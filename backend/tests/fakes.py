from backend.app.schemas.tmdb import TmdbSearchResult
from backend.app.schemas.recognition import NormalizedTitle


class FakeTmdbClient:
    def __init__(
        self,
        movie_results: list[TmdbSearchResult] | None = None,
        tv_results: list[TmdbSearchResult] | None = None,
    ) -> None:
        self.movie_results = movie_results or []
        self.tv_results = tv_results or []
        self.movie_calls: list[tuple[str, int | None, str]] = []
        self.tv_calls: list[tuple[str, int | None, str]] = []

    async def search_movie(
        self,
        query: str,
        year: int | None = None,
        language: str = "ru-RU",
    ) -> list[TmdbSearchResult]:
        self.movie_calls.append((query, year, language))
        return self.movie_results

    async def search_tv(
        self,
        query: str,
        year: int | None = None,
        language: str = "ru-RU",
    ) -> list[TmdbSearchResult]:
        self.tv_calls.append((query, year, language))
        return self.tv_results


class FakeTitleNormalizer:
    def __init__(self, result: NormalizedTitle | None = None, fail: bool = False) -> None:
        self.result = result or NormalizedTitle(clean_title="In The Grey", year=2026, media_type="MOVIE", confidence=0.92)
        self.fail = fail
        self.calls: list[tuple[str, str | None, int | None]] = []

    async def normalize(self, original_name: str, parser_title: str | None, parser_year: int | None) -> NormalizedTitle:
        self.calls.append((original_name, parser_title, parser_year))
        if self.fail:
            raise RuntimeError("normalizer failed")
        return self.result
