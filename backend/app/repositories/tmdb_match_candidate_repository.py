from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tmdb_match_candidate import TmdbMatchCandidate


class TmdbMatchCandidateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, candidate: TmdbMatchCandidate) -> TmdbMatchCandidate:
        self.session.add(candidate)
        await self.session.flush()
        return candidate

    async def list_by_media_item(self, media_item_id: int) -> Sequence[TmdbMatchCandidate]:
        result = await self.session.execute(
            select(TmdbMatchCandidate)
            .where(TmdbMatchCandidate.media_item_id == media_item_id)
            .order_by(TmdbMatchCandidate.score.desc(), TmdbMatchCandidate.id.asc())
        )
        return result.scalars().all()

    async def delete_for_media_item(self, media_item_id: int) -> None:
        await self.session.execute(
            delete(TmdbMatchCandidate).where(TmdbMatchCandidate.media_item_id == media_item_id)
        )
