from xml.sax.saxutils import escape

from ..models.media_item import MediaItem


def build_movie_nfo(item: MediaItem) -> str:
    title = item.localized_title or item.matched_title or item.parsed_title or ""
    original_title = item.tmdb_original_title or title
    year = item.matched_year or item.year
    plot = item.localized_overview or ""

    lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "<movie>"]
    if title:
        lines.append(f"  <title>{escape(title)}</title>")
    if original_title:
        lines.append(f"  <originaltitle>{escape(original_title)}</originaltitle>")
    if year:
        lines.append(f"  <year>{year}</year>")
    if plot:
        lines.append(f"  <plot>{escape(plot)}</plot>")
    if item.tmdb_id:
        lines.append(f'  <uniqueid type="tmdb" default="true">{item.tmdb_id}</uniqueid>')
    if item.imdb_id:
        lines.append(f'  <uniqueid type="imdb">{escape(item.imdb_id)}</uniqueid>')
    if item.tvdb_id:
        lines.append(f'  <uniqueid type="tvdb">{item.tvdb_id}</uniqueid>')
    lines.append("</movie>")
    return "\n".join(lines) + "\n"
