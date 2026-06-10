from backend.app.schemas.tmdb import TmdbSearchResult


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
