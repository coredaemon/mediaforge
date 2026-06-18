from __future__ import annotations

import json
import re
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tv_grouping_run import TvGroupingRun
from ..schemas.tv import TvFolderContext
from ..utils.ai_response_normalization import normalize_confidence, normalize_tmdb_queries


class TvAiGroupingService:
    def __init__(self, session: AsyncSession, local_client: object | None = None) -> None:
        self.session = session
        self.local_client = local_client

    async def group(self, scan_session_id: int, context: TvFolderContext) -> dict[str, Any]:
        started = time.perf_counter()
        status = "success"
        error = None
        try:
            if self.local_client is not None and hasattr(self.local_client, "group_tv"):
                raw = await self.local_client.group_tv(context.model_dump())
            else:
                raw = _deterministic_grouping(context)
            normalized = normalize_tv_grouping(raw, context)
            output = normalized
        except Exception as exc:
            status = "failed"
            error = str(exc)
            output = _deterministic_grouping(context)
        run = TvGroupingRun(
            scan_session_id=scan_session_id,
            provider="local",
            model=getattr(self.local_client, "model", None),
            status=status,
            duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
            input_json=context.model_dump(),
            output_json=output,
            error=error,
        )
        self.session.add(run)
        await self.session.flush()
        return output


class TvCloudAuditService:
    def __init__(self, session: AsyncSession, gemini_client: object | None = None) -> None:
        self.session = session
        self.gemini_client = gemini_client

    async def audit(
        self,
        scan_session_id: int,
        context: TvFolderContext,
        grouping: dict[str, Any],
        tmdb_data: dict[str, Any],
    ) -> dict[str, Any]:
        started = time.perf_counter()
        status = "success"
        error = None
        try:
            if self.gemini_client is not None and hasattr(self.gemini_client, "audit_tv"):
                raw = await self.gemini_client.audit_tv(context.model_dump(), grouping, tmdb_data)
            else:
                raw = _identity_audit(grouping)
            output = normalize_tv_audit(raw, grouping)
        except Exception as exc:
            status = "failed"
            error = str(exc)
            output = _identity_audit(grouping)
        self.session.add(
            TvGroupingRun(
                scan_session_id=scan_session_id,
                provider="gemini",
                model=getattr(self.gemini_client, "model", None),
                status=status,
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                input_json={"context": context.model_dump(), "grouping": grouping, "tmdb_data": tmdb_data},
                output_json=output,
                error=error,
            )
        )
        await self.session.flush()
        return output


def normalize_tv_grouping(value: Any, context: TvFolderContext) -> dict[str, Any]:
    value = _coerce_json_object(value)
    if not isinstance(value, dict):
        return _deterministic_grouping(context)
    shows = value.get("shows")
    if isinstance(shows, dict):
        shows = [shows]
    if not isinstance(shows, list):
        shows = []
    normalized = [_normalize_show(show, index) for index, show in enumerate(shows) if isinstance(show, dict)]
    return {"shows": normalized, "warnings": _string_list(value.get("warnings"))}


def normalize_tv_audit(value: Any, grouping: dict[str, Any]) -> dict[str, Any]:
    value = _coerce_json_object(value)
    if not isinstance(value, dict):
        return _identity_audit(grouping)
    shows = value.get("shows")
    if isinstance(shows, dict):
        shows = [shows]
    if not isinstance(shows, list):
        shows = []
    return {"shows": [_normalize_audit_show(show) for show in shows if isinstance(show, dict)], "global_warnings": _string_list(value.get("global_warnings"))}


def _normalize_show(show: dict[str, Any], index: int) -> dict[str, Any]:
    confidence = normalize_confidence(show.get("confidence"))
    queries, _ = normalize_tmdb_queries(
        show.get("tmdb_queries"),
        clean_title=_text(show.get("probable_title")) or _text(show.get("title")),
        year=_int(show.get("year")),
        parser_title=None,
    )
    seasons = show.get("seasons")
    if isinstance(seasons, dict):
        seasons = [seasons]
    return {
        "local_group_id": _text(show.get("local_group_id")) or f"show-{index + 1}",
        "probable_title": _text(show.get("probable_title")) or _text(show.get("title")) or "Unknown Show",
        "original_title": _text(show.get("original_title")),
        "language": _text(show.get("language")) or "ru",
        "year": _int(show.get("year")),
        "confidence": confidence if confidence is not None else 0.5,
        "reason": _text(show.get("reason")),
        "tmdb_queries": queries,
        "external_ids": show.get("external_ids") if isinstance(show.get("external_ids"), dict) else {},
        "seasons": [_normalize_grouping_season(season) for season in seasons or [] if isinstance(season, dict)],
        "uncertain_files": show.get("uncertain_files") if isinstance(show.get("uncertain_files"), list) else [],
    }


