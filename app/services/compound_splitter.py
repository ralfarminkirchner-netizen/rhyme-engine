"""
compound_splitter.py — Deutsche Komposita-Zerlegung (Dekompensation).

Duenner Adapter um `split-words` (CharSplit, n-gram-Modell, ~95% Wortkopf-Treffer).
Zweck: lange Determinativkomposita ("Schattenkabinett") in Glieder zerlegen,
damit der Hauptakzent korrekt aufs LETZTE Glied wandern kann (-> Stress-Anchor)
und interne Morphemgrenzen fuer Mosaikreime (Typ C) sichtbar werden.

Designprinzipien:
- HARTER FALLBACK: fehlt das Paket oder ist das Modell unsicher, wird das Wort
  UNGETEILT zurueckgegeben. Die Engine darf daran nie zerbrechen.
- KONFIDENZ-GATE: nur splitten, wenn der CharSplit-Score >= MIN_SCORE. Echte
  Komposita sind deutlich positiv, Nicht-Komposita (Beziehung) negativ.
- ORIGINALSCHREIBUNG: Glieder werden aus dem Originalwort geschnitten (Laengen
  des Modells), nicht aus dessen rekapitalisierter Ausgabe.
- REKURSIV: mehrgliedrige Komposita werden tiefer zerlegt (Nacht+Schatten+...).
- Keine Semantik. Rein strukturell.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

# Nur splitten, wenn das Modell mindestens so sicher ist. Echte Komposita scoren
# in der Praxis >=0.7 (schattenkabinett 0.99, autobahn 0.73), Fehlsplits einfacher
# Woerter <0.5 (machen 0.21, denken 0.40). 0.5 = hohe Praezision (lieber NICHT
# splitten als falsch — ein Fehlsplit verschoebe den Reim-Anker).
MIN_SCORE = 0.5
MIN_PART_LEN = 3      # jedes Glied mindestens so lang
MAX_DEPTH = 4         # Schutz gegen Endlos-/Ueberzerlegung

_splitter = None
_available: Optional[bool] = None


def _get_splitter():
    global _splitter, _available
    if _available is None:
        try:
            from split_words import Splitter  # type: ignore

            _splitter = Splitter()
            _available = True
        except Exception:
            _splitter = None
            _available = False
    return _splitter


def is_available() -> bool:
    """True, wenn das CharSplit-Modell geladen werden konnte."""
    _get_splitter()
    return bool(_available)


def _binary_split(word: str, min_score: float) -> Optional[tuple[str, str]]:
    splitter = _get_splitter()
    if splitter is None:
        return None
    try:
        results = splitter.split_compound(word)
    except Exception:
        return None
    if not results:
        return None
    score, head, tail = results[0]
    if score < min_score:
        return None
    # Glieder aus dem ORIGINALWORT schneiden (Schreibung/Case erhalten).
    if len(head) + len(tail) == len(word):
        head, tail = word[: len(head)], word[len(head):]
    else:
        head, tail = head.lower(), tail.lower()
    if len(head) < MIN_PART_LEN or len(tail) < MIN_PART_LEN:
        return None
    return head, tail


def _split_rec(word: str, min_score: float, depth: int) -> List[str]:
    if depth <= 0 or len(word) < 2 * MIN_PART_LEN:
        return [word]
    pair = _binary_split(word, min_score)
    if pair is None:
        return [word]
    head, tail = pair
    return _split_rec(head, min_score, depth - 1) + _split_rec(tail, min_score, depth - 1)


@lru_cache(maxsize=8192)
def split_compound(word: str, min_score: float = MIN_SCORE) -> List[str]:
    """
    Zerlegt ein deutsches Kompositum in seine Glieder.

    Beispiele:
        "schattenkabinett"  -> ["schatten", "kabinett"]
        "beziehung"         -> ["beziehung"]        (kein Kompositum)
        (ohne split-words)  -> [word]               (harter Fallback)

    Reihenfolge der Glieder = Originalreihenfolge. Das letzte Glied traegt im
    Deutschen fast immer den Hauptakzent (Determinativkompositum).
    """
    if not word or not word.strip():
        return [word]
    return _split_rec(word, min_score, MAX_DEPTH)


def head_components(word: str, min_score: float = MIN_SCORE) -> List[str]:
    """Alle Glieder ausser dem letzten (= die Bestimmungsglieder)."""
    parts = split_compound(word, min_score)
    return parts[:-1] if len(parts) > 1 else []


def last_component(word: str, min_score: float = MIN_SCORE) -> str:
    """Das Grundwort (letztes Glied) — Traeger des Hauptakzents."""
    return split_compound(word, min_score)[-1]
