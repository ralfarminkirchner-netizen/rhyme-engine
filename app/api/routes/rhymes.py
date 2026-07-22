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
from typing import List, Optional

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
    include_dictionary: bool = False
    dictionary_sources: Optional[List[str]] = None


class UserLibrarySearchRequest(BaseModel):
    query: str
    limit: int = Field(30, ge=1, le=100)
    min_score: float = Field(0.0, ge=0.0, le=1.0)


class UserMeaningSearchRequest(BaseModel):
    query: str
    limit: int = Field(25, ge=1, le=100)
    min_score: float = Field(0.0, ge=0.0, le=1.0)


class UserLibraryListRequest(BaseModel):
    limit: int = Field(500, ge=1, le=5000)


class UserRhymeFeedbackRequest(BaseModel):
    query: str
    source_title: str
    line_no: int = Field(..., ge=0)
    phrase: str
    rating: int = Field(..., ge=0, le=10)
    comment: str = Field("", max_length=2000)


class UserTrainingBuildRequest(BaseModel):
    max_examples: int = Field(2000, ge=1, le=50000)
    include_text_lines: bool = True


class UserModelTrainRequest(BaseModel):
    min_pair_score: float = Field(0.58, ge=0.0, le=1.0)


class UserPipelineRunRequest(BaseModel):
    query: str = "schattenkabinett"
    prefer_pages_export: bool = True
    context_radius: int = Field(12, ge=1, le=64)
    max_examples: int = Field(2000, ge=1, le=50000)
    min_pair_score: float = Field(0.58, ge=0.0, le=1.0)
    limit: int = Field(25, ge=1, le=100)
    min_score: float = Field(0.40, ge=0.0, le=1.0)


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
            include_dictionary=request.include_dictionary,
            dictionary_sources=request.dictionary_sources,
        )
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/user-texts/search-lines")
async def search_user_text_lines(request: UserLibrarySearchRequest):
    """Durchsucht die importierte Textbibliothek nach Zeilen und Fragmenten."""
    try:
        from app.services.user_text_importer import search_text_library

        return search_text_library(
            query=request.query,
            limit=request.limit,
        )
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/user-texts/feedback")
async def save_user_rhyme_feedback(request: UserRhymeFeedbackRequest):
    """Speichert lokale 0-10-Bewertungen fuer Reimtreffer."""
    try:
        from app.services.user_text_importer import save_rhyme_feedback

        return save_rhyme_feedback(
            query=request.query,
            source_title=request.source_title,
            line_no=request.line_no,
            phrase=request.phrase,
            rating=request.rating,
            comment=request.comment,
        )
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/user-texts/search-meaning")
async def search_user_meaning(request: UserMeaningSearchRequest):
    """BEDEUTUNGS-Achse: thematisch verwandte Zeilen (lokal, kein Reim).

    Nutzt Satz-Embeddings (semantisch, findet auch Synonyme/Metaphern), wenn
    `sentence-transformers` installiert ist — sonst Fallback auf TF-IDF.
    """
    try:
        from app.services.semantic_embeddings import is_available, search_semantic

        if is_available():
            res = search_semantic(
                query=request.query, limit=request.limit, min_score=request.min_score
            )
            if res.get("enabled"):
                return res

        from app.services.meaning_search import search_meaning

        return search_meaning(
            query=request.query,
            limit=request.limit,
            min_score=request.min_score,
        )
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/user-texts/search-quotes")
async def search_user_quotes(request: UserLibrarySearchRequest):
    """Rankt quotierbare Zeilen aus der lokalen Quote-Bibliothek."""
    try:
        from app.services.user_text_importer import search_quote_library

        return search_quote_library(
            query=request.query,
            limit=request.limit,
            min_score=request.min_score,
        )
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/user-texts/library")
async def load_user_library(request: UserLibraryListRequest):
    """Laedt alle lokalen Bibliothekslisten: Texte, Reim-Units, Reimpaare, Quotes."""
    try:
        from app.services.user_text_importer import load_full_user_library

        return load_full_user_library(limit=request.limit)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/user-texts/build-training")
async def build_user_training(request: UserTrainingBuildRequest):
    """Erzeugt lokal ignorierte JSONL-Trainingsbeispiele aus User-Bibliotheken."""
    try:
        from app.services.user_text_importer import build_training_dataset

        return build_training_dataset(
            max_examples=request.max_examples,
            include_text_lines=request.include_text_lines,
        )
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/user-texts/train-local-model")
async def train_user_local_model(request: UserModelTrainRequest):
    """Kalibriert ein lokales, git-ignoriertes Reimranking-Modell."""
    try:
        from app.services.local_rhyme_model import train_local_rhyme_model

        return train_local_rhyme_model(min_pair_score=request.min_pair_score)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/user-texts/pipeline")
async def run_user_pipeline(request: UserPipelineRunRequest):
    """Importiert, exportiert Trainingsdaten, trainiert lokal und sucht trainiert."""
    try:
        from app.services.personal_rhyme_pipeline import run_personal_rhyme_pipeline

        return run_personal_rhyme_pipeline(
            query=request.query,
            prefer_pages_export=request.prefer_pages_export,
            context_radius=request.context_radius,
            max_examples=request.max_examples,
            min_pair_score=request.min_pair_score,
            limit=request.limit,
            min_score=request.min_score,
        )
    except Exception as e:
        raise HTTPException(400, str(e))
