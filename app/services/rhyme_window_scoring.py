"""
Phase-3 scoring harness for the Phrase-Layer.

Pure functions over RhymeWindow → no I/O, no engine coupling, no API calls.
Compares two windows (query vs candidate) and returns sub-scores plus a
weighted total.

Weighting (klangbasiert, nicht orthografisch):
    anchor      0.40   ← Vokalführung an betonten Positionen
    vowel_run   0.25   ← Gesamt-Vokalpalette der Phrase
    rhythm      0.20   ← Stress-Slot-Muster + Längenabgleich
    grip        0.15   ← Konsonanten als Gerüst, nicht als Hauptsignal
    ─────────────────
    total       1.00

Self-match invariant: total_score(w, w) == 1.0 für jedes w mit Inhalt.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable, List

from app.schemas.rhyme_window import RhymeWindow


# ── Constants ────────────────────────────────────────────────────────────────

REDUCED_VOWELS: frozenset[str] = frozenset({"ə", "ɐ"})

# Sub-score weights — sum to 1.0
W_ANCHOR    = 0.40
W_VOWEL_RUN = 0.25
W_RHYTHM    = 0.20
W_GRIP      = 0.15


# ── Generic similarity primitives ────────────────────────────────────────────

def _multiset_jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """
    Jaccard similarity on multisets. Order-insensitive, frequency-sensitive.

    Both empty → 1.0 (vacuous match, trivially identical).
    One empty  → 0.0 (no overlap possible).
    """
    ca, cb = Counter(a), Counter(b)
    if not ca and not cb:
        return 1.0
    inter = sum((ca & cb).values())
    union = sum((ca | cb).values())
    return inter / union if union else 1.0


def _positional_match(a: List[int], b: List[int]) -> float:
    """Position-aligned 0/1 match ratio, normalised by max length."""
    if not a and not b:
        return 1.0
    n = max(len(a), len(b))
    common = min(len(a), len(b))
    matches = sum(1 for i in range(common) if a[i] == b[i])
    return matches / n


def _length_ratio(a: List, b: List) -> float:
    la, lb = len(a), len(b)
    if la == 0 and lb == 0:
        return 1.0
    if la == 0 or lb == 0:
        return 0.0
    return min(la, lb) / max(la, lb)


# ── Sub-scores ───────────────────────────────────────────────────────────────

def anchor_score(qw: RhymeWindow, cw: RhymeWindow) -> float:
    """
    Stressed-vowel agreement.  This is the dominant rap-rhyme signal:
    two phrases that share the same anchor nuclei (e.g. /aɪ … aɪ/)
    will be perceived as rhyming even when their suffixes differ.

    Empty-vs-empty: 1.0.  Empty-vs-non-empty: 0.0.
    """
    return _multiset_jaccard(qw.anchor_nuclei, cw.anchor_nuclei)


def vowel_run_score(qw: RhymeWindow, cw: RhymeWindow) -> float:
    """
    Full-phrase vowel palette overlap.  Reduced vowels (schwa, ɐ) are
    excluded — they carry no perceptual colour.
    """
    qa = [v for v in qw.vowel_run if v not in REDUCED_VOWELS]
    ca = [v for v in cw.vowel_run if v not in REDUCED_VOWELS]
    return _multiset_jaccard(qa, ca)


def rhythm_score(qw: RhymeWindow, cw: RhymeWindow) -> float:
    """
    Half positional stress-slot match, half length similarity.
    Captures both *where* the beats fall and *how long* the phrase is.
    """
    pos = _positional_match(qw.stress_slots, cw.stress_slots)
    lr  = _length_ratio(qw.stress_slots, cw.stress_slots)
    return 0.5 * pos + 0.5 * lr


def grip_score(qw: RhymeWindow, cw: RhymeWindow) -> float:
    """
    Consonant scaffolding.  Lowest weight by design: rap rhymes lean on
    vowels first, consonants only fine-tune.
    """
    return _multiset_jaccard(qw.consonant_grip, cw.consonant_grip)


# ── Weighted total ───────────────────────────────────────────────────────────

def total_score(qw: RhymeWindow, cw: RhymeWindow) -> float:
    """Weighted sum of the four sub-scores; range [0.0, 1.0]."""
    return (
        W_ANCHOR    * anchor_score(qw, cw)    +
        W_VOWEL_RUN * vowel_run_score(qw, cw) +
        W_RHYTHM    * rhythm_score(qw, cw)    +
        W_GRIP      * grip_score(qw, cw)
    )


def score_breakdown(qw: RhymeWindow, cw: RhymeWindow) -> dict:
    """Diagnostic dict — useful for tests and debug output."""
    a = anchor_score(qw, cw)
    v = vowel_run_score(qw, cw)
    r = rhythm_score(qw, cw)
    g = grip_score(qw, cw)
    return {
        "anchor":    a,
        "vowel_run": v,
        "rhythm":    r,
        "grip":      g,
        "total":     W_ANCHOR*a + W_VOWEL_RUN*v + W_RHYTHM*r + W_GRIP*g,
    }
