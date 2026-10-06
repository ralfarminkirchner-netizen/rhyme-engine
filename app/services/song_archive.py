"""Private, versioned song memory; meaning and rhyme ratings stay independent."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath

import httpx

ARCHIVE_REPO = "ralfarminkirchner-netizen/mindlaxy-vault"
AXES = {"meaning", "rhyme", "rhythm"}
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def sync_archive(inbox: Path, token: str, client=None) -> dict:
    """Read a pinned private GitHub snapshot; validate everything before writing."""
    if not token:
        raise ValueError("Private archive access requires SONG_ARCHIVE_GITHUB_TOKEN")
    own_client = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=False)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    base = f"https://api.github.com/repos/{ARCHIVE_REPO}"

    def get(url):
        response = client.get(url, headers=headers)
        if response.status_code != 200:
            # Never leak response bodies, request headers or tokens.
            raise RuntimeError(f"Archive read failed (HTTP {response.status_code})")
        return response

    try:
        if get(base).json().get("private") is not True:
            raise ValueError("Song archive must be private")
        commit = get(base + "/branches/main").json()["commit"]["sha"]
        raw_headers = {**headers, "Accept": "application/vnd.github.raw+json"}

        def raw(path):
            response = client.get(base + f"/contents/{path}?ref={commit}", headers=raw_headers)
            if response.status_code != 200:
                raise RuntimeError(f"Archive file read failed (HTTP {response.status_code})")
            return response.content

        manifest = json.loads(raw("songtexte/manifest.json"))
        if manifest.get("schema_version") != 1:
            raise ValueError("Unsupported song archive schema")
        pending = []
        seen = set()
        for doc in manifest["documents"]:
            if not SAFE_ID.fullmatch(doc["id"]):
                raise ValueError("Invalid document identity")
            for version in doc["versions"]:
                digest = version["sha256"]
                if not re.fullmatch(r"[a-f0-9]{64}", digest):
                    raise ValueError("Invalid content digest")
                path = PurePosixPath(version["path"])
                expected = PurePosixPath("songtexte/texts") / doc["id"] / (digest + ".txt")
                if path != expected:
                    raise ValueError("Invalid archive path")
                name = f"archive-{doc['id']}-{digest}.txt"
                if name in seen:
                    raise ValueError("Duplicate archive version")
                seen.add(name)
                data = raw(str(path))
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError("Archive content checksum mismatch")
                data.decode("utf-8")
                pending.append((name, data))
        inbox.mkdir(parents=True, exist_ok=True)
        changed = 0
        for name, data in pending:
            target = inbox / name
            if not target.exists() or target.read_bytes() != data:
                temporary = target.with_suffix(".tmp")
                temporary.write_bytes(data)
                temporary.replace(target)
                changed += 1
        memory = inbox.parent / "archive"
        memory.mkdir(parents=True, exist_ok=True)
        temporary = memory / "manifest.tmp"
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
        temporary.replace(memory / "manifest.json")
        return {"status": "ok", "versions": len(pending), "changed": changed, "commit": commit}
    finally:
        if own_client:
            client.close()


def sync_configured_archive(inbox: Path) -> dict:
    token = os.environ.get("SONG_ARCHIVE_GITHUB_TOKEN", "")
    if not token:
        return {"status": "not_configured"}
    try:
        return sync_archive(inbox, token)
    except httpx.HTTPError as exc:
        raise RuntimeError("Archive connection failed") from exc


def passage(inbox: Path, document_id: str, version: str, start: int, end: int) -> dict:
    manifest = json.loads((inbox.parent / "archive/manifest.json").read_text("utf-8"))
    doc = next((d for d in manifest["documents"] if d["id"] == document_id), None)
    if not doc or not any(v["sha256"] == version for v in doc["versions"]):
        raise ValueError("Unknown source/version")
    lines = (inbox / f"archive-{document_id}-{version}.txt").read_text("utf-8").splitlines()
    if not 1 <= start <= end <= len(lines):
        raise ValueError("Invalid passage range")
    return {"document_id": document_id, "title": doc["title"], "version": version,
            "start_line": start, "end_line": end, "text": "\n".join(lines[start-1:end]),
            "source": doc.get("source", {}), "status": doc.get("status", "draft")}


def record_feedback(inbox: Path, document_id: str, version: str, start: int, end: int,
                    axis: str, rating: float, comment: str = "") -> dict:
    if axis not in AXES or not 0 <= rating <= 10:
        raise ValueError("Use meaning/rhyme/rhythm and a finite rating from 0 to 10")
    item = {**passage(inbox, document_id, version, start, end),
            "axis": axis, "rating": rating, "comment": comment}
    path = inbox.parent / "archive/feedback.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def reviewed_passages(inbox: Path) -> list:
    """Latest assessment per axis, with its history retained in feedback.jsonl."""
    path = inbox.parent / "archive/feedback.jsonl"
    if not path.exists():
        return []
    entries = {}
    for line in path.read_text("utf-8").splitlines():
        item = json.loads(line)
        key = (item["document_id"], item["version"], item["start_line"], item["end_line"])
        row = entries.setdefault(key, {k: v for k, v in item.items() if k not in {"axis", "rating", "comment"}})
        row.setdefault("ratings", {})[item["axis"]] = {"rating": item["rating"], "comment": item["comment"]}
    return list(entries.values())


def search_passages(inbox: Path, query: str, limit: int = 25) -> dict:
    """Reviewed statements remain retrievable even with poor rhyme ratings."""
    from app.services.meaning_search import _tokens
    terms = set(_tokens(query))
    matches = []
    for item in reviewed_passages(inbox):
        overlap = terms & set(_tokens(item["text"]))
        if overlap:
            matches.append({**item, "matched_terms": sorted(overlap), "score": len(overlap) / len(terms)})
    matches.sort(key=lambda item: (item["score"], item["ratings"].get("meaning", {}).get("rating", 0)), reverse=True)
    return {"axis": "meaning", "results": matches[:limit], "total_candidates": len(matches)}


def export_reviewed_training(inbox: Path) -> dict:
    """Explicit user feedback only; no invented positive labels or model training."""
    items = reviewed_passages(inbox)
    path = inbox.parent / "archive/reviewed_training.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items), "utf-8")
    return {"status": "ok", "examples": len(items), "path": str(path)}
