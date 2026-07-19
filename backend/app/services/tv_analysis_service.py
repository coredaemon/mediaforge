from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..models.enums import MediaFileKind, ReviewDecision
from ..models.tv_episode import TvEpisode
from ..models.tv_season import TvSeason
from ..models.tv_show import TvShow
from ..repositories.app_settings_repository import AppSettingsRepository
from ..repositories.media_file_repository import MediaFileRepository
from ..repositories.scan_session_repository import ScanSessionRepository
from ..repositories.tv_repository import TvRepository
from ..schemas.tmdb import TmdbDetailsResult, TmdbSearchResult
from ..schemas.tv import TvAnalyzeResult, TvFolderContext, TvReviewDecisionRequest
from ..services.scan_session_service import ScanSessionNotFoundError
from ..utils.media_name_parser import parse_episode_range
from ..utils.tmdb_images import tmdb_image_url
from .tmdb_client import (
    TmdbApiKeyMissingError,
    TmdbClient,
    TmdbClientProtocol,
    fetch_localized_details,
    fetch_localized_tv_season_details,
)
from .tv_ai import TvAiGroupingService, TvCloudAuditService
from .tv_folder_context import TvFolderContextBuilder


logger = logging.getLogger(__name__)

# Above this, a TMDB match is treated as settled and needs no manual confirmation.
CONFIDENT_MATCH_THRESHOLD = 0.8


class TvShowNotFoundError(LookupError):
    """Raised when a TV show does not exist."""


class TvEpisodeNotFoundError(LookupError):
    """Raised when a TV episode does not exist."""


