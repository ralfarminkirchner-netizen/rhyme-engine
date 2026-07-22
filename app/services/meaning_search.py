"""
meaning_search.py — Lokale, private BEDEUTUNGS-/Themensuche.

Getrennte Achse vom Reim-Ranking ("einmal nach Reimen, einmal nach Bedeutung").
Findet thematisch verwandte Zeilen im eigenen Korpus per TF-IDF + Cosinus.

Designprinzipien:
- STRIKT getrennt vom Reim-Scoring. Diese Funktion kennt keine Phonetik, kein
  Reim-Anker. So kann kein "semantic drift" das Reim-Ranking verfaelschen.
- LOKAL & PRIVAT: kein externer API-Call, keine Embeddings-Abhaengigkeit. Reines
  TF-IDF ueber den importierten Textkorpus (sqlite text_entries).
- Baseline: erfasst lexikalisch-thematische Naehe (gleiche/verwandte Woerter),
  noch keine Synonyme/Metaphern — dafuer waere ein optionales Embedding-Modell
  noetig (separat zuschaltbar).
"""
from __future__ import annotations

import math
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from app.services.user_text_importer import DB_PATH, WORD_RE

# Kompakte deutsche Funktionswort-Stoppliste (Themen-Signal statt Grammatik).
STOPWORDS = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem",
    "einer", "eines", "und", "oder", "aber", "doch", "denn", "weil", "dass",
    "ob", "wie", "wenn", "als", "auch", "nur", "noch", "schon", "mal", "so",
    "im", "in", "an", "auf", "aus", "bei", "mit", "nach", "von", "vor", "zu",
    "zur", "zum", "um", "ueber", "über", "unter", "durch", "gegen", "ohne",
    "ich", "du", "er", "sie", "es", "wir", "ihr", "mich", "dich", "sich",
    "mir", "dir", "uns", "euch", "mein", "dein", "sein", "ihre", "unser",
    "ist", "bin", "bist", "sind", "war", "warst", "waren", "hat", "habe",
    "hast", "haben", "hatte", "wird", "werden", "kann", "muss", "will",
    "nicht", "kein", "keine", "ja", "nein", "man", "wer", "was", "wo",
    "hier", "da", "dort", "dann", "jetzt", "immer", "nie", "sehr", "mehr",
    "schon", "wieder", "etwas", "alle", "alles", "dieser", "diese", "dieses",
}


def _tokens(text: str) -> List[str]:
    norm = unicodedata.normalize("NFKC", text or "").lower()
    return [t for t in WORD_RE.findall(norm) if len(t) > 1 and t not in STOPWORDS]


def _norm_key(text: str) -> str:
    return " ".join(WORD_RE.findall(unicodedata.normalize("NFKC", text or "").lower()))


def search_meaning(
    query: str,
    db_path: Path = DB_PATH,
    limit: int = 25,
    min_score: float = 0.0,
) -> Dict[str, Any]:
    if not db_path.exists():
        return {"query": query, "results": [], "warning": "Textbibliothek fehlt. Erst importieren."}

    q_tokens = _tokens(query)
    if not q_tokens:
        return {"query": query, "results": [], "total_candidates": 0,
                "warning": "Query enthaelt nur Stopp-/Kurzwoerter."}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "select source_title, line_no, text from text_entries where word_count >= 2"
        ).fetchall()
    finally:
        conn.close()

    docs: List[Dict[str, Any]] = []
    df: Counter = Counter()
    for row in rows:
        toks = _tokens(row["text"])
        if not toks:
            continue
        tf = Counter(toks)
        docs.append({"row": row, "tf": tf})
        for term in tf:
            df[term] += 1

    n_docs = len(docs)
    if n_docs == 0:
        return {"query": query, "results": [], "total_candidates": 0}

    idf = {term: math.log(1.0 + n_docs / (1 + df.get(term, 0))) for term in set(q_tokens) | set(df)}

    # Query-Vektor
    q_tf = Counter(q_tokens)
    q_vec = {t: q_tf[t] * idf.get(t, 0.0) for t in q_tf}
    q_norm = math.sqrt(sum(w * w for w in q_vec.values())) or 1.0

    scored: List[Dict[str, Any]] = []
    seen: set = set()
    for doc in docs:
        tf = doc["tf"]
        # Dot-Produkt nur ueber Query-Terme (uebrige tragen 0 bei).
        dot = sum(q_vec[t] * (tf.get(t, 0) * idf.get(t, 0.0)) for t in q_vec)
        if dot <= 0:
            continue
        d_norm = math.sqrt(sum((c * idf.get(t, 0.0)) ** 2 for t, c in tf.items())) or 1.0
        cos = dot / (q_norm * d_norm)
        if cos < min_score:
            continue
        row = doc["row"]
        key = _norm_key(row["text"])
        if key in seen:
            continue
        seen.add(key)
        scored.append({
            "text": row["text"],
            "score": round(cos, 4),
            "source_title": row["source_title"],
            "line_no": row["line_no"],
            "matched_terms": sorted(t for t in q_vec if tf.get(t, 0) > 0),
        })

    scored.sort(key=lambda d: d["score"], reverse=True)
    return {
        "query": query,
        "results": scored[:limit],
        "total_candidates": n_docs,
        "axis": "meaning",
        "method": "tfidf",
    }
