from pathlib import Path

from app.services.local_rhyme_model import rerank_with_local_model, train_local_rhyme_model
from app.services.user_text_importer import refresh_user_text_database, search_user_rhymes


def _build_fixture_database(tmp_path: Path) -> Path:
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
    return tmp_path / "rhyme_database.sqlite"


def test_train_local_rhyme_model_writes_private_model(tmp_path: Path):
    db_path = _build_fixture_database(tmp_path)
    model_path = tmp_path / "training" / "local_rhyme_model.json"

    summary = train_local_rhyme_model(
        db_path=db_path,
        model_path=model_path,
        min_pair_score=0.50,
    )

    assert summary["status"] == "ok"
    assert summary["pair_count"] > 0
    assert model_path.exists()
    assert summary["weights"]["anchor"] > 0
    assert 3 <= summary["ideal_syllables"] <= 8


def test_local_model_reranks_candidates_with_learned_score(tmp_path: Path):
    db_path = _build_fixture_database(tmp_path)
    model_path = tmp_path / "training" / "local_rhyme_model.json"
    train_local_rhyme_model(db_path=db_path, model_path=model_path, min_pair_score=0.50)

    candidates = search_user_rhymes(
        "schattenkabinett",
        db_path=db_path,
        limit=5,
        min_score=0.40,
    )["results"]
    reranked = rerank_with_local_model(
        "schattenkabinett",
        candidates,
        model_path=model_path,
    )

    assert reranked["enabled"] is True
    assert reranked["provider"] == "local"
    assert reranked["results"]
    assert all("learned_score" in row for row in reranked["results"])


def test_local_model_reports_missing_model(tmp_path: Path):
    result = rerank_with_local_model(
        "schattenkabinett",
        [{"phrase": "wackeliges brett", "score": 0.8}],
        model_path=tmp_path / "missing.json",
    )

    assert result["enabled"] is False
    assert result["provider"] == "local"
    assert result["results"][0]["phrase"] == "wackeliges brett"
