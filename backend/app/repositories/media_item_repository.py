from sqlalchemy.ext.asyncio import AsyncSession


class MediaItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
