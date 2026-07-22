"""Tests fuer die zusaetzlichen Reim-Woerterbuecher (lokal)."""
from pathlib import Path

from app.services.dictionary_loader import (
    SOURCE_PREFIX,
    dictionary_summary,
    import_dictionaries,
    score_dictionary_rhymes,
)
from app.services.user_text_importer import refresh_user_text_database, search_user_rhymes


def _seed_personal(tmp_path: Path) -> Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "rap.txt").write_text(
        "\n".join(["wackeliges brett", "lass die finger weg", "plastik im besteck"]) + "\n",
        "utf-8",
    )
    refresh_user_text_database(inbox_dir=inbox, data_root=tmp_path, prefer_pages_export=False)
    return tmp_path / "rhyme_database.sqlite"


def _seed_dict(tmp_path: Path) -> Path:
    d = tmp_path / "dictionaries"
    d.mkdir()
    (d / "ontologie.txt").write_text(
        "\n".join(["# komm", "Bewusstsein", "Erkenntnis", "Kabinett", "Dasein"]) + "\n", "utf-8"
    )
    return d


def test_import_and_summary(tmp_path: Path):
    db = _seed_personal(tmp_path)
    res = import_dictionaries(dictionary_dir=_seed_dict(tmp_path), db_path=db)
    assert res["status"] == "ok"
    assert res["sources"].get("ontologie") == 4   # Kommentarzeile ignoriert
    summ = dictionary_summary(db_path=db)
    assert summ["total_entries"] == 4


def test_score_dictionary_rhymes_finds_match(tmp_path: Path):
    db = _seed_personal(tmp_path)
    import_dictionaries(dictionary_dir=_seed_dict(tmp_path), db_path=db)
    hits = score_dictionary_rhymes("schattenkabinett", db_path=db, min_score=0.0)
    phrases = [h["phrase"] for h in hits]
    assert "Kabinett" in phrases
    kab = next(h for h in hits if h["phrase"] == "Kabinett")
    assert kab["source_title"].startswith(SOURCE_PREFIX)
    assert kab["is_dictionary"] is True


def test_search_includes_dictionary_only_when_requested(tmp_path: Path):
    db = _seed_personal(tmp_path)
    import_dictionaries(dictionary_dir=_seed_dict(tmp_path), db_path=db)

    without = search_user_rhymes("schattenkabinett", db_path=db, limit=20, min_score=0.4)
    assert not any(r["source_title"].startswith(SOURCE_PREFIX) for r in without["results"])

    withd = search_user_rhymes(
        "schattenkabinett", db_path=db, limit=20, min_score=0.4, include_dictionary=True
    )
    assert any(r["phrase"] == "Kabinett" for r in withd["results"])


def test_dictionary_survives_personal_reimport(tmp_path: Path):
    db = _seed_personal(tmp_path)
    import_dictionaries(dictionary_dir=_seed_dict(tmp_path), db_path=db)
    # Personal-Reimport darf das Woerterbuch nicht loeschen
    inbox = tmp_path / "inbox"
    refresh_user_text_database(inbox_dir=inbox, data_root=tmp_path, prefer_pages_export=False)
    assert dictionary_summary(db_path=db)["total_entries"] == 4
