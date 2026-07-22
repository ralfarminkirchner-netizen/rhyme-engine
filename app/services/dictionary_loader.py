"""
dictionary_loader.py — Zusaetzliche Reim-Woerterbuecher (lokal, privat).

Erweitert die Reimsuche ueber den EIGENEN Korpus hinaus: kuratierte/--externe
Wortlisten (eine Datei = eine Quelle, z.B. "philosophie", "ontologie",
"spiritualitaet", "allgemein") werden in eine eigene Tabelle geladen und bei der
Suche zusaetzlich gescort.

Eigenschaften:
- Eigene Tabelle `dictionary_entries`; wird bei Personal-Reimport NICHT gedroppt
  (analog zu rhyme_feedback). Eigener Import-Lauf.
- Treffer werden mit Quelle markiert ("source_title" = "[WB] <name>"), damit das
  UI Woerterbuch-Treffer von eigenen Zeilen unterscheiden kann.
- Rein lokal, keine KI, kein externer Call.
"""
from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path
from typing import Any, Dict, List

from app.services.parser import parse_german_word
from app.services.phrase_scorer import PhraseFeatures, score_rhyme
from app.services.user_text_importer import DATA_ROOT, DB_PATH, WORD_RE

DICTIONARY_DIR = DATA_ROOT / "dictionaries"
SOURCE_PREFIX = "[WB] "


def ensure_dictionary_schema(conn: sqlite3.Connection) -> None:
    # Migration: alte Tabelle ohne terminal_family verwerfen (regenerierbar aus .txt).
    cols = [r[1] for r in conn.execute("pragma table_info(dictionary_entries)").fetchall()]
    if cols and "terminal_family" not in cols:
        conn.execute("drop table dictionary_entries")
        conn.commit()
    conn.executescript(
        """
        create table if not exists dictionary_entries (
            id integer primary key autoincrement,
            word text not null,
            source text not null,
            syllable_count integer not null,
            terminal_family text not null default '',
            unique(word, source)
        );
        create index if not exists idx_dict_source on dictionary_entries(source);
        create index if not exists idx_dict_family on dictionary_entries(terminal_family);
        """
    )


def _terminal_family_of(word: str) -> str:
    """Endreim-Vokalfamilie eines Wortes (für den Vorfilter)."""
    from app.services.phrase_scorer import PhraseFeatures
    from app.services.user_text_importer import _vowel_family, _last_vowel  # type: ignore

    try:
        anchor = PhraseFeatures.from_phrase(word).anchor
        v = _last_vowel(anchor)
        return _vowel_family(v) if v else ""
    except Exception:
        return ""


def _clean_term(line: str) -> str:
    return unicodedata.normalize("NFKC", line).strip()


# Führende Artikel/Präpositionen, die einen großgeschriebenen Mehrworttitel
# als echten Begriff (statt Eigenname) ausweisen: "Das Absolute", "An sich".
_LEADING_OK = {
    "das", "der", "die", "dem", "den", "des", "ein", "eine", "vom", "zum",
    "zur", "im", "am", "an", "in", "auf", "aus", "und", "ohne", "mit", "für",
}


def _is_proper_name_like(term: str) -> bool:
    """True für vermutliche Eigennamen (Person/Ort): mehrwortig, alle Wörter groß."""
    words = WORD_RE.findall(term)
    if len(words) < 2 or len(words) > 3:
        return False
    if words[0].lower() in _LEADING_OK:
        return False
    return all(w[:1].isupper() for w in words)


