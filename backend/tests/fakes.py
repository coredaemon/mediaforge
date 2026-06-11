from backend.app.schemas.tmdb import TmdbDetailsResult, TmdbExternalIds, TmdbSearchResult
from backend.app.schemas.recognition import LlmPreflightCheck, NormalizedTitle
from backend.app.services.recognition_clients import NormalizeParseResult


class FakeTmdbClient:
    def __init__(
        self,
        movie_results: list[TmdbSearchResult] | None = None,
        tv_results: list[TmdbSearchResult] | None = None,
        movie_details: dict[int, TmdbDetailsResult] | None = None,
        tv_details: dict[int, TmdbDetailsResult] | None = None,
    ) -> None:
        self.movie_results = movie_results or []
        self.tv_results = tv_results or []
        self.movie_details = movie_details or {}
        self.tv_details = tv_details or {}
        self.movie_calls: list[tuple[str, int | None, str]] = []
        self.tv_calls: list[tuple[str, int | None, str]] = []
        self.movie_detail_calls: list[tuple[int, str]] = []
        self.tv_detail_calls: list[tuple[int, str]] = []

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

    async def get_movie_details(self, tmdb_id: int, language: str = "ru-RU") -> TmdbDetailsResult:
        self.movie_detail_calls.append((tmdb_id, language))
        if tmdb_id in self.movie_details:
            return self.movie_details[tmdb_id]
        for result in self.movie_results:
            if result.tmdb_id == tmdb_id:
                return TmdbDetailsResult(
                    tmdb_id=result.tmdb_id,
                    media_type="movie",
                    title=result.title,
                    original_title=result.original_title,
                    overview=result.overview,
                    year=result.year,
                    poster_path=result.poster_path,
                    backdrop_path=result.backdrop_path,
                    external_ids=TmdbExternalIds(imdb_id="tt0133093", wikidata_id="Q83495"),
                    metadata_language=language,
                )
        return TmdbDetailsResult(
            tmdb_id=tmdb_id,
            media_type="movie",
            title="Фильм",
            original_title="Movie",
            overview="Русское описание",
            year=2026,
            poster_path="/poster.jpg",
            backdrop_path="/backdrop.jpg",
            external_ids=TmdbExternalIds(imdb_id="tt123", wikidata_id="Q1"),
            metadata_language=language,
        )

    async def get_tv_details(self, tmdb_id: int, language: str = "ru-RU") -> TmdbDetailsResult:
        self.tv_detail_calls.append((tmdb_id, language))
        if tmdb_id in self.tv_details:
            return self.tv_details[tmdb_id]
        return TmdbDetailsResult(
            tmdb_id=tmdb_id,
            media_type="tv",
            title="Сериал",
            original_title="Show",
            overview="Русское описание сериала",
            year=2020,
            poster_path="/poster.jpg",
            backdrop_path="/backdrop.jpg",
            external_ids=TmdbExternalIds(imdb_id="tt999", tvdb_id=42, wikidata_id="Q2"),
            metadata_language=language,
        )


class FakeTitleNormalizer:
    def __init__(
        self,
        result: NormalizedTitle | None = None,
        fail: bool = False,
        preflight_ok: bool = True,
        preflight_valid_json: bool = True,
    ) -> None:
        self.result = result or NormalizedTitle(clean_title="In The Grey", year=2026, media_type="MOVIE", confidence=0.92)
        self.fail = fail
        self.preflight_ok = preflight_ok
        self.preflight_valid_json = preflight_valid_json
        self.model = "fake-model"
        self.calls: list[tuple[str, str | None, int | None]] = []
        self.preflight_calls: list[str] = []

    async def normalize(
        self, original_name: str, parser_title: str | None, parser_year: int | None
    ) -> NormalizeParseResult:
        self.calls.append((original_name, parser_title, parser_year))
        if self.fail:
            raise RuntimeError("normalizer failed")
        return NormalizeParseResult(title=self.result)

    async def preflight(self, expected_provider: str) -> LlmPreflightCheck:
        self.preflight_calls.append(expected_provider)
        if self.fail:
            return LlmPreflightCheck(
                ok=False,
                provider=expected_provider,
                model=self.model,
                duration_ms=5,
                response_valid_json=False,
                error="connection failed",
                error_type="ConnectError",
            )
        return LlmPreflightCheck(
            ok=self.preflight_ok and self.preflight_valid_json,
            provider=expected_provider,
            model=self.model,
            duration_ms=7,
            response_valid_json=self.preflight_valid_json,
            error=None if self.preflight_ok and self.preflight_valid_json else "invalid preflight response",
            error_type=None if self.preflight_ok and self.preflight_valid_json else "invalid_json",
        )
