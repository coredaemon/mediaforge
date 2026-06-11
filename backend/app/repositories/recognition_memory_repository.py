import json
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.recognition_memory import RecognitionCorrection, RecognitionTokenRule


class RecognitionMemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_correction(self, correction: RecognitionCorrection) -> RecognitionCorrection:
        self.session.add(correction)
        await self.session.flush()
        return correction

    async def list_corrections(self) -> Sequence[RecognitionCorrection]:
        result = await self.session.execute(
            select(RecognitionCorrection).order_by(RecognitionCorrection.created_at.desc(), RecognitionCorrection.id.desc())
        )
        return result.scalars().all()

    async def list_token_rules(self) -> Sequence[RecognitionTokenRule]:
        result = await self.session.execute(
            select(RecognitionTokenRule).order_by(RecognitionTokenRule.hit_count.desc(), RecognitionTokenRule.token.asc())
        )
        return result.scalars().all()

    async def list_remove_tokens(self) -> set[str]:
        rules = await self.list_token_rules()
        return {rule.token for rule in rules if rule.action == "remove"}

    async def upsert_remove_token(self, token: str, source: str = "manual") -> RecognitionTokenRule | None:
        normalized = _normalize_token(token)
        if not normalized:
            return None
        result = await self.session.execute(select(RecognitionTokenRule).where(RecognitionTokenRule.token == normalized))
        rule = result.scalar_one_or_none()
        if rule is None:
            rule = RecognitionTokenRule(token=normalized, action="remove", source=source, hit_count=1)
            self.session.add(rule)
        else:
            rule.hit_count += 1
        await self.session.flush()
        return rule


def dump_tokens(tokens: list[str]) -> str:
    return json.dumps([_normalize_token(token) for token in tokens if _normalize_token(token)])


def load_tokens(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(token) for token in data if str(token).strip()]


def _normalize_token(token: str) -> str:
    return token.strip().lower()
