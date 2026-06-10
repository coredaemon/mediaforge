from backend.app.models.enums import MediaType
from backend.app.utils.media_name_parser import parse_media_filename


def test_parse_simple_movie_with_year() -> None:
    result = parse_media_filename("Matrix.1999.mkv")

    assert result.media_type == MediaType.MOVIE
    assert result.title == "Matrix"
    assert result.year == 1999


def test_parse_movie_removes_technical_tokens() -> None:
    result = parse_media_filename("The.Matrix.1999.1080p.BluRay.x264.mkv")

    assert result.media_type == MediaType.MOVIE
    assert result.title == "The Matrix"
    assert result.year == 1999


def test_parse_movie_with_parenthesized_year() -> None:
    result = parse_media_filename("The Matrix (1999).mkv")

    assert result.media_type == MediaType.MOVIE
    assert result.title == "The Matrix"
    assert result.year == 1999


def test_parse_unicode_movie_with_parenthesized_year() -> None:
    result = parse_media_filename("Реальные упыри (2014).mkv")

    assert result.media_type == MediaType.MOVIE
    assert result.title == "Реальные упыри"
    assert result.year == 2014


def test_parse_sxxexx_episode() -> None:
    result = parse_media_filename("Hannibal.S01E01.mkv")

    assert result.media_type == MediaType.TV_EPISODE
    assert result.title == "Hannibal"
    assert result.season_number == 1
    assert result.episode_number == 1


def test_parse_sxxexx_episode_removes_trailing_technical_tokens() -> None:
    result = parse_media_filename("Hannibal.S01E03.1080p.BluRay.mkv")

    assert result.media_type == MediaType.TV_EPISODE
    assert result.title == "Hannibal"
    assert result.season_number == 1
    assert result.episode_number == 3


def test_parse_one_x_two_episode() -> None:
    result = parse_media_filename("Desperate.Housewives.1x02.mkv")

    assert result.media_type == MediaType.TV_EPISODE
    assert result.title == "Desperate Housewives"
    assert result.season_number == 1
    assert result.episode_number == 2


def test_parse_dash_separated_episode() -> None:
    result = parse_media_filename("Show Name - S03E07 - Episode Title.mkv")

    assert result.media_type == MediaType.TV_EPISODE
    assert result.title == "Show Name"
    assert result.season_number == 3
    assert result.episode_number == 7


def test_parse_unknown_does_not_raise() -> None:
    result = parse_media_filename("weird_file_without_clear_pattern.mkv")

    assert result.media_type == MediaType.UNKNOWN
    assert result.needs_review
    assert result.confidence < 0.7
