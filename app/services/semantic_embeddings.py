"""
semantic_embeddings.py — Lokale Bedeutungssuche per Satz-Embeddings (optional).

Hebt die Bedeutungs-Achse von rein lexikalisch (TF-IDF) auf SEMANTISCH:
findet thematisch verwandte Zeilen auch ohne Wort-Ueberlappung
(schmerz -> Leid/Wunde/Trauer).

Eigenschaften:
- LOKAL & PRIVAT: Modell laeuft offline auf der Maschine, kein externer API-Call.
- HARTER FALLBACK: ohne `sentence-transformers`/`numpy` -> is_available()=False,
  der Aufrufer nutzt dann TF-IDF. Bricht nie.
- Embeddings werden EINMAL berechnet und gecacht (Hash ueber den Korpus); bei
  Aenderung automatisch neu.
- Getrennte Achse — kein Einfluss aufs Reim-Ranking.
"""
from __future__ import annotations

import hashlib
import os
import pickle
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.user_text_importer import DATA_ROOT, DB_PATH, WORD_RE


def _meaningful(text: str) -> bool:
    """Filtert kaputte Extraktions-Fragmente ('er mend', 'hte n', 'ie hartA')."""
    toks = WORD_RE.findall(text or "")
    if not toks:
        return False
    long_toks = [t for t in toks if len(t) >= 4]
    # Echte Sprache hat lange Woerter. Leerzeichen-zerbrochene Extraktions-
    # Fragmente ("Tä ter in tro jek te", "ei ne aus") haben fast nur Kurz-Tokens.
    if len(long_toks) >= 2:
        return True
    if len(toks) == 1 and len(toks[0]) >= 8:
        return True
    return False

MODEL_NAME = os.getenv(
    "RHYME_EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
CACHE_PATH = DATA_ROOT / "semantic_cache.pkl"

_model = None
_available: Optional[bool] = None


def is_available() -> bool:
    """True, wenn sentence-transformers + numpy importierbar sind."""
    global _available
    if _available is None:
        try:
            import numpy  # noqa: F401
            import sentence_transformers  # noqa: F401

            _available = True
        except Exception:
            _available = False
    return bool(_available)


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _corpus_rows(db_path: Path) -> List[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "select source_title, line_no, text from text_entries where word_count >= 2"
        ).fetchall()
    finally:
        conn.close()


def _corpus_hash(texts: List[str]) -> str:
    h = hashlib.md5()
    h.update(MODEL_NAME.encode("utf-8"))
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def build_index(db_path: Path = DB_PATH, cache_path: Path = CACHE_PATH, force: bool = False) -> Dict[str, Any]:
    """Berechnet & cacht Embeddings fuer alle Korpus-Zeilen."""
    if not is_available():
        return {"status": "unavailable", "warning": "sentence-transformers nicht installiert."}
    if not db_path.exists():
        return {"status": "missing_database"}

    import numpy as np

    rows = [r for r in _corpus_rows(db_path) if _meaningful(r["text"])]
    texts = [r["text"] for r in rows]
    if not texts:
        return {"status": "empty", "count": 0}
    digest = _corpus_hash(texts)

    if not force and cache_path.exists():
        try:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
            if cached.get("hash") == digest:
                return {"status": "ok", "count": len(texts), "cached": True}
        except Exception:
            pass

    model = _get_model()
    emb = model.encode(texts, normalize_embeddings=True, batch_size=64, show_progress_bar=False)
    # Entartete Zeilen (leer/nur Satzzeichen) koennen Null-/NaN-Vektoren liefern,
    # die die Cosinus-Matrix vergiften -> hart auf 0 saeubern.
    emb = np.nan_to_num(np.asarray(emb, dtype="float32"), nan=0.0, posinf=0.0, neginf=0.0)
    meta = [{"text": r["text"], "source_title": r["source_title"], "line_no": r["line_no"]} for r in rows]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump({"hash": digest, "meta": meta, "emb": emb}, f)
    return {"status": "ok", "count": len(texts), "cached": False}


def search_semantic(
    query: str,
    db_path: Path = DB_PATH,
    cache_path: Path = CACHE_PATH,
    limit: int = 25,
    min_score: float = 0.0,
) -> Dict[str, Any]:
    """Semantische Bedeutungssuche. Gibt enabled=False zurueck, wenn Modell fehlt."""
    if not is_available():
        return {"enabled": False, "query": query, "results": [],
                "warning": "Embedding-Modell nicht installiert (Fallback: TF-IDF)."}
    # Einzelwort-Queries sind als Satz-Embedding instabil -> lexikalischer
    # TF-IDF-Fallback (findet das Wort direkt) ist hier zuverlaessiger.
    if len([t for t in WORD_RE.findall(query) if len(t) >= 2]) < 2:
        return {"enabled": False, "query": query, "results": [],
                "warning": "Einzelwort -> TF-IDF-Fallback (semantisch ab 2 Woertern)."}
    if not db_path.exists():
        return {"enabled": True, "query": query, "results": [], "warning": "Textbibliothek fehlt."}

    import numpy as np

    build_index(db_path=db_path, cache_path=cache_path)
    try:
        with open(cache_path, "rb") as f:
            cache = pickle.load(f)
    except Exception:
        return {"enabled": True, "query": query, "results": [], "warning": "Index nicht ladbar."}

    emb = np.nan_to_num(cache["emb"], nan=0.0, posinf=0.0, neginf=0.0)
    meta = cache["meta"]
    model = _get_model()
    q = model.encode([query], normalize_embeddings=True)
    q = np.nan_to_num(np.asarray(q, dtype="float32")[0], nan=0.0, posinf=0.0, neginf=0.0)
    with np.errstate(all="ignore"):  # macOS-BLAS sendet spurious matmul-Warnungen
        sims = np.nan_to_num(emb @ q, nan=-1.0)  # Cosinus (alles normalisiert)

    order = np.argsort(-sims)
    results: List[Dict[str, Any]] = []
    seen: set = set()
    for idx in order:
        score = float(sims[idx])
        if score < min_score:
            break
        m = meta[idx]
        key = m["text"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "text": m["text"],
            "score": round(score, 4),
            "source_title": m["source_title"],
            "line_no": m["line_no"],
        })
        if len(results) >= limit:
            break

    return {"enabled": True, "query": query, "axis": "meaning", "method": "embeddings",
            "model": MODEL_NAME, "total_candidates": len(meta), "results": results}
