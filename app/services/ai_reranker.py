"""AI reranking layer for personal rhyme search using Gemini."""

import os
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

class RerankedCandidate(BaseModel):
    candidate_id: int = Field(description="The original candidate_id of the phrase.")
    score: float = Field(description="A score between 0.0 and 1.0 rating the phrase matching quality.")
    reason: str = Field(description="A short reason in German why this score was given, focusing on flow, syllables, and anchor.")

class RerankResponse(BaseModel):
    ranked: List[RerankedCandidate]
    notes: Optional[str] = Field(None, description="Any general notes about the ranking process.")

RERANKER_INSTRUCTIONS = """
Du bist ein Deutschrap-Reim-Reranker für eine persönliche Reim-Bibliothek.
Bewerte keine Rechtschreibung und keine optische Ähnlichkeit.

Priorität der Bewertung:
1. 3-8-silbige Phrase-Level-Endreimketten (besonders 4-6 Silben).
2. Starker Terminal-Endreim / Anchor-Match am hörbaren Ende.
3. Rhythmischer Grip, Kadenz, Betonungsgefühl, Flow-Dichte (ähnliche Silbenzahl wie Query).
4. Multi-Word-Phrasen vor isolierten Wörtern, wenn sie rap-tauglich sind.
5. Vokal-Spine nur als sekundärer Tiebreaker.

Du erhältst eine JSON-Liste mit Kandidaten und der Such-Query.
Bewerte jeden Kandidaten im Kontext der Query und weise ihm einen neuen Score (0.0 bis 1.0) zu.
Ein perfekter Reim auf "schattenkabinett" (5 Silben) wäre z.B. "wackeliges brett" (Score 1.0).
Ein langweiliger 1-Silber auf "-ett" wie "komplett" sollte maximal 0.4 erhalten.
"""

def rerank_with_gemini(query: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "enabled": False,
            "provider": "gemini",
            "warning": "GEMINI_API_KEY ist nicht gesetzt.",
            "results": candidates
        }

    if not HAS_GENAI:
        return {
            "enabled": False,
            "provider": "gemini",
            "warning": "google-genai Paket ist nicht installiert.",
            "results": candidates
        }

    client = genai.Client(api_key=api_key)

    payload = {
        "query": query,
        "candidates": [
            {
                "candidate_id": i,
                "phrase": c["phrase"],
                "syllable_count": c.get("syllable_count"),
                "word_count": len(str(c["phrase"]).split())
            }
            for i, c in enumerate(candidates)
        ]
    }

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=json.dumps(payload, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=RERANKER_INSTRUCTIONS,
                response_mime_type="application/json",
                response_schema=RerankResponse,
                temperature=0.2,
            )
        )

        parsed = json.loads(response.text)
        ranked = parsed.get("ranked", [])

        by_id = {idx: c for idx, c in enumerate(candidates)}
        used: set[int] = set()
        merged: List[Dict[str, Any]] = []

        # Sort by the LLM score descending
        ranked_sorted = sorted(ranked, key=lambda x: x.get("score", 0.0), reverse=True)

        for item in ranked_sorted:
            cid = item.get("candidate_id")
            if cid is not None and cid in by_id and cid not in used:
                enriched = dict(by_id[cid])
                enriched["llm_score"] = float(item.get("score", 0.0))
                enriched["llm_reason"] = str(item.get("reason", ""))[:240]
                merged.append(enriched)
                used.add(cid)

        # Append remaining untouched
        for i, c in enumerate(candidates):
            if i not in used:
                merged.append(c)

        return {
            "enabled": True,
            "provider": "gemini",
            "warning": "",
            "candidate_count": len(candidates),
            "results": merged
        }
    except Exception as exc:
        return {
            "enabled": True,
            "provider": "gemini",
            "warning": f"Gemini API Fehler: {exc}",
            "results": candidates
        }

def rerank_with_fake(query: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """A fake reranker for CI and testing purposes."""
    merged = []
    for i, c in enumerate(candidates):
        enriched = dict(c)
        enriched["llm_score"] = 0.99 if i == 0 else 0.5
        enriched["llm_reason"] = "Fake test reason"
        merged.append(enriched)
    return {
        "enabled": True,
        "provider": "fake",
        "warning": "",
        "candidate_count": len(candidates),
        "results": merged
    }

def rerank_rhymes(query: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    from dotenv import load_dotenv
    load_dotenv()

    provider = os.getenv("RHYME_RERANKER_PROVIDER", "").lower()

    if provider == "fake":
        return rerank_with_fake(query, candidates)

    if provider == "local":
        from app.services.local_rhyme_model import rerank_with_local_model
        return rerank_with_local_model(query, candidates)

    if os.getenv("GEMINI_API_KEY"):
        return rerank_with_gemini(query, candidates)

    from app.services.local_rhyme_model import load_local_rhyme_model, rerank_with_local_model
    if load_local_rhyme_model():
        return rerank_with_local_model(query, candidates)

    # Fallback to existing command reranker if any
    try:
        from app.services.rhyme_reranker import rerank_with_command
        return rerank_with_command(query, candidates)
    except ImportError:
        return {
            "enabled": False,
            "provider": "none",
            "warning": "Kein Reranker (Gemini / Command) konfiguriert.",
            "results": candidates
        }
