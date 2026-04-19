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
