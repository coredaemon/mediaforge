import re
from pathlib import Path

from ..models.enums import MediaType
from ..services.parser_types import ParsedMediaCandidate

TECHNICAL_TOKENS = {
    "1080p",
    "720p",
    "2160p",
    "4k",
    "bluray",
    "brrip",
    "bdrip",
    "web-dl",
    "webdl",
    "webrip",
    "hdrip",
    "dvdrip",
    "x264",
    "x265",
    "hevc",
    "h264",
    "h265",
    "aac",
    "dts",
    "rarbg",
    "yify",
}

SXXEXX_PATTERN = re.compile(r"(?P<prefix>.*?)[\s._-]*[Ss](?P<season>\d{1,2})[Ee](?P<episode>\d{1,3})")
ONE_X_TWO_PATTERN = re.compile(r"(?P<prefix>.*?)[\s._-]*(?P<season>\d{1,2})x(?P<episode>\d{1,3})", re.IGNORECASE)
PAREN_YEAR_PATTERN = re.compile(r"(?P<title>.+?)\s*\((?P<year>19\d{2}|20\d{2})\)")
TOKEN_YEAR_PATTERN = re.compile(r"(?P<title>.+?)[\s._-]+(?P<year>19\d{2}|20\d{2})(?:[\s._-]|$)")


def parse_media_filename(path: str | Path, remove_tokens: set[str] | None = None) -> ParsedMediaCandidate:
    original_name = Path(path).name
    stem = Path(path).stem

    episode_match = SXXEXX_PATTERN.search(stem) or ONE_X_TWO_PATTERN.search(stem)
    if episode_match:
        title = clean_title(episode_match.group("prefix"), remove_tokens=remove_tokens)
        return ParsedMediaCandidate(
            title=title,
            original_name=original_name,
            media_type=MediaType.TV_EPISODE,
            year=None,
            season_number=int(episode_match.group("season")),
            episode_number=int(episode_match.group("episode")),
            confidence=0.95 if title else 0.65,
            needs_review=not bool(title),
        )

    movie_match = PAREN_YEAR_PATTERN.search(stem) or TOKEN_YEAR_PATTERN.search(stem)
    if movie_match:
        title = clean_title(movie_match.group("title"), remove_tokens=remove_tokens)
        return ParsedMediaCandidate(
            title=title,
            original_name=original_name,
            media_type=MediaType.MOVIE,
            year=int(movie_match.group("year")),
            season_number=None,
            episode_number=None,
            confidence=0.9 if title else 0.6,
            needs_review=not bool(title),
        )

    title = clean_title(stem, remove_tokens=remove_tokens)
    return ParsedMediaCandidate(
        title=title or None,
        original_name=original_name,
        media_type=MediaType.UNKNOWN,
        year=None,
        season_number=None,
        episode_number=None,
        confidence=0.2,
        needs_review=True,
    )


def clean_title(value: str, remove_tokens: set[str] | None = None) -> str:
    normalized = value.replace("_", " ").replace(".", " ").replace("-", " ")
    ignored_tokens = TECHNICAL_TOKENS | {token.lower() for token in (remove_tokens or set())}
    words = [word for word in normalized.split() if word.lower() not in ignored_tokens]
    return " ".join(words).strip()