def import_dictionaries(
    dictionary_dir: Path = DICTIONARY_DIR,
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    """Liest alle *.txt aus dem Woerterbuch-Ordner in die DB (idempotent)."""
    if not db_path.exists():
        return {"status": "missing_database", "warning": "Erst Personal-Import laufen lassen.", "sources": {}}
    dictionary_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(dictionary_dir.glob("*.txt"))
    conn = sqlite3.connect(db_path)
    try:
        ensure_dictionary_schema(conn)
        per_source: Dict[str, int] = {}
        for path in files:
            source = path.stem.lower()
            seen: set[str] = set()
            rows = []
            for raw in path.read_text("utf-8", errors="ignore").splitlines():
                term = _clean_term(raw)
                if not term or term.startswith("#"):
                    continue
                if not WORD_RE.findall(term):
                    continue
                if _is_proper_name_like(term):
                    continue
                key = term.lower()
                if key in seen:
                    continue
                seen.add(key)
                try:
                    syl = parse_german_word(term.split()[-1]).syllable_count
                except Exception:
                    syl = max(1, len(WORD_RE.findall(term)))
                rows.append((term, source, syl, _terminal_family_of(term)))
            conn.executemany(
                "insert or ignore into dictionary_entries "
                "(word, source, syllable_count, terminal_family) values (?, ?, ?, ?)",
                rows,
            )
            per_source[source] = len(rows)
        conn.commit()
        total = int(conn.execute("select count(*) from dictionary_entries").fetchone()[0])
    finally:
        conn.close()

    return {"status": "ok", "warning": "", "sources": per_source, "total_entries": total,
            "dictionary_dir": str(dictionary_dir)}


def dictionary_summary(db_path: Path = DB_PATH) -> Dict[str, Any]:
    if not db_path.exists():
        return {"total_entries": 0, "sources": {}}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ensure_dictionary_schema(conn)
        rows = conn.execute(
            "select source, count(*) as n from dictionary_entries group by source order by n desc"
        ).fetchall()
    finally:
        conn.close()
    return {"sources": {r["source"]: int(r["n"]) for r in rows},
            "total_entries": sum(int(r["n"]) for r in rows)}


def score_dictionary_rhymes(
    query: str,
    db_path: Path = DB_PATH,
    min_score: float = 0.0,
    sources: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """Scort alle Woerterbuch-Eintraege gegen die Query (gleiche Reim-Logik)."""
    if not db_path.exists():
        return []
    from app.services.user_text_importer import _personal_phrase_score  # lazy, vermeidet Zyklus

    # Vorfilter: nur Einträge mit derselben Endreim-Vokalfamilie scoren
    # (wie die Engine bei der Paarbildung) -> skaliert auf zehntausende Begriffe.
    try:
        q_feat = PhraseFeatures.from_phrase(query)
        q_syll = q_feat.syllable_count
        from app.services.user_text_importer import _vowel_family, _last_vowel  # type: ignore
        v = _last_vowel(q_feat.anchor)
        q_family = _vowel_family(v) if v else ""
    except Exception:
        q_syll = max(1, len(WORD_RE.findall(query)) * 2)
        q_family = ""

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ensure_dictionary_schema(conn)
        clauses, params = [], []
        if q_family:
            clauses.append("terminal_family = ?")
            params.append(q_family)
        if sources:
            clauses.append("source in (%s)" % ",".join("?" * len(sources)))
            params.extend(s.lower() for s in sources)
        where = (" where " + " and ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"select word, source, syllable_count from dictionary_entries{where}",
            tuple(params),
        ).fetchall()
    finally:
        conn.close()

    out: List[Dict[str, Any]] = []
    for row in rows:
        word = row["word"]
        try:
            s = score_rhyme(query, word)
        except Exception:
            continue
        words = len(WORD_RE.findall(word))
        final = _personal_phrase_score(s, q_syll, row["syllable_count"], words)
        if final < min_score:
            continue
        out.append({
            "phrase": word,
            "score": round(final, 4),
            "raw_score": s.total,
            "anchor": s.anchor, "tail": s.tail, "vowel": s.vowel, "cadence": s.cadence,
            "source_title": SOURCE_PREFIX + row["source"],
            "line_no": 0,
            "line_text": word,
            "syllable_count": row["syllable_count"],
            "reason": s.reason,
            "is_dictionary": True,
        })
    return out
