from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

_IMDB_RE = re.compile(r"^tt\d{7,8}$", re.IGNORECASE)


@dataclass
class NfoParseResult:
    title: str | None = None
    original_title: str | None = None
    year: int | None = None
    plot: str | None = None
    outline: str | None = None
    sorttitle: str | None = None
    premiered: str | None = None
    release_date: str | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None
    wikidata_id: str | None = None
    media_type_hint: str | None = None
    warnings: list[str] = field(default_factory=list)
    ok: bool = False


def parse_nfo_file(path: str | Path) -> NfoParseResult:
    result = NfoParseResult()
    file_path = Path(path)
    if not file_path.exists():
        result.warnings.append("NFO file not found")
        return result
    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        result.warnings.append(f"Could not read NFO: {exc}")
        return result

    text = _decode_nfo_bytes(raw)
    if not text.strip():
        result.warnings.append("NFO file is empty")
        return result

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        try:
            wrapped = f"<root>{text}</root>"
            root = ET.fromstring(wrapped)
            result.warnings.append("NFO XML repaired with wrapper")
        except ET.ParseError as exc:
            result.warnings.append(f"NFO XML parse failed: {exc}")
            return result

    _populate_from_root(root, result)
    result.ok = any(
        (
            result.title,
            result.tmdb_id,
            result.imdb_id,
            result.tvdb_id,
            result.year,
            result.plot,
            result.outline,
        )
    )
    return result


def _decode_nfo_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _populate_from_root(root: ET.Element, result: NfoParseResult) -> None:
    tag_name = _local_tag(root.tag).lower()
    if tag_name in {"movie", "tvshow", "episodedetails"}:
        result.media_type_hint = tag_name

    for element in root.iter():
        tag = _local_tag(element.tag).lower()
        text = (element.text or "").strip()
        if not text and tag != "uniqueid":
            attrs = element.attrib
            if tag == "uniqueid":
                _apply_uniqueid(attrs, text, result)
            continue

        if tag == "uniqueid":
            _apply_uniqueid(element.attrib, text, result)
            continue
        if tag == "title":
            result.title = result.title or text
        elif tag == "originaltitle":
            result.original_title = text
        elif tag == "sorttitle":
            result.sorttitle = text
        elif tag in {"year", "releaseyear"}:
            result.year = result.year or _parse_year(text)
        elif tag in {"plot", "description"}:
            result.plot = result.plot or text
        elif tag == "outline":
            result.outline = text
        elif tag in {"premiered", "releasedate", "releasedate"}:
            if tag == "premiered":
                result.premiered = text
            else:
                result.release_date = text
            result.year = result.year or _parse_year(text[:4] if len(text) >= 4 else text)
        elif tag == "id" and _looks_like_imdb(text):
            result.imdb_id = result.imdb_id or _normalize_imdb(text)
        elif tag in {"imdbid", "imdb_id", "imdb"}:
            result.imdb_id = result.imdb_id or _normalize_imdb(text)
        elif tag in {"tmdbid", "tmdb_id", "tmdb"}:
            result.tmdb_id = result.tmdb_id or _parse_int(text)
        elif tag in {"tvdbid", "tvdb_id", "tvdb"}:
            result.tvdb_id = result.tvdb_id or _parse_int(text)


def _apply_uniqueid(attrs: dict[str, str], text: str, result: NfoParseResult) -> None:
    source = (attrs.get("type") or attrs.get("default") or "").strip().lower()
    value = text or attrs.get("id") or ""
    value = value.strip()
    if not value:
        return
    if source in {"tmdb", "themoviedb"}:
        result.tmdb_id = result.tmdb_id or _parse_int(value)
    elif source == "imdb":
        result.imdb_id = result.imdb_id or _normalize_imdb(value)
    elif source == "tvdb":
        result.tvdb_id = result.tvdb_id or _parse_int(value)
    elif source == "wikidata":
        result.wikidata_id = result.wikidata_id or value
    elif _looks_like_imdb(value):
        result.imdb_id = result.imdb_id or _normalize_imdb(value)
    elif value.isdigit():
        if source == "tvdb":
            result.tvdb_id = result.tvdb_id or int(value)
        elif source in {"tmdb", "themoviedb"}:
            result.tmdb_id = result.tmdb_id or int(value)


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _parse_year(value: str) -> int | None:
    match = re.search(r"(19|20)\d{2}", value)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _parse_int(value: str) -> int | None:
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _looks_like_imdb(value: str) -> bool:
    return bool(_IMDB_RE.match(value.strip()))


def _normalize_imdb(value: str) -> str:
    value = value.strip().lower()
    if value.startswith("tt"):
        return value
    digits = re.sub(r"\D", "", value)
    if digits:
        return f"tt{digits}"
    return value