def _normalize_grouping_season(season: dict[str, Any]) -> dict[str, Any]:
    episodes = season.get("episodes")
    if isinstance(episodes, dict):
        episodes = [episodes]
    return {
        "season_number": _int(season.get("season_number")) or 1,
        "confidence": normalize_confidence(season.get("confidence")) or 0.5,
        "episodes": [_normalize_grouping_episode(ep) for ep in episodes or [] if isinstance(ep, dict)],
    }


def _normalize_grouping_episode(ep: dict[str, Any]) -> dict[str, Any]:
    return {
        "episode_number": _int(ep.get("episode_number")) or 0,
        "file_relative_path": _text(ep.get("file_relative_path")) or "",
        "episode_title": _text(ep.get("episode_title")),
        "confidence": normalize_confidence(ep.get("confidence")) or 0.5,
        "reason": _text(ep.get("reason")),
    }


def _normalize_audit_show(show: dict[str, Any]) -> dict[str, Any]:
    return {
        "local_group_id": _text(show.get("local_group_id")),
        "approved": bool(show.get("approved", False)),
        "corrected_title": _text(show.get("corrected_title")),
        "corrected_year": _int(show.get("corrected_year")),
        "selected_tmdb_id": _int(show.get("selected_tmdb_id")),
        "selected_reason": _text(show.get("selected_reason")),
        "confidence": normalize_confidence(show.get("confidence")) or 0.5,
        "seasons": show.get("seasons") if isinstance(show.get("seasons"), list) else [],
        "issues": _string_list(show.get("issues")),
        "manual_review_required": bool(show.get("manual_review_required", False)),
    }


def _coerce_json_object(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(?P<body>.*?)```", text, re.I | re.S)
    if fenced:
        text = fenced.group("body").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _deterministic_grouping(context: TvFolderContext) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    uncertain: list[dict[str, str]] = []
    for file in context.files:
        if file.kind != "VIDEO":
            continue
        title = file.possible_title or (context.possible_show_titles[0] if context.possible_show_titles else "Unknown Show")
        group = grouped.setdefault(
            title.lower(),
            {
                "local_group_id": f"show-{len(grouped) + 1}",
                "probable_title": title,
                "original_title": None,
                "language": "ru" if _has_cyrillic(title) else "en",
                "year": None,
                "confidence": 0.72,
                "reason": "Deterministic TV hints grouped files by folder/title.",
                "tmdb_queries": [title],
                "external_ids": _first_sidecar_ids(context),
                "seasons": [],
                "uncertain_files": [],
            },
        )
        if file.season_number is None or file.episode_number is None:
            uncertain.append({"file_relative_path": file.relative_path, "reason": "No season/episode number detected"})
            continue
        season = _season_bucket(group, file.season_number)
        season["episodes"].append(
            {
                "episode_number": file.episode_number,
                "file_relative_path": file.relative_path,
                "episode_title": None,
                "confidence": 0.85,
                "reason": "Deterministic TV filename/folder hint.",
            }
        )
    for group in grouped.values():
        group["uncertain_files"].extend(uncertain)
    return {"shows": list(grouped.values()), "warnings": context.warnings}


def _identity_audit(grouping: dict[str, Any]) -> dict[str, Any]:
    shows = []
    for show in grouping.get("shows", []):
        shows.append(
            {
                "local_group_id": show.get("local_group_id"),
                "approved": not show.get("uncertain_files"),
                "corrected_title": show.get("probable_title"),
                "corrected_year": show.get("year"),
                "selected_tmdb_id": None,
                "selected_reason": "Cloud audit unavailable; local grouping retained.",
                "confidence": show.get("confidence") or 0.5,
                "seasons": show.get("seasons") or [],
                "issues": [item.get("reason", "Uncertain file") for item in show.get("uncertain_files", []) if isinstance(item, dict)],
                "manual_review_required": bool(show.get("uncertain_files")),
            }
        )
    return {"shows": shows, "global_warnings": []}


def _season_bucket(group: dict[str, Any], season_number: int) -> dict[str, Any]:
    for season in group["seasons"]:
        if season["season_number"] == season_number:
            return season
    season = {"season_number": season_number, "confidence": 0.85, "episodes": []}
    group["seasons"].append(season)
    return season


def _first_sidecar_ids(context: TvFolderContext) -> dict[str, Any]:
    for file in context.files:
        if file.sidecar_ids and any(file.sidecar_ids.get(key) for key in ("tmdb_id", "imdb_id", "tvdb_id")):
            return file.sidecar_ids
    return {}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value]
    return [str(value)]


def _has_cyrillic(text: str) -> bool:
    return any("\u0400" <= ch <= "\u04FF" for ch in text)
