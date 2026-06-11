from pathlib import Path

from backend.app.utils.target_paths import (
    build_movie_folder_path,
    build_movie_video_path,
    build_tv_video_path,
    sanitize_path_segment,
)


def test_build_movie_target_video_path() -> None:
    target_root = Path("/library")

    video_path = build_movie_video_path(target_root, "The Matrix", 1999, ".mkv")

    assert video_path.as_posix() == "/library/The Matrix (1999)/The Matrix (1999).mkv"


def test_build_movie_target_paths_without_movies_subfolder() -> None:
    target_root = Path("/library")
    folder = build_movie_folder_path(target_root, "The Matrix", 1999)

    assert folder.as_posix() == "/library/The Matrix (1999)"
    assert (folder / "movie.nfo").as_posix() == "/library/The Matrix (1999)/movie.nfo"
    assert (folder / "poster.jpg").as_posix() == "/library/The Matrix (1999)/poster.jpg"
    assert (folder / "fanart.jpg").as_posix() == "/library/The Matrix (1999)/fanart.jpg"


def test_build_movie_target_path_with_cyrillic_title() -> None:
    target_root = Path("D:/Фильмы")
    video_path = build_movie_video_path(target_root, "Безрассудный", 2026, ".mkv")

    assert video_path.as_posix() == "D:/Фильмы/Безрассудный (2026)/Безрассудный (2026).mkv"


def test_build_tv_episode_target_video_path() -> None:
    target_root = Path("/library")

    video_path = build_tv_video_path(target_root, "Hannibal", 1, 3, ".mkv")

    assert video_path.as_posix() == "/library/TV Shows/Hannibal/Season 01/Hannibal S01E03.mkv"


def test_sanitize_path_segment_removes_invalid_windows_characters() -> None:
    assert sanitize_path_segment("Bad: Movie*Name?") == "Bad_ Movie_Name_"


def test_sanitize_path_segment_preserves_cyrillic_titles() -> None:
    assert sanitize_path_segment("Матрица") == "Матрица"
