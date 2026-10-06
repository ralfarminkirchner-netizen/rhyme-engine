import hashlib
import json

import httpx
import pytest

from app.services.song_archive import (sync_archive, record_feedback, search_passages,
                                      export_reviewed_training, sync_configured_archive)


def archive_client(text="Eine Aussage ohne passenden Reim.\nNoch eine Aussage.\n", private=True,
                   wrong_hash=False, unsafe=False):
    data = text.encode()
    digest = hashlib.sha256(data).hexdigest()
    path = f"songtexte/texts/song/{digest}.txt"
    manifest = {"schema_version": 1, "documents": [{"id": "song", "title": "Test",
                "status": "draft", "versions": [{"sha256": digest,
                "path": "../secret" if unsafe else path}]}]}

    def handle(request):
        route = request.url.path
        assert request.headers["authorization"] == "Bearer test-token"
        if "/contents/" in route:
            assert request.url.params["ref"] == "pinned-commit"
        if route.endswith("/mindlaxy-vault"):
            return httpx.Response(200, json={"private": private})
        if route.endswith("/branches/main"):
            return httpx.Response(200, json={"commit": {"sha": "pinned-commit"}})
        if route.endswith("/manifest.json"):
            return httpx.Response(200, json=manifest)
        if route.endswith(path):
            return httpx.Response(200, content=b"modified" if wrong_hash else data)
        raise AssertionError(route)
    return httpx.Client(transport=httpx.MockTransport(handle)), digest


def test_exact_versions_and_idempotent_sync(tmp_path):
    client, digest = archive_client(text="Wiederholt.\n\nWiederholt.\n")
    inbox = tmp_path / "inbox"
    with client:
        first = sync_archive(inbox, "test-token", client)
        second = sync_archive(inbox, "test-token", client)
    assert first["changed"] == 1
    assert second["changed"] == 0
    assert (inbox / f"archive-song-{digest}.txt").read_text() == "Wiederholt.\n\nWiederholt.\n"


@pytest.mark.parametrize("options", [{"private": False}, {"wrong_hash": True}, {"unsafe": True}])
def test_invalid_remote_does_not_write(tmp_path, options):
    client, _ = archive_client(**options)
    inbox = tmp_path / "inbox"
    with client, pytest.raises(ValueError):
        sync_archive(inbox, "test-token", client)
    assert not inbox.exists()


def test_statement_survives_poor_rhyme_and_revisions_keep_history(tmp_path):
    client, digest = archive_client()
    inbox = tmp_path / "inbox"
    with client:
        sync_archive(inbox, "test-token", client)
    record_feedback(inbox, "song", digest, 1, 1, "meaning", 9, "Aussage passt")
    record_feedback(inbox, "song", digest, 1, 1, "rhyme", 1)
    record_feedback(inbox, "song", digest, 1, 1, "rhyme", 2)
    found = search_passages(inbox, "Aussage")["results"][0]
    assert found["ratings"]["meaning"]["rating"] == 9
    assert found["ratings"]["rhyme"]["rating"] == 2
    assert found["version"] == digest
    assert len((tmp_path / "archive/feedback.jsonl").read_text().splitlines()) == 3
    export = export_reviewed_training(inbox)
    assert export["examples"] == 1
    assert "rhythm" not in json.loads((tmp_path / "archive/reviewed_training.jsonl").read_text())["ratings"]


@pytest.mark.parametrize("axis,rating", [("total", 7), ("meaning", -1), ("meaning", 11),
                                         ("meaning", float("nan")), ("meaning", float("inf"))])
def test_invalid_ratings_rejected_before_writes(tmp_path, axis, rating):
    with pytest.raises(ValueError):
        record_feedback(tmp_path / "inbox", "song", "missing", 1, 1, axis, rating)


def test_no_credential_means_no_implicit_remote_access(tmp_path, monkeypatch):
    monkeypatch.delenv("SONG_ARCHIVE_GITHUB_TOKEN", raising=False)
    assert sync_configured_archive(tmp_path / "inbox") == {"status": "not_configured"}
