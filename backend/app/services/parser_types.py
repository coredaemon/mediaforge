from dataclasses import dataclass

from ..models.enums import MediaType


@dataclass(frozen=True)
class ParsedMediaCandidate:
    title: str | None
    original_name: str
    media_type: MediaType
    year: int | None
    season_number: int | None
    episode_number: int | None
    confidence: float
    needs_review: bool
