"""Optional AI reranking layer for personal rhyme search.

The Python scorer stays the fast retrieval layer. This module prepares a small,
privacy-conscious payload for an external LLM command and merges its ranking
back into the normal search response. The external command reads JSON on stdin
and writes JSON on stdout.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


RERANKER_INSTRUCTIONS = """
Du bist ein Deutschrap-Reim-Reranker fuer eine persoenliche Reim-Bibliothek.
Bewerte keine Rechtschreibung und keine optische Aehnlichkeit.

Prioritaet:
1. 3-8-silbige Phrase-Level-Endreimketten, besonders 4-6 Silben
2. starker Terminal-Endreim / Anchor-Match am hoerbaren Ende
3. rhythmischer Grip, Kadenz, Betonungsgefuehl, Flow-Dichte
4. Multi-Word-Phrasen vor isolierten Woertern, wenn sie rap-tauglich sind
5. Vokal-Spine nur als sekundaeren Tiebreaker

Antwortformat als reines JSON:
{
  "ranked": [
    {"candidate_id": 12, "score": 0.97, "reason": "kurzer Grund"}
  ],
  "notes": "optional"
}
""".strip()


@dataclass
class RerankConfig:
    command: Optional[str]
    timeout_seconds: float = 20.0
    include_context: bool = False


def load_rerank_config() -> RerankConfig:
    timeout_raw = os.getenv("RHYME_RERANKER_TIMEOUT_SECONDS", "20")
    try:
        timeout_seconds = max(1.0, min(float(timeout_raw), 120.0))
    except ValueError:
        timeout_seconds = 20.0
    return RerankConfig(
        command=os.getenv("RHYME_RERANKER_COMMAND"),
        timeout_seconds=timeout_seconds,
        include_context=os.getenv("RHYME_RERANKER_INCLUDE_CONTEXT") == "1",
    )


def _candidate_payload(candidate_id: int, row: Dict[str, Any], include_context: bool) -> Dict[str, Any]:
    payload = {
        "candidate_id": candidate_id,
        "phrase": row["phrase"],
        "score": row["score"],
        "raw_score": row.get("raw_score", row["score"]),
        "anchor": row.get("anchor"),
        "tail": row.get("tail"),
        "vowel": row.get("vowel"),
        "cadence": row.get("cadence"),
        "syllable_count": row.get("syllable_count"),
        "word_count": len(str(row["phrase"]).split()),
        "reason": row.get("reason", ""),
    }
    if include_context:
        payload["source_title"] = row.get("source_title", "")
        payload["line_no"] = row.get("line_no")
        payload["line_text"] = row.get("line_text", "")
    return payload


def build_rerank_payload(
    query: str,
    candidates: List[Dict[str, Any]],
    include_context: bool = False,
) -> Dict[str, Any]:
    return {
        "instructions": RERANKER_INSTRUCTIONS,
        "query": query,
        "privacy": {
            "line_context_included": include_context,
            "default_policy": "Send phrase-level candidates only; no full private text context.",
        },
        "candidates": [
            _candidate_payload(candidate_id, candidate, include_context)
            for candidate_id, candidate in enumerate(candidates)
        ],
    }


def _parse_reranker_response(stdout: str) -> List[Dict[str, Any]]:
    data = json.loads(stdout)
    ranked = data.get("ranked")
    if not isinstance(ranked, list):
        raise ValueError("reranker response must contain a ranked list")
    parsed: List[Dict[str, Any]] = []
    for item in ranked:
        if not isinstance(item, dict):
            continue
        candidate_id = item.get("candidate_id")
        if not isinstance(candidate_id, int):
            continue
        score = item.get("score", 0.0)
        try:
            score_float = max(0.0, min(float(score), 1.0))
        except (TypeError, ValueError):
            score_float = 0.0
        parsed.append(
            {
                "candidate_id": candidate_id,
                "llm_score": round(score_float, 4),
                "llm_reason": str(item.get("reason", ""))[:240],
            }
        )
    return parsed


def rerank_with_command(
    query: str,
    candidates: List[Dict[str, Any]],
    config: Optional[RerankConfig] = None,
) -> Dict[str, Any]:
    config = config or load_rerank_config()
    if not config.command:
        return {
            "enabled": False,
            "provider": "none",
            "warning": "RHYME_RERANKER_COMMAND ist nicht gesetzt.",
            "results": candidates,
        }

    payload = build_rerank_payload(query, candidates, include_context=config.include_context)
    try:
        completed = subprocess.run(
            shlex.split(config.command),
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
            check=False,
        )
    except Exception as exc:
        return {
            "enabled": True,
            "provider": "command",
            "warning": f"Reranker konnte nicht ausgefuehrt werden: {exc}",
            "results": candidates,
        }

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[:300]
        return {
            "enabled": True,
            "provider": "command",
            "warning": f"Reranker exit {completed.returncode}: {detail}",
            "results": candidates,
        }

    try:
        ranked = _parse_reranker_response(completed.stdout)
    except Exception as exc:
        return {
            "enabled": True,
            "provider": "command",
            "warning": f"Reranker-Antwort ungueltig: {exc}",
            "results": candidates,
        }

    by_id = {idx: candidate for idx, candidate in enumerate(candidates)}
    used: set[int] = set()
    merged: List[Dict[str, Any]] = []
    for item in ranked:
        candidate_id = item["candidate_id"]
        candidate = by_id.get(candidate_id)
        if candidate is None or candidate_id in used:
            continue
        enriched = dict(candidate)
        enriched["llm_score"] = item["llm_score"]
        enriched["llm_reason"] = item["llm_reason"]
        merged.append(enriched)
        used.add(candidate_id)

    # Keep deterministic retrieval order for candidates the LLM did not mention.
    for candidate_id, candidate in enumerate(candidates):
        if candidate_id not in used:
            merged.append(candidate)

    return {
        "enabled": True,
        "provider": "command",
        "warning": "",
        "candidate_count": len(candidates),
        "results": merged,
    }
