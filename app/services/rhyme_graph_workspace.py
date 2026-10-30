"""Local graph workspaces, archive provenance and explicit user decisions.

Graph snapshots are immutable. Feedback is an append-only event stream, scoped
to one edge in one snapshot; no decision is inferred from a similarity score.
This module does not call a language model or read original archive files.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.rhyme_graph import GraphBuildRequest
from app.services.rhyme_graph import build_rhyme_graph


PROJECT_DATA = Path(__file__).resolve().parents[1] / "data" / "user_texts"


class WorkspaceRequest(GraphBuildRequest):
    include_library: bool = False
    library_query: str = Field("", max_length=500)
    library_limit: int = Field(12, ge=1, le=30)


class SaveGraphRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field("Reimgraph", min_length=1, max_length=120)
    request: WorkspaceRequest
    expected_graph_fingerprint: Optional[str] = Field(None, pattern=r"^[a-f0-9]{64}$")

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Bitte einen Titel für den Graphen angeben.")
        return value.strip()


class EdgeFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edge_id: str = Field(min_length=1, max_length=100)
    decision: Literal["accepted", "experiment", "rejected"]
    heard: bool = False
    comment: str = Field("", max_length=4000)
    performance_note: str = Field("", max_length=4000)
    meaning_note: str = Field("", max_length=4000)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _archive_path(path: Path | None = None) -> Path:
    configured = os.environ.get("REIMGRAPH_ARCHIVE_PATH")
    return path or (Path(configured).expanduser() if configured else PROJECT_DATA / "rhyme_database.sqlite")


def _archive_candidates(query: str, limit: int, db_path: Path) -> tuple[list[dict], list[str]]:
    if not db_path.is_file():
        return [], ["Persönliche Reimbibliothek fehlt in dieser Arbeitskopie. Erst eigene Texte importieren."]

    # Use the same end-anchor family as the existing personal phrase library,
    # then score a bounded pool. Never send archive content to a remote service.
    from app.services.phrase_scorer import score_rhyme
    from app.services.user_text_importer import _terminal_family

    family = _terminal_family(query)
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        total = conn.execute("select count(*) from rhyme_units").fetchone()[0]
        rows = conn.execute(
            """select id, source_id, source_title, line_no, line_text, phrase
               from rhyme_units where terminal_vowel_family = ? order by id limit 180""",
            (family,),
        ).fetchall()
        rows += conn.execute(
            """select id, source_id, source_title, line_no, line_text, phrase
               from rhyme_units where terminal_vowel_family != ? order by id limit 60""",
            (family,),
        ).fetchall()
    except sqlite3.OperationalError:
        return [], ["Die lokale Bibliothek besitzt noch kein passendes Reimschema. Bitte erneut importieren."]
    finally:
        conn.close()

    ranked = []
    for row in rows:
        score = score_rhyme(query, row["phrase"])
        ranked.append((score.total, score.anchor, score.tail, row["id"], dict(row)))
    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    result, seen = [], set()
    for *_, row in ranked:
        key = (row["source_id"], row["line_no"])
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
        if len(result) >= limit:
            break
    warnings = []
    if total > len(rows):
        warnings.append(f"Archivsuche begrenzt: {len(rows)} von {total} Reimstellen vorgeprüft (Endanker zuerst).")
    if not result:
        warnings.append("Die persönliche Reimbibliothek enthält noch keine Reimstellen.")
    return result, warnings


def build_workspace_graph(request: WorkspaceRequest, archive_path: Path | None = None) -> dict:
    """Enrich input with real source lines, then return a reproducible snapshot."""
    text = request.text
    sources: dict[int, dict] = {}
    warnings: list[str] = []
    if request.include_library:
        query = request.library_query.strip() or next((line.strip() for line in text.splitlines() if line.strip()), "")
        candidates, warnings = _archive_candidates(query, request.library_limit, _archive_path(archive_path))
        existing = {line.strip().casefold() for line in text.split("\n")}
        for item in candidates:
            line = item["line_text"]
            if line.strip().casefold() in existing:
                continue
            # Keep all original blank lines and therefore override indices.
            # The core indexes LF, not Unicode/CR-only separators. Use exactly
            # the same convention so every source labels its real occurrence.
            separator = "" if not text or text.endswith("\n") else "\n"
            line_index = (text + separator).count("\n")
            candidate_text = text + separator + line
            if len(candidate_text) > 16000 or len(candidate_text.split("\n")) > 64:
                warnings.append("Weitere Archivstellen passen nicht in die begrenzte Arbeitsfläche (64 Zeilen / 16000 Zeichen).")
                break
            text = candidate_text
            existing.add(line.strip().casefold())
            sources[line_index] = {
                "kind": "library", "source_id": item["source_id"],
                "source_title": item["source_title"], "line_no": item["line_no"],
                "line_text": line, "unit_id": item["id"],
                "line_hash": hashlib.sha256(line.encode("utf-8")).hexdigest(),
            }
    core_request = GraphBuildRequest.model_validate({
        **request.model_dump(exclude={"include_library", "library_query", "library_limit"}),
        "text": text,
    })
    graph = build_rhyme_graph(core_request, sources=sources).model_dump(mode="json")
    graph["warnings"].extend(warnings)
    graph["fingerprint"] = hashlib.sha256(_json(graph).encode("utf-8")).hexdigest()
    return graph


class GraphWorkspaceStore:
    def __init__(self, path: Path | None = None):
        configured = os.environ.get("REIMGRAPH_DATA_DIR")
        self.path = path or (Path(configured).expanduser() if configured else PROJECT_DATA) / "reimgraph.sqlite"

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.executescript("""
            create table if not exists graph_sessions (
                id text primary key, title text not null,
                created_at text not null, updated_at text not null,
                request_json text not null, graph_json text not null,
                node_count integer not null, edge_count integer not null
            );
            create table if not exists graph_feedback_events (
                id integer primary key autoincrement,
                session_id text not null references graph_sessions(id),
                edge_id text not null, payload_json text not null, updated_at text not null
            );
            create index if not exists graph_feedback_session
                on graph_feedback_events(session_id, id);
        """)
        return conn

    def list_sessions(self) -> dict:
        if not self.path.is_file():
            return {"sessions": []}
        with closing(self._connect()) as conn, conn:
            rows = conn.execute("""select id,title,created_at,updated_at,node_count,edge_count
                from graph_sessions order by updated_at desc,id limit 100""").fetchall()
        return {"sessions": [dict(row) for row in rows]}

    def save(self, title: str, request: WorkspaceRequest, graph: dict) -> dict:
        session_id, timestamp = str(uuid4()), _now()
        with closing(self._connect()) as conn, conn:
            conn.execute("insert into graph_sessions values (?,?,?,?,?,?,?,?)", (
                session_id, title, timestamp, timestamp,
                _json(request.model_dump(mode="json")), _json(graph),
                len(graph["nodes"]), len(graph["edges"]),
            ))
        return self.load(session_id)

    def load(self, session_id: str) -> dict:
        if not self.path.is_file():
            raise KeyError(session_id)
        with closing(self._connect()) as conn, conn:
            row = conn.execute("select * from graph_sessions where id=?", (session_id,)).fetchone()
            if row is None:
                raise KeyError(session_id)
            events = conn.execute("select payload_json from graph_feedback_events where session_id=? order by id", (session_id,)).fetchall()
        history = [json.loads(event["payload_json"]) for event in events]
        latest = {item["edge_id"]: item for item in history}
        return {
            "id": row["id"], "title": row["title"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "request": json.loads(row["request_json"]), "graph": json.loads(row["graph_json"]),
            "feedback": list(latest.values()), "feedback_history": history,
        }

    def add_feedback(self, session_id: str, request: EdgeFeedbackRequest) -> dict:
        session = self.load(session_id)
        if request.edge_id not in {edge["id"] for edge in session["graph"]["edges"]}:
            raise ValueError("Die Beziehung gehört nicht zu diesem gespeicherten Graphen.")
        payload = {**request.model_dump(), "updated_at": _now()}
        with closing(self._connect()) as conn, conn:
            conn.execute("insert into graph_feedback_events (session_id,edge_id,payload_json,updated_at) values (?,?,?,?)", (
                session_id, request.edge_id, _json(payload), payload["updated_at"],
            ))
            conn.execute("update graph_sessions set updated_at=? where id=?", (payload["updated_at"], session_id))
        return payload


def load_source_context(source_id: str, line_no: int, db_path: Path | None = None, expected_line_hash: str | None = None) -> dict:
    path = _archive_path(db_path)
    if not path.is_file():
        raise KeyError(source_id)
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        doc = conn.execute("select * from documents where source_id=?", (source_id,)).fetchone()
        target = conn.execute("select text from lines where source_id=? and line_no=?", (source_id, line_no)).fetchone()
        if doc is None or target is None:
            raise KeyError(source_id)
        lines = conn.execute("select line_no,text from lines where source_id=? and line_no between ? and ? order by line_no", (
            source_id, max(1, line_no - 2), line_no + 2,
        )).fetchall()
        current_hash = hashlib.sha256(target["text"].encode("utf-8")).hexdigest()
        return {"source_id": source_id, "title": doc["title"], "path": doc["path"],
                "extraction_method": doc["extraction_method"], "status": doc["status"],
                "line_hash": current_hash,
                "matches_snapshot": current_hash == expected_line_hash if expected_line_hash else None,
                "line_no": line_no, "lines": [dict(line) for line in lines]}
    finally:
        conn.close()
