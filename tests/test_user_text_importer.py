from pathlib import Path

from app.services.user_text_importer import (
    build_training_dataset,
    load_full_user_library,
    load_user_text_summary,
    refresh_user_text_database,
    save_rhyme_feedback,
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

    # limit=6: "plastik im besteck" (-eck) ist nach der Stress-Anchor-Migration
    # gleichauf mit "lass die finger weg" (beide -eck-Slant auf -ett); exakte
    # -ett-Treffer ("...jetzt") ranken jetzt korrekt davor. Beide -eck-Phrasen
    # sind gleichwertig -> Fenster 6, damit der Gleichstand nicht eine arbitraer
    # rauswirft. orthografischer Fehltreffer "patientenkontakt" bleibt draußen.
    result = search_user_rhymes(
        "schattenkabinett",
        db_path=tmp_path / "rhyme_database.sqlite",
        limit=6,
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


def test_load_full_user_library_returns_all_library_lists(tmp_path: Path):
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

    library = load_full_user_library(
        db_path=tmp_path / "rhyme_database.sqlite",
        limit=20,
    )

    assert library["status"] == "ok"
    assert library["counts"]["text_lines"] == 6
    assert library["counts"]["rhyme_units"] > 0
    assert library["counts"]["rhyme_pairs"] > 0
    assert library["counts"]["quotes"] > 0
    assert library["text_lines"]
    assert library["rhyme_units"]
    assert library["rhyme_pairs"]
    assert library["quotes"]


def test_load_full_user_library_reports_missing_database(tmp_path: Path):
    library = load_full_user_library(db_path=tmp_path / "missing.sqlite")

    assert library["status"] == "missing_database"
    assert library["counts"]["text_lines"] == 0
    assert library["text_lines"] == []


def test_rhyme_feedback_is_saved_and_returned_in_search(tmp_path: Path):
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
    db_path = tmp_path / "rhyme_database.sqlite"
    first_search = search_user_rhymes(
        "wach lieg im Bett",
        db_path=db_path,
        limit=5,
        min_score=0.0,
    )
    target = first_search["results"][0]

    saved = save_rhyme_feedback(
        query="wach lieg im Bett",
        source_title=target["source_title"],
        line_no=target["line_no"],
        phrase=target["phrase"],
        rating=10,
        comment="starker endreim",
        db_path=db_path,
    )

    assert saved["status"] == "ok"
    second_search = search_user_rhymes(
        "wach lieg im Bett",
        db_path=db_path,
        limit=5,
        min_score=0.0,
    )
    rated = [
        row for row in second_search["results"]
        if row["source_title"] == target["source_title"]
        and row["line_no"] == target["line_no"]
        and row["phrase"] == target["phrase"]
    ][0]
    assert rated["feedback_rating"] == 10
    assert rated["feedback_comment"] == "starker endreim"
    assert rated["feedback_score"] >= rated["score"]


def test_rhyme_feedback_survives_reimport(tmp_path: Path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "rap.txt").write_text(
        "\n".join(
            [
                "nachts wach lieg im Bett",
                "absichtlich erschreckt",
                "lass die finger weg",
                "machen wir es jetzt",
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
    db_path = tmp_path / "rhyme_database.sqlite"
    target = search_user_rhymes(
        "wach lieg im Bett",
        db_path=db_path,
        limit=1,
        min_score=0.0,
    )["results"][0]
    save_rhyme_feedback(
        query="wach lieg im Bett",
        source_title=target["source_title"],
        line_no=target["line_no"],
        phrase=target["phrase"],
        rating=2,
        comment="zu glatt",
        db_path=db_path,
    )

    refresh_user_text_database(
        inbox_dir=inbox,
        data_root=tmp_path,
        prefer_pages_export=False,
    )

    result = search_user_rhymes(
        "wach lieg im Bett",
        db_path=db_path,
        limit=5,
        min_score=0.0,
    )
    assert any(row.get("feedback_rating") == 2 for row in result["results"])


def test_duplicate_trailing_phrases_are_collapsed_in_search(tmp_path: Path):
    """Verschiedene Zeilen mit identischer Endphrase fluten das Ranking nicht."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "rap.txt").write_text(
        "\n".join(
            [
                "morgens wieder wackeliges brett",   # Endfenster: 'wieder wackeliges brett'
                "lass die finger weg",
                "abends wieder wackeliges brett",    # gleiche Endphrase, andere Zeile
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
    db_path = tmp_path / "rhyme_database.sqlite"
    result = search_user_rhymes(
        "wach lieg im Bett",
        db_path=db_path,
        limit=10,
        min_score=0.0,
    )
    phrases = [row["phrase"] for row in result["results"]]
    assert phrases.count("wieder wackeliges brett") == 1
    rep = next(row for row in result["results"] if row["phrase"] == "wieder wackeliges brett")
    assert rep["occurrence_count"] == 2


def _seed_pattern_corpus(tmp_path: Path) -> Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "rap.txt").write_text(
        "\n".join(
            [
                "lass die finger weg",
                "machen wir es jetzt",
                "wackeliges brett",
                "plastik im besteck",
                "absichtlich erschreckt",
            ]
        )
        + "\n",
        "utf-8",
    )
    refresh_user_text_database(inbox_dir=inbox, data_root=tmp_path, prefer_pages_export=False)
    return tmp_path / "rhyme_database.sqlite"


def test_positive_feedback_generalizes_to_unrated_similar_pattern(tmp_path: Path):
    """8-10-Bewertungen auf zwei Muster-Treffer ziehen einen dritten, unbewerteten hoch."""
    db_path = _seed_pattern_corpus(tmp_path)

    baseline = search_user_rhymes("ganz neue zeile im bett", db_path=db_path, limit=10, min_score=0.0)
    by_phrase = {row["phrase"]: row for row in baseline["results"]}
    members = [p for p in ("plastik im besteck", "absichtlich erschreckt", "wackeliges brett") if p in by_phrase]
    assert len(members) >= 3
    rated_a, rated_b, target = members[0], members[1], members[2]
    target_before = by_phrase[target]["feedback_score"]

    # Zwei VERSCHIEDENE Treffer desselben Endreim-/Flow-Musters je einmal stark bewerten.
    for phrase in (rated_a, rated_b):
        save_rhyme_feedback(
            query="frische bewertungsphrase im bett",
            source_title=by_phrase[phrase]["source_title"],
            line_no=by_phrase[phrase]["line_no"],
            phrase=phrase,
            rating=10,
            db_path=db_path,
        )

    after = search_user_rhymes("ganz neue zeile im bett", db_path=db_path, limit=10, min_score=0.0)
    target_after = next(row for row in after["results"] if row["phrase"] == target)

    # Der NICHT bewertete, aber gleich-gemusterte Treffer wurde generalisiert mitgezogen.
    assert target_after["feedback_rating"] is None
    assert target_after["feedback_pattern_count"] >= 2
    assert target_after["feedback_score"] > target_before


def test_low_feedback_generalizes_down_unrated_similar_pattern(tmp_path: Path):
    """0-3-Bewertungen auf Muster-Treffer senken einen unbewerteten Muster-Treffer ab."""
    db_path = _seed_pattern_corpus(tmp_path)

    baseline = search_user_rhymes("ganz neue zeile im bett", db_path=db_path, limit=10, min_score=0.0)
    by_phrase = {row["phrase"]: row for row in baseline["results"]}
    members = [p for p in ("plastik im besteck", "absichtlich erschreckt", "wackeliges brett") if p in by_phrase]
    rated_a, rated_b, target = members[0], members[1], members[2]
    target_before = by_phrase[target]["feedback_score"]

    for phrase in (rated_a, rated_b):
        save_rhyme_feedback(
            query="frische bewertungsphrase im bett",
            source_title=by_phrase[phrase]["source_title"],
            line_no=by_phrase[phrase]["line_no"],
            phrase=phrase,
            rating=1,
            db_path=db_path,
        )

    after = search_user_rhymes("ganz neue zeile im bett", db_path=db_path, limit=10, min_score=0.0)
    target_after = next(row for row in after["results"] if row["phrase"] == target)
    assert target_after["feedback_pattern_count"] >= 2
    assert target_after["feedback_score"] < target_before


def test_feedback_comment_is_never_sent_to_external_reranker(tmp_path: Path):
    """Kommentartexte bleiben lokal — Rerank-Payload enthält sie nicht."""
    import app.services.user_text_importer as importer

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "rap.txt").write_text(
        "\n".join(["lass die finger weg", "wackeliges brett", "plastik im besteck"]) + "\n",
        "utf-8",
    )
    refresh_user_text_database(inbox_dir=inbox, data_root=tmp_path, prefer_pages_export=False)
    db_path = tmp_path / "rhyme_database.sqlite"

    target = search_user_rhymes("wach lieg im Bett", db_path=db_path, limit=1, min_score=0.0)["results"][0]
    save_rhyme_feedback(
        query="wach lieg im Bett",
        source_title=target["source_title"],
        line_no=target["line_no"],
        phrase=target["phrase"],
        rating=9,
        comment="GEHEIM privater kommentar",
        db_path=db_path,
    )

    captured: dict = {}

    def _fake_rerank(query, candidates):
        captured["payload"] = repr(candidates)
        return {"enabled": True, "provider": "fake", "warning": "", "results": candidates}

    original = importer.search_user_rhymes.__globals__.get("rerank_rhymes")
    # search_user_rhymes importiert rerank_rhymes lazily; patche das Quellmodul.
    import app.services.ai_reranker as ai_reranker
    ai_reranker.rerank_rhymes = _fake_rerank
    try:
        search_user_rhymes(
            "wach lieg im Bett", db_path=db_path, limit=5, min_score=0.0, rerank=True,
        )
    finally:
        if original is not None:
            ai_reranker.rerank_rhymes = original

    assert "GEHEIM" not in captured.get("payload", "")
