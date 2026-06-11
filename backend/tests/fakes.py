from backend.app.schemas.tmdb import TmdbSearchResult
from backend.app.schemas.recognition import LlmPreflightCheck, NormalizedTitle


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

    async def normalize(self, original_name: str, parser_title: str | None, parser_year: int | None) -> NormalizedTitle:
        self.calls.append((original_name, parser_title, parser_year))
        if self.fail:
            raise RuntimeError("normalizer failed")
        return self.result

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
