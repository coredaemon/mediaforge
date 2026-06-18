from backend.app.schemas.tv import TvFolderContext, TvFolderFileHint
from backend.app.services.tv_ai import normalize_tv_audit, normalize_tv_grouping


def _context() -> TvFolderContext:
    return TvFolderContext(
        root_path="D:/source",
        folders=["Тестовый сериал", "Тестовый сериал/Сезон 1"],
        files=[
            TvFolderFileHint(
                relative_path="Тестовый сериал/Сезон 1/Тестовый сериал S01E01.mkv",
                file_name="Тестовый сериал S01E01.mkv",
                kind="VIDEO",
                season_number=1,
                episode_number=1,
                possible_title="Тестовый сериал",
            )
        ],
        possible_show_titles=["Тестовый сериал"],
    )


def test_normalize_tv_grouping_extracts_markdown_json() -> None:
    raw = """
    model notes before JSON
    ```json
    {
      "shows": {
        "local_group_id": "show-1",
        "probable_title": "Тестовый сериал",
        "confidence": "90%",
        "tmdb_queries": {"title": "Тестовый сериал", "year": "2024"},
        "seasons": {
          "season_number": "1",
          "episodes": {
            "episode_number": "1",
            "file_relative_path": "Тестовый сериал/Сезон 1/Тестовый сериал S01E01.mkv"
          }
        }
      }
    }
    ```
    trailing notes
    """

    result = normalize_tv_grouping(raw, _context())
    show = result["shows"][0]

    assert show["confidence"] == 0.9
    assert show["tmdb_queries"] == ["Тестовый сериал 2024"]
    assert show["seasons"][0]["season_number"] == 1
    assert show["seasons"][0]["episodes"][0]["episode_number"] == 1


def test_normalize_tv_grouping_malformed_output_falls_back_to_context() -> None:
    result = normalize_tv_grouping("not json { broken", _context())

    assert result["shows"][0]["probable_title"] == "Тестовый сериал"
    assert result["shows"][0]["seasons"][0]["episodes"][0]["episode_number"] == 1


def test_normalize_tv_audit_extracts_corrections_and_manual_review() -> None:
    grouping = {
        "shows": [
            {
                "local_group_id": "show-1",
                "probable_title": "Wrong",
                "confidence": 0.6,
                "seasons": [],
                "uncertain_files": [],
            }
        ]
    }
    raw = 'prefix {"shows":[{"local_group_id":"show-1","approved":false,"corrected_title":"Correct","corrected_year":"2024","selected_tmdb_id":"123","confidence":94,"manual_review_required":true,"issues":["check episode 2"]}]} suffix'

    result = normalize_tv_audit(raw, grouping)
    show = result["shows"][0]

    assert show["corrected_title"] == "Correct"
    assert show["corrected_year"] == 2024
    assert show["selected_tmdb_id"] == 123
    assert show["confidence"] == 0.94
    assert show["manual_review_required"] is True
    assert show["issues"] == ["check episode 2"]
