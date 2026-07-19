from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.tv_episode import TvEpisode
from ..models.tv_grouping_run import TvGroupingRun
from ..models.tv_season import TvSeason
from ..models.tv_show import TvShow


class TvRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def delete_for_scan_session(self, scan_session_id: int) -> None:
        show_ids = await self.session.scalars(select(TvShow.id).where(TvShow.scan_session_id == scan_session_id))
        ids = list(show_ids)
        if ids:
            await self.session.execute(delete(TvEpisode).where(TvEpisode.show_id.in_(ids)))
            await self.session.execute(delete(TvSeason).where(TvSeason.show_id.in_(ids)))
            await self.session.execute(delete(TvGroupingRun).where(TvGroupingRun.show_id.in_(ids)))
        await self.session.execute(delete(TvGroupingRun).where(TvGroupingRun.scan_session_id == scan_session_id))
        await self.session.execute(delete(TvShow).where(TvShow.scan_session_id == scan_session_id))

    async def add_show(self, show: TvShow) -> TvShow:
        self.session.add(show)
        await self.session.flush()
        return show

    async def add_season(self, season: TvSeason) -> TvSeason:
        self.session.add(season)
        await self.session.flush()
        return season

    async def add_episode(self, episode: TvEpisode) -> TvEpisode:
        self.session.add(episode)
        await self.session.flush()
        return episode

    async def add_grouping_run(self, run: TvGroupingRun) -> TvGroupingRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_show(self, show_id: int) -> TvShow | None:
        return await self.session.get(
            TvShow,
            show_id,
            options=[selectinload(TvShow.seasons).selectinload(TvSeason.episodes)],
        )

    async def list_shows(self, scan_session_id: int) -> Sequence[TvShow]:
        result = await self.session.execute(
            select(TvShow)
            .where(TvShow.scan_session_id == scan_session_id)
            .options(selectinload(TvShow.seasons).selectinload(TvSeason.episodes))
            .order_by(TvShow.id.asc())
        )
        return result.scalars().all()

    async def list_seasons(self, show_id: int) -> Sequence[TvSeason]:
        result = await self.session.execute(
            select(TvSeason)
            .where(TvSeason.show_id == show_id)
            .options(selectinload(TvSeason.episodes))
            .order_by(TvSeason.season_number.asc())
        )
        return result.scalars().all()

    async def get_episode(self, episode_id: int) -> TvEpisode | None:
        return await self.session.get(TvEpisode, episode_id)

    async def list_episodes(self, show_id: int) -> Sequence[TvEpisode]:
        result = await self.session.execute(
            select(TvEpisode)
            .where(TvEpisode.show_id == show_id)
            .order_by(TvEpisode.season_number.asc(), TvEpisode.episode_number.asc(), TvEpisode.id.asc())
        )
        return result.scalars().all()
