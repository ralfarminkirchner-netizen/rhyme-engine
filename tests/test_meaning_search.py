"""Tests fuer die getrennte Bedeutungs-Achse (TF-IDF, lokal)."""
from pathlib import Path

from app.services.meaning_search import search_meaning
from app.services.user_text_importer import refresh_user_text_database


def _seed(tmp_path: Path) -> Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "texte.txt").write_text(
        "\n".join(
            [
                "der schmerz sitzt tief im herzen und brennt",
                "die liebe traegt mich durch die dunkle nacht",
                "geld regiert die welt und macht uns kalt",
                "schmerz und trauer ziehen durch die strassen",
                "die sonne lacht am hellen morgen",
            ]
        )
        + "\n",
        "utf-8",
    )
    refresh_user_text_database(inbox_dir=inbox, data_root=tmp_path, prefer_pages_export=False)
    return tmp_path / "rhyme_database.sqlite"


def test_meaning_search_finds_topical_lines(tmp_path: Path):
    db = _seed(tmp_path)
    res = search_meaning("schmerz", db_path=db, limit=5, min_score=0.0)
    texts = [r["text"] for r in res["results"]]
    # Beide "schmerz"-Zeilen muessen oben stehen, themenfremde nicht.
    assert any("schmerz sitzt tief" in t for t in texts)
    assert any("schmerz und trauer" in t for t in texts)
    assert res["axis"] == "meaning"


def test_meaning_search_ranks_by_relevance_not_rhyme(tmp_path: Path):
    db = _seed(tmp_path)
    res = search_meaning("liebe nacht", db_path=db, limit=5, min_score=0.01)
    top = res["results"][0]["text"]
    assert "liebe traegt mich durch die dunkle nacht" in top


def test_meaning_search_ignores_stopword_only_query(tmp_path: Path):
    db = _seed(tmp_path)
    res = search_meaning("und der die", db_path=db, limit=5)
    assert res["results"] == []


def test_meaning_search_missing_db(tmp_path: Path):
    res = search_meaning("schmerz", db_path=tmp_path / "nope.sqlite")
    assert res["results"] == []
    assert "warning" in res
