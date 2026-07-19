from xml.sax.saxutils import escape

from ..models.media_item import MediaItem
from ..models.tv_episode import TvEpisode
from ..models.tv_show import TvShow


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


def build_tvshow_nfo(show: TvShow) -> str:
    title = show.title
    original_title = show.original_title or title
    lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "<tvshow>"]
    if title:
        lines.append(f"  <title>{escape(title)}</title>")
    if original_title:
        lines.append(f"  <originaltitle>{escape(original_title)}</originaltitle>")
    if show.year:
        lines.append(f"  <year>{show.year}</year>")
    if show.first_air_date:
        lines.append(f"  <premiered>{escape(show.first_air_date)}</premiered>")
    if show.overview:
        lines.append(f"  <plot>{escape(show.overview)}</plot>")
    if show.tmdb_id:
        lines.append(f'  <uniqueid type="tmdb" default="true">{show.tmdb_id}</uniqueid>')
    if show.imdb_id:
        lines.append(f'  <uniqueid type="imdb">{escape(show.imdb_id)}</uniqueid>')
    if show.tvdb_id:
        lines.append(f'  <uniqueid type="tvdb">{show.tvdb_id}</uniqueid>')
    if show.wikidata_id:
        lines.append(f'  <uniqueid type="wikidata">{escape(show.wikidata_id)}</uniqueid>')
    lines.append("</tvshow>")
    return "\n".join(lines) + "\n"


def build_episode_nfo(show: TvShow, episode: TvEpisode) -> str:
    title = episode.title or f"S{episode.season_number:02d}E{episode.episode_number:02d}"
    lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "<episodedetails>"]
    lines.append(f"  <title>{escape(title)}</title>")
    lines.append(f"  <showtitle>{escape(show.title)}</showtitle>")
    lines.append(f"  <season>{episode.season_number}</season>")
    lines.append(f"  <episode>{episode.episode_number}</episode>")
    if episode.episode_number_end and episode.episode_number_end != episode.episode_number:
        # Kodi/Jellyfin read this as "this file also covers the next episode".
        lines.append(f"  <episodenumberend>{episode.episode_number_end}</episodenumberend>")
    if episode.air_date:
        lines.append(f"  <aired>{escape(episode.air_date)}</aired>")
    if episode.overview:
        lines.append(f"  <plot>{escape(episode.overview)}</plot>")
    if episode.tmdb_episode_id:
        lines.append(f'  <uniqueid type="tmdb" default="true">{episode.tmdb_episode_id}</uniqueid>')
    if show.tmdb_id:
        lines.append(f'  <uniqueid type="tmdb_show">{show.tmdb_id}</uniqueid>')
    if show.imdb_id:
        lines.append(f'  <uniqueid type="imdb">{escape(show.imdb_id)}</uniqueid>')
    if show.tvdb_id:
        lines.append(f'  <uniqueid type="tvdb">{show.tvdb_id}</uniqueid>')
    lines.append("</episodedetails>")
    return "\n".join(lines) + "\n"
