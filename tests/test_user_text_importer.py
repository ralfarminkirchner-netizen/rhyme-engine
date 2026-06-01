from pathlib import Path

from app.services.user_text_importer import (
    build_training_dataset,
    load_user_text_summary,
    refresh_user_text_database,
    search_quote_library,
    search_text_library,
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
    assert summary.quote_count > 0
    assert summary.sample_quotes
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


def test_search_user_rhymes_does_not_saturate_hard_endings_over_phrase_fit(tmp_path: Path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "rap.txt").write_text(
        "\n".join(
            [
                "zu zweit sind wir komplett",
                "wackeliges brett",
                "genau jetzt",
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
    assert phrases.index("wackeliges brett") < phrases.index("zu zweit sind wir komplett")
    assert "patientenkontakt" not in phrases
    assert len({row["score"] for row in result["results"]}) > 1


def test_missing_summary_returns_empty_status(tmp_path: Path):
    summary = load_user_text_summary(tmp_path)

    assert summary["source_count"] == 0
    assert summary["documents"] == []
    assert summary["quote_count"] == 0
    assert summary["warnings"]


def test_search_text_library_returns_matching_imported_lines(tmp_path: Path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "rap.txt").write_text(
        "\n".join(
            [
                "nachts wach lieg im Bett",
                "der Schatten steht im Treppenhaus",
                "Plastikbesteck liegt auf dem Tisch",
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

    result = search_text_library(
        "Schatten Treppenhaus",
        db_path=tmp_path / "rhyme_database.sqlite",
        limit=5,
    )

    assert result["results"][0]["text"] == "der Schatten steht im Treppenhaus"
    assert result["results"][0]["matched_terms"] == 2


def test_search_quote_library_ranks_quotable_rhyme_lines(tmp_path: Path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "rap.txt").write_text(
        "\n".join(
            [
                "nachts wach lieg im Bett",
                "der Schatten schreibt Gesetz",
                "wackeliges brett",
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

    result = search_quote_library(
        "schattenkabinett",
        db_path=tmp_path / "rhyme_database.sqlite",
        limit=5,
        min_score=0.30,
    )

    texts = [row["text"] for row in result["results"]]
    assert "der Schatten schreibt Gesetz" in texts
    assert all(row["quote_score"] > 0 for row in result["results"])


def test_build_training_dataset_exports_private_jsonl(tmp_path: Path):
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

    output_path = tmp_path / "training" / "rhyme_training.jsonl"
    summary = build_training_dataset(
        db_path=tmp_path / "rhyme_database.sqlite",
        output_path=output_path,
        max_examples=20,
    )

    assert summary["status"] == "ok"
    assert summary["example_count"] > 0
    assert summary["rhyme_pair_count"] > 0
    assert output_path.exists()
    lines = output_path.read_text("utf-8").splitlines()
    assert len(lines) == summary["example_count"]
    assert any('"kind": "rhyme_pair"' in line for line in lines)


def test_build_training_dataset_reports_missing_database(tmp_path: Path):
    summary = build_training_dataset(
        db_path=tmp_path / "missing.sqlite",
        output_path=tmp_path / "training.jsonl",
    )

    assert summary["status"] == "missing_database"
    assert summary["example_count"] == 0
    assert not (tmp_path / "training.jsonl").exists()
