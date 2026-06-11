from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.enums import MediaItemStatus, MediaType
from backend.app.models.media_item import MediaItem
from backend.app.repositories.media_item_repository import MediaItemRepository
from backend.app.services.scan_session_service import ScanSessionService
from backend.app.services.sidecar_metadata_service import SidecarMetadataService
from backend.app.services.tmdb_service import TMDBService
from backend.app.schemas.tmdb import TmdbDetailsResult, TmdbExternalIds, TmdbSearchResult
from backend.app.utils.nfo_parser import parse_nfo_file
from backend.tests.fakes import FakeTmdbClient


def test_parse_nfo_uniqueid_tmdb(tmp_path: Path) -> None:
    nfo = tmp_path / "movie.nfo"
    nfo.write_text(
        '<?xml version="1.0"?><movie><title>Отец</title><year>2026</year>'
        '<uniqueid type="tmdb" default="true">123456</uniqueid></movie>',
        encoding="utf-8",
    )
    result = parse_nfo_file(nfo)
    assert result.ok
    assert result.title == "Отец"
    assert result.year == 2026
    assert result.tmdb_id == 123456


def test_parse_nfo_uniqueid_imdb(tmp_path: Path) -> None:
    nfo = tmp_path / "movie.nfo"
    nfo.write_text(
        '<movie><title>Film</title><uniqueid type="imdb">tt1234567</uniqueid></movie>',
        encoding="utf-8",
    )
    result = parse_nfo_file(nfo)
    assert result.imdb_id == "tt1234567"


def test_parse_nfo_imdbid_tag(tmp_path: Path) -> None:
    nfo = tmp_path / "movie.nfo"
    nfo.write_text("<movie><imdbid>tt7654321</imdbid></movie>", encoding="utf-8")
    result = parse_nfo_file(nfo)
    assert result.imdb_id == "tt7654321"


def test_parse_nfo_cyrillic_title(tmp_path: Path) -> None:
    nfo = tmp_path / "movie.nfo"
    nfo.write_text("<movie><title>Чингис-Хан</title><year>2024</year></movie>", encoding="utf-8")
    result = parse_nfo_file(nfo)
    assert result.title == "Чингис-Хан"
    assert result.year == 2024


def test_parse_nfo_bad_xml_sets_failed(tmp_path: Path) -> None:
    nfo = tmp_path / "movie.nfo"
    nfo.write_text("<movie><title>Unclosed", encoding="utf-8")
    result = parse_nfo_file(nfo)
    assert not result.ok
    assert result.warnings


async def _item_with_sidecar(db_session: AsyncSession, tmp_path: Path, nfo_content: str) -> MediaItem:
    folder = tmp_path / "movie"
    folder.mkdir(parents=True)
    (folder / "movie.nfo").write_text(nfo_content, encoding="utf-8")
    (folder / "Отец (2026).mkv").write_bytes(b"video")
    from backend.app.models.media_file import MediaFile
    from backend.app.models.enums import MediaFileKind

    scan = await ScanSessionService(db_session).create_scan_session(str(folder), str(tmp_path / "out"))
    item = await MediaItemRepository(db_session).create(
        MediaItem(
            scan_session_id=scan.id,
            media_type=MediaType.MOVIE,
            status=MediaItemStatus.DISCOVERED,
            original_title="Отец (2026).mkv",
            parsed_title="Отец",
            year=2026,
        )
    )
    video = MediaFile(
        scan_session_id=scan.id,
        media_item_id=item.id,
        path=str(folder / "Отец (2026).mkv"),
        file_name="Отец (2026).mkv",
        extension=".mkv",
        size_bytes=10,
        kind=MediaFileKind.VIDEO,
        is_video=True,
        is_subtitle=False,
        is_sidecar=False,
    )
    db_session.add(video)
    await db_session.commit()
    await SidecarMetadataService(db_session).enrich_item_from_sidecars(item, video)
    await db_session.commit()
    return item


