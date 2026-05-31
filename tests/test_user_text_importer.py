from pathlib import Path

from app.services.user_text_importer import (
    load_user_text_summary,
    refresh_user_text_database,
    search_user_rhymes,
)


def test_import_plain_text_builds_user_rhyme_database(tmp_path: Path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "rap.txt").write_text(
        "\n".join(
            [
                "wach lieg im Bett",
                "Wackelndes Brett",
                "Wachstum verlässt",
                "Aktienregress",
                "Plastikbesteck",
                "Schattengewächs",
                "straff wie ein Netz",
                "schattungsgesetz",
            ]
        )
        + "\n",
        "utf-8",
    )

    summary = refresh_user_text_database(
        inbox_dir=inbox,
        data_root=tmp_path,
        prefer_pages_export=False,
    )

    assert summary.imported_count == 1
    assert summary.line_count == 8
    assert summary.rhyme_unit_count >= 7
    assert summary.rhyme_pair_count > 0
    assert (tmp_path / "rhyme_database.sqlite").exists()
    assert list((tmp_path / "extracted").glob("*.txt"))


def test_search_user_rhymes_uses_imported_phrase_units(tmp_path: Path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "rap.txt").write_text(
        "\n".join(
            [
                "nachts wach lieg im Bett",
                "absichtlich erschreckt",
                "lass die finger weg",
                "machen wir es jetzt",
                "wackeliges brett",
                "plastik im besteck",
                "patientenkontakt",
            ]
        )
        + "\n",
        "utf-8",
    )
    refresh_user_text_database(
        inbox_dir=inbox,
        data_root=tmp_path,
        prefer_pages_export=False,
    )

    result = search_user_rhymes(
        "schattenkabinett",
        db_path=tmp_path / "rhyme_database.sqlite",
        limit=5,
        min_score=0.45,
    )

    phrases = [row["phrase"] for row in result["results"]]
    assert "wackeliges brett" in phrases
    assert "plastik im besteck" in phrases
    assert "patientenkontakt" not in phrases


def test_missing_summary_returns_empty_status(tmp_path: Path):
    summary = load_user_text_summary(tmp_path)

    assert summary["source_count"] == 0
    assert summary["documents"] == []
    assert summary["warnings"]
