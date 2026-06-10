from sqlalchemy.ext.asyncio import AsyncSession


class OperationPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
