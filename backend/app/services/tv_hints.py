from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..utils.media_name_parser import clean_title

TV_JUNK_TOKENS = {
    "1080p",
    "720p",
    "2160p",
    "web-dl",
    "webdl",
    "webrip",
    "bluray",
    "bdrip",
    "amzn",
    "nf",
    "new-team",
    "lostfilm",
    "jaskier",
    "x264",
    "x265",
    "hevc",
}

SXXEXX = re.compile(r"(?P<prefix>.*?)[\s._-]*[Ss](?P<season>\d{1,2})[Ee](?P<episode>\d{1,3})(?P<suffix>.*)")
ONE_X_TWO = re.compile(r"(?P<prefix>.*?)[\s._-]*(?P<season>\d{1,2})x(?P<episode>\d{1,3})(?P<suffix>.*)", re.I)
EN_WORDS = re.compile(
    r"(?P<prefix>.*?)(?:season|s)\s*(?P<season>\d{1,2})[\s._-]*(?:episode|ep|e)\.?\s*(?P<episode>\d{1,3})(?P<suffix>.*)",
    re.I,
)
RU_WORDS = re.compile(
    r"(?P<prefix>.*?)(?:(?P<season>\d{1,2})\s*сезон\s*(?P<episode>\d{1,3})\s*сер(?:ия|ии|ию|\.?)|сезон\s*(?P<season2>\d{1,2})\s*сер(?:ия|ии|ию|\.?)\s*(?P<episode2>\d{1,3}))(?P<suffix>.*)",
    re.I,
)
EP_ONLY = re.compile(r"(?P<prefix>.*?)(?:^|[\s._-])(?:episode|ep\.?|e|сер(?:ия|ии|ию|\.?))\s*(?P<episode>\d{1,3})(?P<suffix>.*)", re.I)
SEASON_FOLDER = re.compile(r"(?:season|сезон|s)\s*(?P<season>\d{1,2})", re.I)


@dataclass
class TvFileHint:
    season_number: int | None = None
    episode_number: int | None = None
    possible_title: str | None = None
    possible_episode_title: str | None = None
    junk_tokens: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reason: str | None = None


def parse_tv_file_hint(file_name: str, parent_names: list[str] | None = None) -> TvFileHint:
    stem = Path(file_name).stem
    parent_names = parent_names or []
    for pattern, reason in (
        (SXXEXX, "Filename contains SxxExx"),
        (ONE_X_TWO, "Filename contains 1x02"),
        (EN_WORDS, "Filename contains English season/episode words"),
        (RU_WORDS, "Filename contains Russian season/episode words"),
    ):
        match = pattern.search(stem)
        if not match:
            continue
        season = match.groupdict().get("season") or match.groupdict().get("season2")
        episode = match.groupdict().get("episode") or match.groupdict().get("episode2")
        prefix = match.groupdict().get("prefix") or ""
        suffix = match.groupdict().get("suffix") or ""
        title = _possible_show_title(prefix, parent_names)
        return TvFileHint(
            season_number=int(season),
            episode_number=int(episode),
            possible_title=title,
            possible_episode_title=_possible_episode_title(suffix),
            junk_tokens=_junk_tokens(stem),
            confidence=0.95 if title else 0.8,
            reason=reason,
        )

    episode_only = EP_ONLY.search(stem)
    season = _season_from_parents(parent_names)
    if episode_only and season is not None:
        prefix = episode_only.groupdict().get("prefix") or ""
        return TvFileHint(
            season_number=season,
            episode_number=int(episode_only.group("episode")),
            possible_title=_possible_show_title(prefix, parent_names),
            junk_tokens=_junk_tokens(stem),
            confidence=0.72,
            reason="Episode number plus season folder",
        )

    if stem.strip().isdigit() and season is not None:
        return TvFileHint(
            season_number=season,
            episode_number=int(stem.strip()),
            possible_title=_possible_show_title("", parent_names),
            confidence=0.7,
            reason="Numeric episode file in season folder",
        )

    return TvFileHint(
        possible_title=_possible_show_title(stem, parent_names),
        junk_tokens=_junk_tokens(stem),
        confidence=0.25,
        reason="No reliable episode pattern",
    )


def _season_from_parents(parent_names: list[str]) -> int | None:
    for name in reversed(parent_names):
        match = SEASON_FOLDER.search(name)
        if match:
            return int(match.group("season"))
    return None


def _possible_show_title(prefix: str, parent_names: list[str]) -> str | None:
    cleaned = clean_title(prefix, remove_tokens=TV_JUNK_TOKENS)
    if cleaned:
        return cleaned
    for name in reversed(parent_names):
        if SEASON_FOLDER.search(name):
            continue
        cleaned_parent = clean_title(name, remove_tokens=TV_JUNK_TOKENS)
        if cleaned_parent:
            return cleaned_parent
    return None


def _possible_episode_title(suffix: str) -> str | None:
    cleaned = clean_title(suffix, remove_tokens=TV_JUNK_TOKENS)
    return cleaned or None


def _junk_tokens(value: str) -> list[str]:
    lower = value.lower()
    return sorted(token for token in TV_JUNK_TOKENS if token in lower)
