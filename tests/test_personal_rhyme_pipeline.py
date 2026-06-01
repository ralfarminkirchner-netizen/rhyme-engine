from pathlib import Path

from app.services.personal_rhyme_pipeline import run_personal_rhyme_pipeline


def test_personal_rhyme_pipeline_runs_import_train_and_reranked_search(tmp_path: Path):
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
                "zu zweit sind wir komplett",
            ]
        )
        + "\n",
        "utf-8",
    )

    result = run_personal_rhyme_pipeline(
        query="schattenkabinett",
        inbox_dir=inbox,
        data_root=tmp_path,
        prefer_pages_export=False,
        min_pair_score=0.50,
        limit=5,
        min_score=0.35,
    )

    assert result["status"] == "ok"
    assert result["import"]["imported_count"] == 1
    assert result["training"]["example_count"] > 0
    assert result["model"]["pair_count"] > 0
    assert result["search"]["rerank"]["provider"] == "local"
    assert result["search"]["results"]
    assert all("learned_score" in row for row in result["search"]["results"])
    assert (tmp_path / "training" / "rhyme_training.jsonl").exists()
    assert (tmp_path / "training" / "local_rhyme_model.json").exists()


def test_personal_rhyme_pipeline_reports_incomplete_without_sources(tmp_path: Path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    result = run_personal_rhyme_pipeline(
        query="schattenkabinett",
        inbox_dir=inbox,
        data_root=tmp_path,
        prefer_pages_export=False,
    )

    assert result["status"] == "no_training_pairs"
    assert result["import"]["imported_count"] == 0
    assert result["model"]["pair_count"] == 0
    assert result["search"]["results"] == []
