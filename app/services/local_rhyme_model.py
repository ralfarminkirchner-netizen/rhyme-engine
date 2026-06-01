"""Local private training and reranking for personal rhyme search."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from statistics import median
from typing import Any, Dict, List

from app.services.user_text_importer import DB_PATH, TRAINING_DIR, WORD_RE


MODEL_PATH = TRAINING_DIR / "local_rhyme_model.json"
FEATURES = ("anchor", "tail", "vowel", "cadence")


def _normalize_weights(raw: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, raw.get(feature, 0.0)) for feature in FEATURES)
    if total <= 0:
        return {"anchor": 0.42, "tail": 0.28, "vowel": 0.12, "cadence": 0.18}
    return {
        feature: round(max(0.0, raw.get(feature, 0.0)) / total, 4)
        for feature in FEATURES
    }


def _fit_score(query_syllables: int, candidate_syllables: int) -> float:
    diff = abs(query_syllables - candidate_syllables)
    if diff == 0:
        return 1.0
    if diff == 1:
        return 0.88
    if diff == 2:
        return 0.70
    if diff == 3:
        return 0.52
    return 0.35


def train_local_rhyme_model(
    db_path: Path = DB_PATH,
    model_path: Path = MODEL_PATH,
    min_pair_score: float = 0.58,
) -> Dict[str, Any]:
    if not db_path.exists():
        return {
            "status": "missing_database",
            "model_path": str(model_path),
            "pair_count": 0,
            "warning": "Reimdatenbank fehlt. Erst importieren.",
        }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            select p.score, p.anchor, p.tail, p.vowel, p.cadence,
                   l.syllable_count as left_syllables,
                   r.syllable_count as right_syllables
            from rhyme_pairs p
            join rhyme_units l on l.id = p.left_unit_id
            join rhyme_units r on r.id = p.right_unit_id
            where p.score >= ?
            order by p.score desc
            """,
            (min_pair_score,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {
            "status": "no_training_pairs",
            "model_path": str(model_path),
            "pair_count": 0,
            "warning": "Keine starken Reimpaare zum Trainieren gefunden.",
        }

    weighted: Dict[str, float] = {feature: 0.0 for feature in FEATURES}
    syllable_counts: List[int] = []
    for row in rows:
        pair_weight = max(0.0, float(row["score"]))
        for feature in FEATURES:
            weighted[feature] += max(0.0, float(row[feature])) * pair_weight
        syllable_counts.extend([int(row["left_syllables"]), int(row["right_syllables"])])

    weights = _normalize_weights(weighted)
    ideal_syllables = int(round(median(syllable_counts))) if syllable_counts else 5
    model = {
        "version": 1,
        "pair_count": len(rows),
        "min_pair_score": min_pair_score,
        "weights": weights,
        "ideal_syllables": max(3, min(8, ideal_syllables)),
        "policy": {
            "terminal_anchor_first": True,
            "phrase_window": "3-8 syllables",
            "privacy": "local model only; no private lines are uploaded",
        },
    }

    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return {
        "status": "ok",
        "model_path": str(model_path),
        "pair_count": len(rows),
        "weights": weights,
        "ideal_syllables": model["ideal_syllables"],
        "warning": "",
    }


def load_local_rhyme_model(model_path: Path = MODEL_PATH) -> Dict[str, Any] | None:
    if not model_path.exists():
        return None
    model = json.loads(model_path.read_text("utf-8"))
    if not isinstance(model, dict) or "weights" not in model:
        return None
    return model


def rerank_with_local_model(
    query: str,
    candidates: List[Dict[str, Any]],
    model_path: Path = MODEL_PATH,
) -> Dict[str, Any]:
    model = load_local_rhyme_model(model_path)
    if not model:
        return {
            "enabled": False,
            "provider": "local",
            "warning": "Lokales Reimmodell fehlt. Erst Training bauen.",
            "results": candidates,
        }

    weights = _normalize_weights(model.get("weights", {}))
    ideal_syllables = int(model.get("ideal_syllables", 5))
    query_words = len(WORD_RE.findall(query))
    query_syllables = max(3, min(8, query_words * 2)) if query_words else ideal_syllables

    reranked: List[Dict[str, Any]] = []
    for candidate in candidates:
        syllables = int(candidate.get("syllable_count") or ideal_syllables)
        feature_score = sum(
            float(candidate.get(feature) or 0.0) * weight
            for feature, weight in weights.items()
        )
        syllable_fit = _fit_score(query_syllables, syllables)
        phrase_window = 1.0 if 3 <= syllables <= 8 else 0.40
        multi_word = 1.0 if len(WORD_RE.findall(str(candidate.get("phrase", "")))) > 1 else 0.72
        learned_score = round(
            min(0.9999, (feature_score * 0.72) + (syllable_fit * 0.16) + (phrase_window * 0.08) + (multi_word * 0.04)),
            4,
        )
        enriched = dict(candidate)
        enriched["learned_score"] = learned_score
        enriched["learned_reason"] = (
            f"lokal trainiert: anchor {weights['anchor']:.2f}, "
            f"tail {weights['tail']:.2f}, cadence {weights['cadence']:.2f}"
        )
        reranked.append(enriched)

    reranked.sort(
        key=lambda item: (
            item.get("learned_score", 0.0),
            item.get("score", 0.0),
            item.get("anchor", 0.0),
            item.get("tail", 0.0),
        ),
        reverse=True,
    )
    return {
        "enabled": True,
        "provider": "local",
        "warning": "",
        "candidate_count": len(candidates),
        "model_pair_count": model.get("pair_count", 0),
        "weights": weights,
        "results": reranked,
    }