async def test_sidecar_tmdb_id_triggers_lookup_before_search(db_session: AsyncSession, tmp_path: Path) -> None:
    item = await _item_with_sidecar(
        db_session,
        tmp_path,
        '<movie><title>Отец</title><uniqueid type="tmdb">123456</uniqueid></movie>',
    )
    assert item.sidecar_tmdb_id == 123456
    client = FakeTmdbClient(
        movie_details={
            123456: TmdbDetailsResult(
                tmdb_id=123456,
                media_type="movie",
                title="Отец",
                overview="Описание",
                year=2026,
                external_ids=TmdbExternalIds(imdb_id="tt999"),
                metadata_language="ru-RU",
            )
        }
    )
    status = await TMDBService(db_session, client=client)._match_item(item)
    assert status == MediaItemStatus.MATCHED
    assert item.tmdb_id == 123456
    assert item.match_source == "sidecar_tmdb_id"
    assert client.movie_calls == []


async def test_sidecar_imdb_id_lookup(db_session: AsyncSession, tmp_path: Path) -> None:
    item = await _item_with_sidecar(
        db_session,
        tmp_path,
        '<movie><title>Отец</title><imdbid>tt1234567</imdbid></movie>',
    )
    client = FakeTmdbClient(
        find_results={
            ("tt1234567", "imdb_id"): [
                TmdbSearchResult(tmdb_id=555, media_type="movie", title="Отец", year=2026)
            ]
        },
        movie_details={
            555: TmdbDetailsResult(
                tmdb_id=555,
                media_type="movie",
                title="Отец",
                year=2026,
                external_ids=TmdbExternalIds(imdb_id="tt1234567"),
                metadata_language="ru-RU",
            )
        },
    )
    status = await TMDBService(db_session, client=client)._match_item(item)
    assert status == MediaItemStatus.MATCHED
    assert item.match_source == "sidecar_imdb_id"
    assert item.tmdb_id == 555


async def test_sidecar_tvdb_id_lookup(db_session: AsyncSession, tmp_path: Path) -> None:
    item = await _item_with_sidecar(
        db_session,
        tmp_path,
        '<tvshow><title>Show</title><uniqueid type="tvdb">42</uniqueid></tvshow>',
    )
    item.media_type = MediaType.TV_SHOW
    client = FakeTmdbClient(
        find_results={("42", "tvdb_id"): [TmdbSearchResult(tmdb_id=900, media_type="tv", title="Show", year=2020)]},
        tv_details={
            900: TmdbDetailsResult(
                tmdb_id=900,
                media_type="tv",
                title="Show",
                year=2020,
                external_ids=TmdbExternalIds(tvdb_id=42),
                metadata_language="ru-RU",
            )
        },
    )
    status = await TMDBService(db_session, client=client)._match_item(item)
    assert status == MediaItemStatus.MATCHED
    assert item.match_source == "sidecar_tvdb_id"


def test_priority_queries_cyrillic_first() -> None:
    from backend.app.services.tmdb_service import _priority_queries

    item = MediaItem(
        scan_session_id=1,
        media_type=MediaType.MOVIE,
        parsed_title="Отец",
        year=2026,
    )
    queries = _priority_queries(item)
    assert queries[0] == "Отец 2026"
    assert "Отец" in queries


async def test_id_lookup_failure_falls_back_to_title_search(db_session: AsyncSession, tmp_path: Path) -> None:
    item = await _item_with_sidecar(
        db_session,
        tmp_path,
        '<movie><title>Отец</title><uniqueid type="tmdb">999999</uniqueid></movie>',
    )
    client = FakeTmdbClient(
        movie_results=[TmdbSearchResult(tmdb_id=1, media_type="movie", title="Отец", year=2026)],
        movie_details={},
    )

    async def fail_details(tmdb_id: int, language: str = "ru-RU"):
        if tmdb_id == 999999:
            raise Exception("not found")
        return await FakeTmdbClient.get_movie_details(client, tmdb_id, language)

    client.get_movie_details = fail_details  # type: ignore[method-assign]
    status = await TMDBService(db_session, client=client)._match_item(item)
    assert status in {MediaItemStatus.MATCHED, MediaItemStatus.NEEDS_REVIEW}
    assert client.movie_calls
