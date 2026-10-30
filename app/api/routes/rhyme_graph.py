"""Offline rhyme graph API. No external model calls or implicit acceptance."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.services.rhyme_graph_workspace import (
    EdgeFeedbackRequest, GraphWorkspaceStore, SaveGraphRequest, WorkspaceRequest,
    build_workspace_graph, load_source_context,
)

router = APIRouter(prefix="/api/rhymes/graph", tags=["rhyme-graph"])


@router.post("/build")
def build(request: WorkspaceRequest):
    try:
        return build_workspace_graph(request)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/sessions")
def sessions():
    return GraphWorkspaceStore().list_sessions()


@router.post("/sessions", status_code=201)
def save(request: SaveGraphRequest):
    try:
        graph = build_workspace_graph(request.request)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    if request.expected_graph_fingerprint and request.expected_graph_fingerprint != graph["fingerprint"]:
        raise HTTPException(409, "Die Analyse oder Archivgrundlage hat sich geändert. Bitte den Graphen neu aufbauen und prüfen.")
    return GraphWorkspaceStore().save(request.title, request.request, graph)


@router.get("/sessions/{session_id}")
def load(session_id: str):
    try:
        return GraphWorkspaceStore().load(session_id)
    except KeyError as error:
        raise HTTPException(404, "Gespeicherter Graph nicht gefunden.") from error


@router.post("/sessions/{session_id}/feedback", status_code=201)
def feedback(session_id: str, request: EdgeFeedbackRequest):
    try:
        return GraphWorkspaceStore().add_feedback(session_id, request)
    except KeyError as error:
        raise HTTPException(404, "Gespeicherter Graph nicht gefunden.") from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/sources/{source_id}")
def source(source_id: str, line_no: int = Query(ge=1), expected_line_hash: Optional[str] = Query(None, pattern=r"^[a-f0-9]{64}$")):
    try:
        return load_source_context(source_id, line_no, expected_line_hash=expected_line_hash)
    except KeyError as error:
        raise HTTPException(404, "Originalstelle nicht mehr in der lokalen Bibliothek vorhanden. Der gespeicherte Graph behält seinen Quellausschnitt.") from error