class TvAnalysisService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        tmdb_client: TmdbClientProtocol | None = None,
        local_client: object | None = None,
        gemini_client: object | None = None,
    ) -> None:
        self.session = session
        self.scan_sessions = ScanSessionRepository(session)
        self.media_files = MediaFileRepository(session)
        self.tv = TvRepository(session)
        self.settings = AppSettingsRepository(session)
        self.tmdb_client = tmdb_client
        self.local_client = local_client
        self.gemini_client = gemini_client

    async def analyze_scan_session(self, scan_session_id: int, force: bool = True) -> TvAnalyzeResult:
        scan_session = await self.scan_sessions.get(scan_session_id)
        if scan_session is None:
            raise ScanSessionNotFoundError(f"Scan session {scan_session_id} was not found.")
        manual_choices: list[dict[str, Any]] = []
        if force:
            # A re-analysis must not throw away a match the user picked by hand.
            manual_choices = await self._collect_manual_choices(scan_session_id)
            await self.tv.delete_for_scan_session(scan_session_id)
            await self.session.flush()

        context = await TvFolderContextBuilder(self.session).build(scan_session_id)
        grouping = await TvAiGroupingService(self.session, self.local_client).group(scan_session_id, context)
        tmdb_data = await self._match_grouping(grouping)
        audit = await TvCloudAuditService(self.session, self.gemini_client).audit(
            scan_session_id,
            context,
            grouping,
            tmdb_data,
        )
        shows = await self._persist(scan_session_id, context, grouping, tmdb_data, audit)
        if manual_choices:
            await self._restore_manual_choices(shows, manual_choices)
        season_count = sum(len(show.get("seasons") or []) for show in grouping.get("shows", []))
        episode_count = sum(
            len(season.get("episodes") or [])
            for show in grouping.get("shows", [])
            for season in show.get("seasons") or []
        )
        warning_count = sum(len(show.warnings or []) for show in shows)
        await self.session.commit()
        return TvAnalyzeResult(
            scan_session_id=scan_session_id,
            show_count=len(shows),
            season_count=season_count,
            episode_count=episode_count,
            warning_count=warning_count,
        )

    async def list_shows(self, scan_session_id: int) -> list[TvShow]:
        if await self.scan_sessions.get(scan_session_id) is None:
            raise ScanSessionNotFoundError(f"Scan session {scan_session_id} was not found.")
        return list(await self.tv.list_shows(scan_session_id))

    async def get_show(self, show_id: int) -> TvShow:
        show = await self.tv.get_show(show_id)
        if show is None:
            raise TvShowNotFoundError(f"TV show {show_id} was not found.")
        return show

    async def search_show_tmdb(self, show_id: int, query: str, year: int | None = None) -> list[TmdbSearchResult]:
        await self.get_show(show_id)
        client = await self._ensure_tmdb_client()
        results = await client.search_tv(query=query, year=year, language="ru-RU")
        if not results:
            results = await client.search_tv(query=query, year=year, language="en-US")
        return results

    async def lookup_show_tmdb(
        self,
        show_id: int,
        *,
        tmdb_id: int | None = None,
        imdb_id: str | None = None,
        tvdb_id: int | None = None,
        select: bool = False,
    ) -> TvShow:
        show = await self.get_show(show_id)
        client = await self._ensure_tmdb_client()
        details: TmdbDetailsResult | None = None
        source = "manual_override"
        if tmdb_id is not None:
            details = await fetch_localized_details(client, tmdb_id=tmdb_id, media_type="tv")
            source = "manual_tmdb_id"
        elif imdb_id:
            results = await client.find_by_external_id(imdb_id, "imdb_id")
            picked = _pick_tv_result(results)
            details = await fetch_localized_details(client, tmdb_id=picked.tmdb_id, media_type="tv")
            source = "manual_imdb_id"
        elif tvdb_id is not None:
            results = await client.find_by_external_id(str(tvdb_id), "tvdb_id")
            picked = _pick_tv_result(results)
            details = await fetch_localized_details(client, tmdb_id=picked.tmdb_id, media_type="tv")
            source = "manual_tvdb_id"
        else:
            raise ValueError("Укажите TMDB ID, IMDb ID или TVDB ID.")

        if select:
            await self._apply_show_details(show, details, source)
            show.review_decision = ReviewDecision.MANUAL_OVERRIDE
            show.needs_review = False
            await self._enrich_episodes_from_tmdb(show)
            await self.session.commit()
            await self.session.refresh(show)
        return show

    async def apply_review_decision(self, show_id: int, payload: TvReviewDecisionRequest) -> TvShow:
        show = await self.get_show(show_id)
        if payload.manual_tmdb_id or payload.manual_imdb_id or payload.manual_tvdb_id:
            await self.lookup_show_tmdb(
                show_id,
                tmdb_id=payload.manual_tmdb_id,
                imdb_id=payload.manual_imdb_id,
                tvdb_id=payload.manual_tvdb_id,
                select=True,
            )
            show = await self.get_show(show_id)
        if payload.manual_title:
            show.title = payload.manual_title
        if payload.manual_year:
            show.year = payload.manual_year
        if payload.decision not in {ReviewDecision.APPROVED, ReviewDecision.IGNORED, ReviewDecision.DEFERRED, ReviewDecision.MANUAL_OVERRIDE}:
            raise ValueError(f"Unsupported review decision: {payload.decision}")
        show.review_decision = payload.decision
        if payload.decision in {ReviewDecision.APPROVED, ReviewDecision.MANUAL_OVERRIDE}:
            show.needs_review = False
        elif payload.decision in {ReviewDecision.IGNORED, ReviewDecision.DEFERRED}:
            show.needs_review = False
        if payload.decision == ReviewDecision.MANUAL_OVERRIDE:
            show.match_source = show.match_source or "manual_override"
        await self.session.commit()
        await self.session.refresh(show)
        return show

    async def _collect_manual_choices(self, scan_session_id: int) -> list[dict[str, Any]]:
        """Remember hand-picked matches, keyed by the files they cover."""
        choices: list[dict[str, Any]] = []
        for show in await self.tv.list_shows(scan_session_id):
            is_manual = show.review_decision == ReviewDecision.MANUAL_OVERRIDE or (
                show.match_source or ""
            ).startswith("manual")
            if not is_manual or not show.tmdb_id:
                continue
            files = {
                episode.source_path
                for episode in await self.tv.list_episodes(show.id)
                if episode.source_path
            }
            if files:
                choices.append(
                    {
                        "files": files,
                        "tmdb_id": show.tmdb_id,
                        "title": show.title,
                        "year": show.year,
                        "match_source": show.match_source,
                        "review_decision": show.review_decision,
                    }
                )
        return choices

    async def _restore_manual_choices(self, shows: list[TvShow], choices: list[dict[str, Any]]) -> None:
        """Re-apply a remembered match to the show that owns the same files."""
        for show in shows:
            # Freshly persisted shows have no loaded relationships, so query episodes.
            files = {
                episode.source_path
                for episode in await self.tv.list_episodes(show.id)
                if episode.source_path
            }
            if not files:
                continue
            best = max(
                choices,
                key=lambda choice: len(files & choice["files"]),
                default=None,
            )
            if best is None:
                continue
            overlap = len(files & best["files"])
            if overlap * 2 <= len(files):  # needs a majority of the same files
                continue
            if show.tmdb_id == best["tmdb_id"]:
                continue
            try:
                await self.lookup_show_tmdb(show.id, tmdb_id=best["tmdb_id"], select=True)
            except Exception:  # noqa: BLE001 - a failed restore must not fail the analysis
                logger.warning("Could not restore manual TMDB choice for show %s", show.id, exc_info=True)
                continue
            show.review_decision = best["review_decision"]
            show.match_source = best["match_source"] or "manual_override"
            show.needs_review = False
        await self.session.flush()

    async def acknowledge_episode(self, episode_id: int) -> TvEpisode:
        """Accept an episode as-is, clearing the review flag that blocks planning.

        Used for episodes that differ from TMDB (merged double episodes, shifted
        numbering) but whose file is correct and should be planned anyway.
        """
        episode = await self.tv.get_episode(episode_id)
        if episode is None:
            raise TvEpisodeNotFoundError(f"TV episode {episode_id} was not found.")
        episode.needs_review = False
        episode.review_acknowledged = True
        await self.session.commit()
        await self.session.refresh(episode)
        return episode

    async def _match_grouping(self, grouping: dict[str, Any]) -> dict[str, Any]:
        try:
            client = await self._ensure_tmdb_client()
        except TmdbApiKeyMissingError:
            return {"shows": {}, "warnings": ["TMDB API key is not configured; TV matching skipped."]}

        matched: dict[str, Any] = {}
        for show in grouping.get("shows", []):
            group_id = show.get("local_group_id")
            details = None
            source = None
            external_ids = show.get("external_ids") or {}
            for key, external_source, match_source in (
                ("tmdb_id", None, "sidecar_tmdb_id"),
                ("imdb_id", "imdb_id", "sidecar_imdb_id"),
                ("tvdb_id", "tvdb_id", "sidecar_tvdb_id"),
            ):
                value = external_ids.get(key)
                if not value:
                    continue
                try:
                    if key == "tmdb_id":
                        details = await fetch_localized_details(client, tmdb_id=int(value), media_type="tv")
                    else:
                        results = await client.find_by_external_id(str(value), external_source or "")
                        picked = _pick_tv_result(results)
                        details = await fetch_localized_details(client, tmdb_id=picked.tmdb_id, media_type="tv")
                    source = match_source
                    break
                except Exception:
                    continue
            candidates: list[TmdbSearchResult] = []
            if details is None:
                for query in show.get("tmdb_queries") or [show.get("probable_title")]:
                    if not query:
                        continue
                    candidates = await client.search_tv(query=query, year=show.get("year"), language="ru-RU")
                    if not candidates:
                        candidates = await client.search_tv(query=query, year=show.get("year"), language="en-US")
                    if candidates:
                        details = await fetch_localized_details(client, tmdb_id=candidates[0].tmdb_id, media_type="tv")
                        source = "local_llm_grouping"
                        break
            matched[group_id] = {"details": details.model_dump() if details else None, "source": source, "candidates": [c.model_dump() for c in candidates[:5]]}
        return {"shows": matched, "warnings": []}

    async def _persist(
        self,
        scan_session_id: int,
        context: TvFolderContext,
        grouping: dict[str, Any],
        tmdb_data: dict[str, Any],
        audit: dict[str, Any],
    ) -> list[TvShow]:
        file_by_relative = await self._files_by_relative(scan_session_id, context)
        audit_by_id = {show.get("local_group_id"): show for show in audit.get("shows", [])}
        saved: list[TvShow] = []
        for grouped_show in grouping.get("shows", []):
            group_id = grouped_show.get("local_group_id")
            audited = audit_by_id.get(group_id, {})
            tmdb_entry = (tmdb_data.get("shows") or {}).get(group_id) or {}
            details = tmdb_entry.get("details") or {}
            title = audited.get("corrected_title") or details.get("title") or grouped_show.get("probable_title") or "Unknown Show"
            tmdb_id = audited.get("selected_tmdb_id") or details.get("tmdb_id")
            match_confidence = audited.get("confidence") or grouped_show.get("confidence") or 0.0
            show = await self.tv.add_show(
                TvShow(
                    scan_session_id=scan_session_id,
                    local_group_id=group_id,
                    title=title,
                    original_title=details.get("original_title") or grouped_show.get("original_title"),
                    year=audited.get("corrected_year") or details.get("year") or grouped_show.get("year"),
                    tmdb_id=tmdb_id,
                    imdb_id=(details.get("external_ids") or {}).get("imdb_id") or (grouped_show.get("external_ids") or {}).get("imdb_id"),
                    tvdb_id=(details.get("external_ids") or {}).get("tvdb_id") or (grouped_show.get("external_ids") or {}).get("tvdb_id"),
                    wikidata_id=(details.get("external_ids") or {}).get("wikidata_id"),
                    overview=details.get("overview"),
                    poster_path=details.get("poster_path"),
                    poster_url=tmdb_image_url(details.get("poster_path")),
                    backdrop_path=details.get("backdrop_path"),
                    backdrop_url=tmdb_image_url(details.get("backdrop_path"), "w780"),
                    language=details.get("metadata_language") or grouped_show.get("language"),
                    match_source=tmdb_entry.get("source") or "local_llm_grouping",
                    confidence=match_confidence or None,
                    review_decision=ReviewDecision.PENDING,
                    # Review is about the match itself. The AI also raises
                    # manual_review_required for library-completeness remarks
                    # ("season 3 is missing its finale"), which say nothing about
                    # whether the show was identified correctly — those must not
                    # hold the whole show out of the plan.
                    needs_review=not tmdb_id
                    or (bool(audited.get("manual_review_required")) and match_confidence < CONFIDENT_MATCH_THRESHOLD),
                    ai_reasoning_summary=audited.get("selected_reason") or grouped_show.get("reason"),
                    local_ai_json=grouped_show,
                    gemini_audit_json=audited,
                    # Only this show's own issues: session-wide warnings would otherwise
                    # be repeated in every show card.
                    warnings=list(audited.get("issues") or []),
                )
            )
            season_models: dict[int, TvSeason] = {}
            for season in grouped_show.get("seasons") or []:
                season_number = int(season.get("season_number") or 1)
                season_model = await self.tv.add_season(
                    TvSeason(show_id=show.id, season_number=season_number, title=f"Season {season_number:02d}")
                )
                season_models[season_number] = season_model
                for episode in season.get("episodes") or []:
                    relative_path = episode.get("file_relative_path") or ""
                    media_file = file_by_relative.get(relative_path.replace("\\", "/").lower())
                    ai_episode_number = int(episode.get("episode_number") or 0)
                    # The file name is authoritative for numbering: the AI grouping
                    # reports only the first number of a merged release (S02E01E02),
                    # silently dropping the second episode.
                    parsed = parse_episode_range(media_file.path if media_file else relative_path)
                    episode_number = parsed.episode_number if parsed else ai_episode_number
                    episode_number_end = parsed.episode_number_end if parsed else None
                    await self.tv.add_episode(
                        TvEpisode(
                            show_id=show.id,
                            season_id=season_model.id,
                            source_file_id=media_file.id if media_file else None,
                            season_number=season_number,
                            episode_number=episode_number,
                            episode_number_end=episode_number_end,
                            title=episode.get("episode_title"),
                            source_path=media_file.path if media_file else relative_path,
                            confidence=episode.get("confidence"),
                            needs_review=media_file is None or episode_number <= 0,
                            issue=None if media_file else "Исходный файл не найден в сессии сканирования.",
                            match_source="local_llm_grouping",
                        )
                    )
            saved.append(show)
        await self.session.flush()
        for show in saved:
            if show.tmdb_id:
                await self._enrich_episodes_from_tmdb(show)
        await self.session.flush()
        return saved

    async def _files_by_relative(self, scan_session_id: int, context: TvFolderContext) -> dict[str, Any]:
        root = Path(context.root_path)
        mapping = {}
        for media_file in await self.media_files.list_by_kind(scan_session_id, MediaFileKind.VIDEO):
            try:
                relative = Path(media_file.path).resolve().relative_to(root.resolve())
            except ValueError:
                relative = Path(media_file.file_name)
            mapping[str(relative).replace("\\", "/").lower()] = media_file
        return mapping

    async def _enrich_episodes_from_tmdb(self, show: TvShow) -> None:
        if not show.tmdb_id:
            return
        try:
            client = await self._ensure_tmdb_client()
        except TmdbApiKeyMissingError:
            return
        seasons = await self.tv.list_seasons(show.id)
        for season in seasons:
            try:
                details = await fetch_localized_tv_season_details(
                    client,
                    tmdb_id=show.tmdb_id,
                    season_number=season.season_number,
                )
            except Exception:
                continue
            season.tmdb_season_id = details.tmdb_season_id
            season.title = details.title or season.title
            season.episode_count = len(details.episodes)
            season.poster_path = details.poster_path
            season.poster_url = details.poster_url
            by_number = {episode.episode_number: episode for episode in details.episodes}
            for episode in await self.tv.list_episodes(show.id):
                if episode.season_number != season.season_number:
                    continue
                tmdb_episode = by_number.get(episode.episode_number)
                if tmdb_episode is None:
                    # Release numbering often runs ahead of TMDB when a season has a
                    # merged double episode. The file is still valid and must not
                    # block planning — record it as information only.
                    episode.warning = (
                        f"В TMDB у сезона {season.season_number} нет серии "
                        f"{episode.episode_number} — файл будет разложен по номеру из имени."
                    )
                    continue
                episode.warning = None
                episode.tmdb_episode_id = tmdb_episode.tmdb_episode_id
                episode.title = episode.title or tmdb_episode.title
                episode.overview = tmdb_episode.overview
                episode.air_date = tmdb_episode.air_date
                if episode.episode_number_end:
                    paired = by_number.get(episode.episode_number_end)
                    if paired and paired.title and episode.title:
                        episode.title = f"{episode.title} / {paired.title}"

    async def _apply_show_details(self, show: TvShow, details: TmdbDetailsResult, source: str) -> None:
        show.tmdb_id = details.tmdb_id
        show.title = details.title or show.title
        show.original_title = details.original_title
        show.year = details.year or show.year
        show.overview = details.overview
        show.poster_path = details.poster_path
        show.poster_url = tmdb_image_url(details.poster_path)
        show.backdrop_path = details.backdrop_path
        show.backdrop_url = tmdb_image_url(details.backdrop_path, "w780")
        show.imdb_id = details.external_ids.imdb_id
        show.tvdb_id = details.external_ids.tvdb_id
        show.wikidata_id = details.external_ids.wikidata_id
        show.language = details.metadata_language
        show.match_source = source
        show.confidence = 1.0

    async def _ensure_tmdb_client(self) -> TmdbClientProtocol:
        if self.tmdb_client is not None:
            return self.tmdb_client
        api_key = get_settings().tmdb_api_key
        if not api_key:
            app_settings = await self.settings.get_or_create()
            api_key = app_settings.tmdb_api_key
        if not api_key:
            raise TmdbApiKeyMissingError("TMDB_API_KEY is not configured")
        self.tmdb_client = TmdbClient(api_key)
        return self.tmdb_client


def _pick_tv_result(results: list[TmdbSearchResult]) -> TmdbSearchResult:
    for result in results:
        if result.media_type == "tv":
            return result
    if not results:
        raise LookupError("Сериал не найден в TMDB.")
    return results[0]
