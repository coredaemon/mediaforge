from backend.app.services.tv_hints import parse_tv_file_hint


def test_tv_hint_sxxexx() -> None:
    hint = parse_tv_file_hint("Show.Name.S01E02.1080p.WEB-DL.mkv")

    assert hint.season_number == 1
    assert hint.episode_number == 2
    assert hint.possible_title == "Show Name"


def test_tv_hint_one_x_two() -> None:
    hint = parse_tv_file_hint("Show.Name.1x03.mkv")

    assert hint.season_number == 1
    assert hint.episode_number == 3


def test_tv_hint_russian_words() -> None:
    hint = parse_tv_file_hint("Тестовый сериал 1 сезон 2 серия.mkv")

    assert hint.season_number == 1
    assert hint.episode_number == 2
    assert hint.possible_title == "Тестовый сериал"


def test_tv_hint_numeric_episode_from_season_folder() -> None:
    hint = parse_tv_file_hint("02.mkv", ["Тестовый сериал", "Сезон 1"])

    assert hint.season_number == 1
    assert hint.episode_number == 2
    assert hint.possible_title == "Тестовый сериал"
