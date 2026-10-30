"""Offline integration checks with invented text and temporary private stores."""
import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.rhyme_graph_workspace import (
    EdgeFeedbackRequest, GraphWorkspaceStore, WorkspaceRequest,
    build_workspace_graph, load_source_context,
)
from app.services.user_text_importer import refresh_user_text_database


def request(**changes):
    return WorkspaceRequest.model_validate({
        "text": "Hase\nNase", "min_syllables": 2, "max_syllables": 2,
        **changes,
    })


def archive(tmp_path: Path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "invented-fixture.txt").write_text(
        "Leise Tassen\nWeise Gassen\nBunte Massen\n", encoding="utf-8",
    )
    refresh_user_text_database(inbox_dir=inbox, data_root=tmp_path, prefer_pages_export=False)
    return tmp_path / "rhyme_database.sqlite"


def test_build_is_reproducible_and_missing_library_is_explicit(tmp_path):
    req = request(include_library=True, library_query="leise Tassen")
    left = build_workspace_graph(req, tmp_path / "missing.sqlite")
    right = build_workspace_graph(req, tmp_path / "missing.sqlite")
    assert left == right
    assert len(left["fingerprint"]) == 64
    assert any("Reimbibliothek fehlt" in warning for warning in left["warnings"])
    assert not list(tmp_path.iterdir())


def test_archive_sources_keep_blank_lines_and_read_original_context(tmp_path):
    db = archive(tmp_path)
    graph = build_workspace_graph(request(
        text="Hase\n\n", include_library=True,
        library_query="weise Gassen", min_syllables=2, max_syllables=4,
    ), db)
    sourced = [node for node in graph["nodes"] if node["source"]]
    assert sourced
    assert min(node["line_index"] for node in sourced) == 2
    for node in sourced:
        source = node["source"]
        assert graph["text"].splitlines()[node["line_index"]] == source["line_text"]
        assert graph["text"][node["char_start"]:node["char_end"]] == node["text"]
        original = load_source_context(source["source_id"], source["line_no"], db)
        assert any(line["text"] == source["line_text"] and line["line_no"] == source["line_no"] for line in original["lines"])
        assert original["title"] == "invented-fixture"


@pytest.mark.parametrize("suffix", ["\r", "\u2028", "\r\n", "\n\n"])
def test_archive_uses_core_lf_line_indices(tmp_path, suffix):
    db = archive(tmp_path)
    graph = build_workspace_graph(request(
        text="Hase" + suffix, include_library=True,
        library_query="weise Gassen", max_syllables=4,
    ), db)
    sourced = [node for node in graph["nodes"] if node["source"]]
    assert sourced
    for node in sourced:
        assert graph["lines"][node["line_index"]]["text"] == node["source"]["line_text"]


def test_source_context_detects_changes_after_snapshot(tmp_path):
    db = archive(tmp_path)
    graph = build_workspace_graph(request(
        include_library=True, library_query="weise Gassen", max_syllables=4,
    ), db)
    source = next(node["source"] for node in graph["nodes"] if node["source"])
    assert source["line_hash"] == hashlib.sha256(source["line_text"].encode("utf-8")).hexdigest()
    assert load_source_context(source["source_id"], source["line_no"], db, source["line_hash"])["matches_snapshot"] is True
    with sqlite3.connect(db) as conn:
        conn.execute("update lines set text=? where source_id=? and line_no=?", ("Inzwischen veränderte Quelle", source["source_id"], source["line_no"]))
    changed = load_source_context(source["source_id"], source["line_no"], db, source["line_hash"])
    assert changed["matches_snapshot"] is False
    assert next(node["source"]["line_text"] for node in graph["nodes"] if node["source"]) == source["line_text"]


