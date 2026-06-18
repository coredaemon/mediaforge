from pathlib import Path

from backend.app.models.scan_session import ScanSession
from backend.app.repositories.app_settings_repository import AppSettingsRepository
from backend.app.schemas.recognition import NormalizedTitle
from backend.app.services.parser_service import ParserService
from backend.app.services.recognition_clients import NormalizeParseResult
from backend.app.services.recognition_service import RecognitionService
from backend.app.services.scanner_service import ScannerService
from backend.app.services.tv_analysis_service import TvAnalysisService


async def test_movie_recognition_uses_openrouter_fast_chain(db_session, tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "Movie.Name.2024.mkv").write_bytes(b"video")
    scan = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan)
    await AppSettingsRepository(db_session).update(
        {
            "openrouter_api_key": "or-key",
            "openrouter_fast_chain": '["fast/model-a","fast/model-b"]',
        }
    )
    await db_session.commit()
    await db_session.refresh(scan)
    await ScannerService(db_session).discover(scan.id)
    await ParserService(db_session).parse_scan_session(scan.id)

    calls: list[list[str]] = []

    async def fake_normalize(self, original_name, parser_title, parser_year, context=None):
        calls.append(self.models)
        return NormalizeParseResult(
            title=NormalizedTitle(clean_title="Movie Name", year=2024, media_type="MOVIE", confidence=0.9)
        )

    monkeypatch.setattr(
        "backend.app.services.recognition_clients.OpenRouterChainTitleNormalizer.normalize",
        fake_normalize,
    )

    result = await RecognitionService(db_session).normalize_scan_session(scan.id)

    assert result.normalized_count == 1
    assert calls == [["fast/model-a", "fast/model-b"]]


async def test_tv_grouping_uses_openrouter_fast_chain(db_session, tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    season = source / "Show" / "Season 01"
    season.mkdir(parents=True)
    target.mkdir()
    (season / "Show S01E01.mkv").write_bytes(b"video")
    scan = ScanSession(source_path=str(source), target_path=str(target))
    db_session.add(scan)
    await AppSettingsRepository(db_session).update(
        {
            "openrouter_api_key": "or-key",
            "openrouter_fast_chain": '["fast/tv"]',
        }
    )
    await db_session.commit()
    await db_session.refresh(scan)
    await ScannerService(db_session).discover(scan.id)

    calls: list[list[str]] = []

    async def fake_run_json(self, *, models, messages, quality_gate=None):
        from backend.app.services.ai_router import AiRouterResult

        calls.append(models)
        return AiRouterResult(
            ok=True,
            provider="openrouter",
            model=models[0],
            normalized_json={
                "shows": [
                    {
                        "local_group_id": "show-1",
                        "probable_title": "Show",
                        "confidence": 0.9,
                        "tmdb_queries": ["Show"],
                        "seasons": [
                            {
                                "season_number": 1,
                                "episodes": [
                                    {
                                        "episode_number": 1,
                                        "file_relative_path": "Show/Season 01/Show S01E01.mkv",
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "warnings": [],
            },
        )

    monkeypatch.setattr("backend.app.services.ai_router.AiChainExecutor.run_json", fake_run_json)

    result = await TvAnalysisService(db_session).analyze_scan_session(scan.id)

    assert result.show_count == 1
    assert calls == [["fast/tv"]]
