from pathlib import Path

from backend.app.utils.paths import (
    is_sidecar_file,
    is_subtitle_file,
    is_video_file,
    normalize_path,
)


def test_normalize_path_expands_and_resolves_without_requiring_existence() -> None:
    normalized = normalize_path(Path(".") / "missing" / ".." / "library")

    assert normalized.is_absolute()
    assert normalized.name == "library"


def test_is_video_file_accepts_known_video_extensions_case_insensitively() -> None:
    assert is_video_file("Movie.MKV")
    assert is_video_file(Path("Episode.mp4"))
    assert not is_video_file("poster.jpg")


def test_is_subtitle_file_accepts_known_subtitle_extensions() -> None:
    assert is_subtitle_file("movie.en.srt")
    assert is_subtitle_file(Path("episode.VTT"))
    assert not is_subtitle_file("movie.mkv")


def test_is_sidecar_file_accepts_metadata_and_artwork_extensions() -> None:
    assert is_sidecar_file("movie.nfo")
    assert is_sidecar_file(Path("poster.JPG"))
    assert not is_sidecar_file("movie.mp4")