def test_snapshot_and_feedback_survive_new_store_without_overwriting_history(tmp_path):
    path = tmp_path / "graph.sqlite"
    store = GraphWorkspaceStore(path)
    assert store.list_sessions() == {"sessions": []}
    assert not path.exists()
    req = request()
    graph = build_workspace_graph(req)
    assert graph["edges"]
    saved = store.save("Meine Prüfung", req, graph)
    assert saved["feedback"] == []
    edge_id = graph["edges"][0]["id"]
    store.add_feedback(saved["id"], EdgeFeedbackRequest(
        edge_id=edge_id, decision="experiment", performance_note="Vokal länger sprechen.",
        meaning_note="Gleiche Szene, andere Perspektive.",
    ))
    store.add_feedback(saved["id"], EdgeFeedbackRequest(
        edge_id=edge_id, decision="accepted", heard=True, comment="Selbst gesprochen.",
    ))
    reopened = GraphWorkspaceStore(path).load(saved["id"])
    assert reopened["graph"] == graph
    assert reopened["request"] == req.model_dump(mode="json")
    assert reopened["feedback"][0]["decision"] == "accepted"
    assert reopened["feedback"][0]["heard"] is True
    assert [item["decision"] for item in reopened["feedback_history"]] == ["experiment", "accepted"]
    assert reopened["feedback_history"][0]["meaning_note"] == "Gleiche Szene, andere Perspektive."
    assert GraphWorkspaceStore(path).list_sessions()["sessions"][0]["edge_count"] == len(graph["edges"])


def test_feedback_cannot_target_a_different_snapshot(tmp_path):
    store = GraphWorkspaceStore(tmp_path / "graph.sqlite")
    saved = store.save("Prüfung", request(), build_workspace_graph(request()))
    with pytest.raises(ValueError, match="gehört nicht"):
        store.add_feedback(saved["id"], EdgeFeedbackRequest(edge_id="made-up", decision="accepted"))
    assert store.load(saved["id"])["feedback_history"] == []


def test_api_build_save_feedback_reload_and_stale_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("REIMGRAPH_DATA_DIR", str(tmp_path))
    from app.main import app

    client = TestClient(app)
    payload = request().model_dump(mode="json")
    built = client.post("/api/rhymes/graph/build", json=payload)
    assert built.status_code == 200, built.text
    graph = built.json()
    assert graph["edges"]
    stale = client.post("/api/rhymes/graph/sessions", json={
        "title": "Veraltet", "request": payload, "expected_graph_fingerprint": "0" * 64,
    })
    assert stale.status_code == 409
    assert client.get("/api/rhymes/graph/sessions").json() == {"sessions": []}
    saved = client.post("/api/rhymes/graph/sessions", json={
        "title": "Gespeicherte Prüfung", "request": payload,
        "expected_graph_fingerprint": graph["fingerprint"],
    })
    assert saved.status_code == 201, saved.text
    session_id = saved.json()["id"]
    feedback = client.post(f"/api/rhymes/graph/sessions/{session_id}/feedback", json={
        "edge_id": graph["edges"][0]["id"], "decision": "rejected", "comment": "Für diese Fassung zu glatt.",
    })
    assert feedback.status_code == 201, feedback.text
    loaded = client.get(f"/api/rhymes/graph/sessions/{session_id}")
    assert loaded.status_code == 200
    assert loaded.json()["graph"] == graph
    assert loaded.json()["feedback"][0]["decision"] == "rejected"
    assert loaded.json()["feedback"][0]["heard"] is False
    assert client.get("/api/rhymes/graph/sessions/missing").status_code == 404
    assert client.post("/api/rhymes/graph/build", json={**payload, "unknown": True}).status_code == 422
    assert client.post("/api/rhymes/graph/build", json={**payload, "text": "   "}).status_code == 422


def test_api_archive_lookup_and_source_hash_round_trip(tmp_path, monkeypatch):
    db = archive(tmp_path)
    monkeypatch.setenv("REIMGRAPH_ARCHIVE_PATH", str(db))
    from app.main import app

    client = TestClient(app)
    built = client.post("/api/rhymes/graph/build", json=request(
        include_library=True, library_query="weise Gassen", max_syllables=4,
    ).model_dump(mode="json"))
    assert built.status_code == 200, built.text
    source = next(node["source"] for node in built.json()["nodes"] if node["source"])
    endpoint = f"/api/rhymes/graph/sources/{source['source_id']}"
    params = {"line_no": source["line_no"], "expected_line_hash": source["line_hash"]}
    reread = client.get(endpoint, params=params)
    assert reread.status_code == 200
    assert reread.json()["matches_snapshot"] is True
    with sqlite3.connect(db) as conn:
        conn.execute("update lines set text=? where source_id=? and line_no=?", ("Veränderte Testquelle", source["source_id"], source["line_no"]))
    assert client.get(endpoint, params=params).json()["matches_snapshot"] is False
    assert client.get(endpoint, params={"line_no": 999999}).status_code == 404
    assert client.get(endpoint, params={"line_no": 0}).status_code == 422
