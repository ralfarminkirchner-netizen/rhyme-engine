import sys
from pathlib import Path

from app.services.rhyme_reranker import (
    RerankConfig,
    build_rerank_payload,
    rerank_with_command,
)
from app.services.user_text_importer import refresh_user_text_database, search_user_rhymes


def test_rerank_payload_excludes_private_context_by_default():
    payload = build_rerank_payload(
        "wach lieg im Bett",
        [
            {
                "phrase": "wackeliges brett",
                "score": 0.9,
                "anchor": 1.0,
                "tail": 1.0,
                "vowel": 1.0,
                "cadence": 1.0,
                "syllable_count": 5,
                "line_text": "private test line",
            }
        ],
    )

    candidate = payload["candidates"][0]
    assert payload["privacy"]["line_context_included"] is False
    assert candidate["phrase"] == "wackeliges brett"
    assert "line_text" not in candidate
    assert "source_title" not in candidate


def test_command_reranker_can_reorder_candidates(tmp_path: Path):
    script = tmp_path / "fake_reranker.py"
    script.write_text(
        "\n".join(
            [
                "import json, sys",
                "data = json.load(sys.stdin)",
                "ranked = []",
                "for item in data['candidates']:",
                "    score = 0.99 if item['phrase'] == 'wackeliges brett' else 0.2",
                "    ranked.append({'candidate_id': item['candidate_id'], 'score': score, 'reason': 'fake flow fit'})",
                "ranked.sort(key=lambda item: item['score'], reverse=True)",
                "print(json.dumps({'ranked': ranked}))",
            ]
        ),
        "utf-8",
    )

    result = rerank_with_command(
        "schattenkabinett",
        [
            {"phrase": "zu zweit sind wir komplett", "score": 0.93},
            {"phrase": "wackeliges brett", "score": 0.90},
        ],
        RerankConfig(command=f"{sys.executable} {script}"),
    )

    assert result["enabled"] is True
    assert result["results"][0]["phrase"] == "wackeliges brett"
    assert result["results"][0]["llm_score"] == 0.99
    assert result["results"][0]["llm_reason"] == "fake flow fit"


def test_user_search_can_use_command_reranker(tmp_path: Path, monkeypatch):
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

    script = tmp_path / "fake_reranker.py"
    script.write_text(
        "\n".join(
            [
                "import json, sys",
                "data = json.load(sys.stdin)",
                "ranked = []",
                "for item in data['candidates']:",
                "    score = 1.0 if item['phrase'] == 'genau jetzt' else 0.1",
                "    ranked.append({'candidate_id': item['candidate_id'], 'score': score, 'reason': 'chosen by fake model'})",
                "ranked.sort(key=lambda item: item['score'], reverse=True)",
                "print(json.dumps({'ranked': ranked}))",
            ]
        ),
        "utf-8",
    )
    monkeypatch.setenv("RHYME_RERANKER_COMMAND", f"{sys.executable} {script}")

    result = search_user_rhymes(
        "schattenkabinett",
        db_path=tmp_path / "rhyme_database.sqlite",
        limit=3,
        min_score=0.45,
        rerank=True,
        rerank_candidate_count=4,
    )

    assert result["rerank"]["enabled"] is True
    assert result["results"][0]["phrase"] == "genau jetzt"
    assert result["results"][0]["llm_reason"] == "chosen by fake model"
