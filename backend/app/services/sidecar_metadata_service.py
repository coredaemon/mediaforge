from __future__ import annotations

from pathlib import Path

from ..models.enums import MediaFileKind
from ..models.media_file import MediaFile
from ..models.media_item import MediaItem
from ..repositories.media_file_repository import MediaFileRepository
from ..utils.nfo_parser import NfoParseResult, parse_nfo_file

NFO_CANDIDATE_NAMES = ("movie.nfo", "tvshow.nfo", "season.nfo")
POSTER_NAMES = ("poster.jpg", "folder.jpg", "cover.jpg")
BACKDROP_NAMES = ("backdrop.jpg", "fanart.jpg")
LOGO_NAMES = ("logo.png", "clearlogo.png")


class SidecarMetadataService:
    def __init__(self, session) -> None:
        self.session = session
        self.media_files = MediaFileRepository(session)

    async def enrich_item_from_sidecars(self, media_item: MediaItem, video_file: MediaFile) -> None:
        folder = Path(video_file.path).parent
        stem = Path(video_file.file_name).stem

        nfo_path = _pick_nfo_path(folder, stem)
        nfo_result: NfoParseResult | None = None
        if nfo_path is not None:
            nfo_result = parse_nfo_file(nfo_path)
            media_item.sidecar_source_path = str(nfo_path)
            if nfo_result.ok:
                media_item.sidecar_metadata_status = "found"
                _apply_nfo_to_item(media_item, nfo_result)
            else:
                media_item.sidecar_metadata_status = "parse_failed"
        else:
            media_item.sidecar_metadata_status = "not_found"

        poster = _pick_existing_file(folder, POSTER_NAMES + (f"{stem}-poster.jpg", f"{stem}.jpg"))
        backdrop = _pick_existing_file(folder, BACKDROP_NAMES + (f"{stem}-fanart.jpg",))
        logo = _pick_existing_file(folder, LOGO_NAMES)

        if poster:
            media_item.local_poster_path = str(poster)
            media_item.sidecar_poster_path = str(poster)
        if backdrop:
            media_item.local_backdrop_path = str(backdrop)
            media_item.sidecar_backdrop_path = str(backdrop)
        if logo:
            media_item.local_logo_path = str(logo)

        if media_item.local_poster_path and not media_item.poster_url:
            media_item.poster_url = f"file:///{media_item.local_poster_path.replace(chr(92), '/')}"

        if nfo_result and nfo_result.plot and not media_item.localized_overview:
            media_item.localized_overview = nfo_result.plot
        if nfo_result and nfo_result.title and not media_item.localized_title:
            media_item.localized_title = nfo_result.title

        await self.session.flush()

    async def link_sidecar_files(self, scan_session_id: int, media_item_id: int, video_file: MediaFile) -> None:
        folder = Path(video_file.path).parent
        stem = Path(video_file.file_name).stem
        session_files = await self.media_files.list_for_scan_session(scan_session_id)
        for media_file in session_files:
            if media_file.kind != MediaFileKind.SIDECAR or media_file.media_item_id is not None:
                continue
            file_path = Path(media_file.path)
            if file_path.parent != folder:
                continue
            name = file_path.name.lower()
            if (
                name.endswith(".nfo")
                or name in {n.lower() for n in POSTER_NAMES + BACKDROP_NAMES + LOGO_NAMES}
                or name.startswith(stem.lower())
            ):
                media_file.media_item_id = media_item_id
        await self.session.flush()


def _pick_nfo_path(folder: Path, stem: str) -> Path | None:
    candidates: list[Path] = []
    for name in NFO_CANDIDATE_NAMES:
        path = folder / name
        if path.exists():
            candidates.append(path)
    stem_nfo = folder / f"{stem}.nfo"
    if stem_nfo.exists():
        candidates.append(stem_nfo)
    if candidates:
        return candidates[0]
    nfo_files = sorted(folder.glob("*.nfo"))
    return nfo_files[0] if nfo_files else None


def _pick_existing_file(folder: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = folder / name
        if path.exists():
            return path
    return None


def _apply_nfo_to_item(item: MediaItem, nfo: NfoParseResult) -> None:
    item.sidecar_title = nfo.title or nfo.sorttitle
    item.sidecar_original_title = nfo.original_title
    item.sidecar_year = nfo.year
    item.sidecar_overview = nfo.plot or nfo.outline
    if nfo.tmdb_id:
        item.sidecar_tmdb_id = nfo.tmdb_id
    if nfo.imdb_id:
        item.sidecar_imdb_id = nfo.imdb_id
    if nfo.tvdb_id:
        item.sidecar_tvdb_id = nfo.tvdb_id
    if nfo.title and not item.parsed_title:
        item.parsed_title = nfo.title
    if nfo.year and not item.year:
        item.year = nfo.year
    from ..models.enums import MediaType

    if nfo.media_type_hint == "movie" and item.media_type == MediaType.UNKNOWN:
        item.media_type = MediaType.MOVIE
    elif nfo.media_type_hint in {"tvshow", "episodedetails"} and item.media_type == MediaType.UNKNOWN:
        item.media_type = MediaType.TV_EPISODE if nfo.media_type_hint == "episodedetails" else MediaType.TV_SHOW
