from fastapi import APIRouter, HTTPException
from app.schemas.rhyme import (
    AnalyzeRequest, SearchRequest, SearchResponse,
    PhoneticFeatures, ModesResponse,
)
from app.services.parser import parse_german_word

router = APIRouter(prefix="/api/rhymes", tags=["rhymes"])

# Engine wird von main.py gesetzt
_engine = None

def set_engine(engine):
    global _engine
    _engine = engine


@router.get("/health")
async def health():
    return {"status": "ok", "words_loaded": len(_engine.word_list) if _engine else 0}


@router.get("/modes", response_model=ModesResponse)
async def modes():
    if not _engine:
        raise HTTPException(503, "Engine not initialised")
    return _engine.get_modes()


@router.post("/analyze", response_model=PhoneticFeatures)
async def analyze(request: AnalyzeRequest):
    try:
        parsed = parse_german_word(request.word)
        return PhoneticFeatures.from_parsed(parsed)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    if not _engine:
        raise HTTPException(503, "Engine not initialised")
    try:
        parsed = parse_german_word(request.query)
        return _engine.search(
            query          = parsed,
            mode           = request.mode,
            custom_weights = request.weights,
            limit          = request.limit,
            include_debug  = request.debug,
        )
    except Exception as e:
        raise HTTPException(400, str(e))


# ── Phrase Scorer Endpoint ────────────────────────────────────────────────────

from pathlib import Path

from pydantic import BaseModel, Field
from typing import List

class PhraseRankRequest(BaseModel):
    query: str
    candidates: List[str]

class PhraseRankResult(BaseModel):
    phrase: str
    score: float
    anchor: float
    tail: float
    vowel: float
    cadence: float
    anchor_gated: bool
    suffix_penalized: bool
    reason: str

class PhraseRankResponse(BaseModel):
    query: str
    ranked: List[PhraseRankResult]


class TextAnalysisRequest(BaseModel):
    text: str


class RhymeHighlightRequest(BaseModel):
    text: str
    context_radius: int = Field(6, ge=0, le=32)


class UserTextImportRequest(BaseModel):
    prefer_pages_export: bool = True
    context_radius: int = Field(12, ge=1, le=64)


class UserTextSearchRequest(BaseModel):
    query: str
    limit: int = Field(30, ge=1, le=100)
    min_score: float = Field(0.0, ge=0.0, le=1.0)
    rerank: bool = False
    rerank_candidate_count: int = Field(120, ge=1, le=250)
    include_context_in_rerank: bool = False


@router.post("/rank-phrases", response_model=PhraseRankResponse)
async def rank_phrases(request: PhraseRankRequest):
    """
    Rankt Kandidaten-Phrasen als Reime zur Query-Phrase.
    Nutzt End-Anker-basierten Scorer (keine globale Vokal-Ähnlichkeit).
    """
    try:
        from app.services.phrase_scorer import rank_rhymes
        ranked = rank_rhymes(request.query, request.candidates)
        return PhraseRankResponse(
            query=request.query,
            ranked=[
                PhraseRankResult(
                    phrase=r.phrase,
                    score=r.total,
                    anchor=r.anchor,
                    tail=r.tail,
                    vowel=r.vowel,
                    cadence=r.cadence,
                    anchor_gated=r.anchor_gated,
                    suffix_penalized=r.suffix_penalized,
                    reason=r.reason,
                )
                for r in ranked
            ],
        )
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/analyze-text")
async def analyze_text(request: TextAnalysisRequest):
    """Analysiert einen kompletten Rap-/Songtext auf Reim- und Tiefenstrukturen."""
    try:
        from dataclasses import asdict
        from app.services.rap_text_analyzer import analyze_rap_text

        return asdict(analyze_rap_text(request.text))
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/highlight-rhymes")
async def highlight_rhymes(request: RhymeHighlightRequest):
    """Markiert reimende Silben im kompletten Text mit stabilen Farbgruppen."""
    try:
        from dataclasses import asdict
        from app.services.rhyme_highlighter import highlight_rhyme_syllables

        return asdict(highlight_rhyme_syllables(request.text, request.context_radius))
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/training/raki-dich")
async def raki_dich_training_text():
    path = Path("app/data/training/raki_dich_lyric.txt")
    if not path.exists():
        raise HTTPException(404, "RAKi-DiCH fixture not found")
    return {"text": path.read_text("utf-8")}


@router.get("/user-texts/summary")
async def user_texts_summary():
    """Status der lokalen Reimdatenbank aus den User-Texten."""
    try:
        from app.services.user_text_importer import load_user_text_summary

        return load_user_text_summary()
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/user-texts/import")
async def import_user_texts(request: UserTextImportRequest):
    """Importiert Pages/TXT-Dateien aus app/data/user_texts/inbox."""
    try:
        from dataclasses import asdict
        from app.services.user_text_importer import refresh_user_text_database

        return asdict(
            refresh_user_text_database(
                prefer_pages_export=request.prefer_pages_export,
                context_radius=request.context_radius,
            )
        )
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/user-texts/search")
async def search_user_texts(request: UserTextSearchRequest):
    """Rankt Reim-Units aus der User-Datenbank gegen eine Query-Phrase."""
    try:
        from app.services.user_text_importer import search_user_rhymes

        return search_user_rhymes(
            query=request.query,
            limit=request.limit,
            min_score=request.min_score,
            rerank=request.rerank,
            rerank_candidate_count=request.rerank_candidate_count,
            include_context_in_rerank=request.include_context_in_rerank,
        )
    except Exception as e:
        raise HTTPException(400, str(e))
