"""
phrase_scorer.py — Phrase-level German rhyme scorer

Kernprinzip:
    Reim wird durch audible Ähnlichkeit am ENDE der Phrase bestimmt,
    nicht durch globale Vokal/Stress-Ähnlichkeit.

Scoring-Architektur:
    1. anchor_score   (0-1) — Ähnlichkeit des End-Ankers (terminal_span)
    2. tail_score     (0-1) — Ähnlichkeit der letzten 2-3 Silben
    3. vowel_score    (0-1) — Vokalfolge des Anker-Fensters (NICHT global)
    4. cadence_score  (0-1) — Silbenzahl + Rhythmus der Phrase
    5. global_vowel   (0-1) — globale Vokalstruktur (NUR als Tiebreaker, schwach)

    final_score = anchor_gate * weighted_sum

    anchor_gate:
        if anchor_score < ANCHOR_MIN → score wird hart gedeckelt auf MAX_WITHOUT_ANCHOR
        Das verhindert, dass globale Ähnlichkeit Reim simuliert.

Gewichte:
    anchor   0.40
    tail     0.30
    vowel    0.15  (lokales Fenster)
    cadence  0.10
    global   0.05  (fast irrelevant)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from app.services.parser import parse_german_word
from app.services.phonological_distance import FEATURES, tail_similarity, phoneme_similarity
from app.schemas.rhyme import ParsedWord

# ── Schwellenwerte ────────────────────────────────────────────────────────────

ANCHOR_MIN           = 0.55   # Unter diesem Wert → harte Deckelung
MAX_WITHOUT_ANCHOR   = 0.35   # Max-Score wenn Anker schwach
SUFFIX_TRAP_PENALTY  = 0.35   # Abzug für Suffix-Traps (-schaft, -heit, etc.)
RAP_SLANT_ANCHOR_MIN = 0.62   # gleicher Endvokal + harte Slant-Coda
VOWEL_GATE_MAX       = 0.45   # anderer Endvokal darf keinen Anker simulieren

SUFFIX_TRAPS = {
    "schaft", "heit", "keit", "ung", "isch", "lich",
    "tion", "sion", "ismus", "ist", "in",
}

WEIGHTS = {
    "anchor":  0.40,
    "tail":    0.30,
    "vowel":   0.15,   # lokales Fenster
    "cadence": 0.10,
    "global":  0.05,
}


# ── Datenstrukturen ───────────────────────────────────────────────────────────

_WORD_EDGE_CHARS = ".,!?;:()[]{}\"'„“”‚‘`"
MAX_PHRASE_WINDOW_SYLLABLES = 8


def _phrase_words(phrase: str) -> List[str]:
    return [w.strip(_WORD_EDGE_CHARS) for w in phrase.strip().split() if w.strip(_WORD_EDGE_CHARS)]


def _parse_context_words(words: List[str]) -> List[tuple[str, ParsedWord]]:
    parsed: List[tuple[str, ParsedWord]] = []
    for word in words:
        try:
            parsed.append((word, parse_german_word(word)))
        except Exception:
            continue
    return parsed


def _tail_phrase_window(parsed_words: List[tuple[str, ParsedWord]]) -> List[tuple[str, ParsedWord]]:
    """Trailing phrase window for 3-8-syllable rap chains across word boundaries."""
    if not parsed_words:
        return []
    total_syllables = sum(parsed.syllable_count for _, parsed in parsed_words)
    if total_syllables <= MAX_PHRASE_WINDOW_SYLLABLES:
        return parsed_words

    window: List[tuple[str, ParsedWord]] = []
    running = 0
    for word, parsed in reversed(parsed_words):
        next_count = running + parsed.syllable_count
        if window and next_count > MAX_PHRASE_WINDOW_SYLLABLES:
            break
        window.append((word, parsed))
        running = next_count
        if running >= MAX_PHRASE_WINDOW_SYLLABLES:
            break
    return list(reversed(window))


@dataclass
class PhraseFeatures:
    """Features einer Phrase für den Reim-Scorer."""
    raw: str
    words: List[str]
    last_word: str
    parsed_last: ParsedWord

    # End-Anker: terminal_span des letzten Wortes
    anchor: List[str] = field(default_factory=list)
    # Tail: alles nach dem letzten Vokal im letzten Wort
    end_tail: List[str] = field(default_factory=list)
    # Lokale Vokalfolge: nur die Vokale des Anker-Fensters
    anchor_vowels: List[str] = field(default_factory=list)
    # Globale Vokalfolge der letzten 2-3 Wörter
    phrase_vowels: List[str] = field(default_factory=list)
    # Silbenzahl der Phrase
    syllable_count: int = 0
    # Letztes Wort für Suffix-Trap-Prüfung
    last_word_lower: str = ""

    @classmethod
    def from_phrase(cls, phrase: str) -> "PhraseFeatures":
        words = _phrase_words(phrase)
        last_word = words[-1] if words else phrase
        parsed = parse_german_word(last_word)

        # Anker = terminal_span (letzter Vokal + Ausklang)
        anchor = parsed.terminal_span

        # Lokale Vokalfolge = nur Vokale im Anker
        from app.services.phonological_distance import FEATURES as PH_FEAT
        VOWELS = {k for k, v in PH_FEAT.items() if v.typ in {"vowel","diphthong"}}
        anchor_vowels = [p for p in anchor if p in VOWELS]

        # Phrase-Vokalfolge: trailing 3-8-syllable rap window, not just last word.
        phrase_vowels = []
        parsed_context = _tail_phrase_window(_parse_context_words(words))
        for _word, p in parsed_context:
            phrase_vowels.extend(p.vowel_spine)

        # Silbenzahl: Summe des trailing phrase windows.
        syllable_count = 0
        for _word, p in parsed_context:
            syllable_count += p.syllable_count

        return cls(
            raw=phrase,
            words=words,
            last_word=last_word,
            parsed_last=parsed,
            anchor=anchor,
            end_tail=parsed.terminal_tail,
            anchor_vowels=anchor_vowels,
            phrase_vowels=phrase_vowels,
            syllable_count=syllable_count,
            last_word_lower=last_word.lower(),
        )


# ── Scoring ───────────────────────────────────────────────────────────────────

def _is_suffix_trap(word: str, query_word: str) -> bool:
    """Prüft ob ein Wort nur durch morphologisches Suffix mit dem Query übereinstimmt."""
    w = word.lower()
    q = query_word.lower()
    for suffix in SUFFIX_TRAPS:
        if w.endswith(suffix) and q.endswith(suffix) and w != q:
            return True
    return False


def _is_vowel(phoneme: str) -> bool:
    feature = FEATURES.get(phoneme)
    return bool(feature and feature.typ in {"vowel", "diphthong"})


def _last_anchor_vowel(features: PhraseFeatures) -> str | None:
    for phoneme in reversed(features.anchor):
        if _is_vowel(phoneme):
            return phoneme
    return None


def _anchor_coda(features: PhraseFeatures) -> List[str]:
    for idx in range(len(features.anchor) - 1, -1, -1):
        if _is_vowel(features.anchor[idx]):
            return features.anchor[idx + 1:]
    return features.anchor


def _is_voiceless_obstruent(phoneme: str) -> bool:
    feature = FEATURES.get(phoneme)
    return bool(feature and feature.typ in {"plosive", "fricative", "affricate"} and not feature.voiced)


def _rap_slant_coda_match(left: List[str], right: List[str]) -> bool:
    """Deutschrap-Slant-Familie nach gleichem Endvokal: -tt/-ss/-ck/-tz/-chs."""
    if not left or not right:
        return False
    if not all(_is_voiceless_obstruent(p) for p in left + right):
        return False
    return True


def _anchor_score(q: PhraseFeatures, c: PhraseFeatures) -> float:
    """Ähnlichkeit des End-Ankers (terminal_span beider Phrasen)."""
    if not q.anchor or not c.anchor:
        return 0.0
    base = tail_similarity(q.anchor, c.anchor)
    q_vowel = _last_anchor_vowel(q)
    c_vowel = _last_anchor_vowel(c)

    # Im Rap darf Konsonantenhärte keinen anderen Endvokal verdecken:
    # "patientenkontakt" endet hart, aber nicht auf den -ett-Vokal.
    if q_vowel and c_vowel and phoneme_similarity(q_vowel, c_vowel) < 0.82:
        return min(base, VOWEL_GATE_MAX)

    q_coda = _anchor_coda(q)
    c_coda = _anchor_coda(c)
    if q_vowel and c_vowel and _rap_slant_coda_match(q_coda, c_coda):
        return max(base, RAP_SLANT_ANCHOR_MIN)

    return base


def _anchor_gated(anchor: float) -> bool:
    return anchor < ANCHOR_MIN


def _tail_score(q: PhraseFeatures, c: PhraseFeatures) -> float:
    """Ähnlichkeit des End-Tails (nach letztem Vokal)."""
    if not q.end_tail and not c.end_tail:
        return 1.0  # beide haben keinen Tail (Vokal am Ende) → OK
    if not q.end_tail or not c.end_tail:
        return 0.3  # einer hat Tail, der andere nicht → schwach
    return tail_similarity(q.end_tail, c.end_tail)


def _vowel_score(q: PhraseFeatures, c: PhraseFeatures) -> float:
    """Lokale Vokalähnlichkeit im Anker-Fenster (NICHT global)."""
    qv, cv = q.anchor_vowels, c.anchor_vowels
    if not qv or not cv:
        return 0.0
    # Positionsgewichtet, nur letzten 3 Vokale
    qv, cv = qv[-3:], cv[-3:]
    n = max(len(qv), len(cv))
    if n == 0:
        return 1.0
    score = 0.0
    total_w = 0.0
    for i in range(n):
        av = qv[i] if i < len(qv) else None
        bv = cv[i] if i < len(cv) else None
        w = n - i  # frühe Vokale im Fenster weniger gewichtet
        total_w += w
        if av is None or bv is None:
            score += 0.0
        elif av == bv:
            score += w
        else:
            score += w * phoneme_similarity(av, bv)
    return score / total_w if total_w else 0.0


def _cadence_score(q: PhraseFeatures, c: PhraseFeatures) -> float:
    """Rhythmus-Ähnlichkeit: Silbenzahl der Phrase."""
    delta = abs(q.syllable_count - c.syllable_count)
    if delta == 0: return 1.0
    if delta == 1: return 0.7
    if delta == 2: return 0.4
    return 0.1


def _global_vowel_score(q: PhraseFeatures, c: PhraseFeatures) -> float:
    """Globale Vokalähnlichkeit (Tiebreaker, sehr schwach gewichtet)."""
    return tail_similarity(q.phrase_vowels[-4:], c.phrase_vowels[-4:])


@dataclass
class RhymeScore:
    phrase: str
    total: float
    anchor: float
    tail: float
    vowel: float
    cadence: float
    global_v: float
    anchor_gated: bool
    suffix_penalized: bool
    reason: str

    def explain(self) -> str:
        gate_flag = " [ANKER-GATE]" if self.anchor_gated else ""
        suffix_flag = " [SUFFIX-TRAP]" if self.suffix_penalized else ""
        return (
            f"{self.phrase!r:35s} → {self.total:.3f}"
            f"  anker={self.anchor:.2f} tail={self.tail:.2f}"
            f"  vowel={self.vowel:.2f} cadence={self.cadence:.2f}"
            f"  global={self.global_v:.2f}"
            f"{gate_flag}{suffix_flag}"
        )


def score_rhyme(query: str, candidate: str) -> RhymeScore:
    """Berechnet den Reim-Score zwischen zwei Phrasen."""
    q = PhraseFeatures.from_phrase(query)
    c = PhraseFeatures.from_phrase(candidate)

    anchor   = _anchor_score(q, c)
    tail     = _tail_score(q, c)
    vowel    = _vowel_score(q, c)
    cadence  = _cadence_score(q, c)
    global_v = _global_vowel_score(q, c)

    # Gewichtete Summe
    raw_score = (
        anchor   * WEIGHTS["anchor"]  +
        tail     * WEIGHTS["tail"]    +
        vowel    * WEIGHTS["vowel"]   +
        cadence  * WEIGHTS["cadence"] +
        global_v * WEIGHTS["global"]
    )

    # ── Hard Gates ────────────────────────────────────────────────────────────
    anchor_gated = False
    suffix_penalized = False

    # Gate 1: Schwacher Anker → Score gedeckelt
    if _anchor_gated(anchor):
        raw_score = min(raw_score, MAX_WITHOUT_ANCHOR)
        anchor_gated = True

    # Gate 2: Suffix-Trap → Penalty
    if _is_suffix_trap(c.last_word_lower, q.last_word_lower):
        raw_score = max(0.0, raw_score - SUFFIX_TRAP_PENALTY)
        suffix_penalized = True

    # Erklärung
    if anchor_gated:
        reason = f"Anker schwach ({anchor:.2f}) → gedeckelt auf {MAX_WITHOUT_ANCHOR}"
    elif anchor >= 0.90:
        reason = "Starker Anker-Match"
    elif anchor >= 0.70:
        reason = "Guter Anker-Match"
    else:
        reason = "Schwacher Anker"

    if suffix_penalized:
        reason += " + Suffix-Trap"

    return RhymeScore(
        phrase=candidate,
        total=round(raw_score, 4),
        anchor=round(anchor, 4),
        tail=round(tail, 4),
        vowel=round(vowel, 4),
        cadence=round(cadence, 4),
        global_v=round(global_v, 4),
        anchor_gated=anchor_gated,
        suffix_penalized=suffix_penalized,
        reason=reason,
    )


def rank_rhymes(query: str, candidates: List[str]) -> List[RhymeScore]:
    """Rankt Kandidaten nach Reim-Score."""
    scores = [score_rhyme(query, c) for c in candidates]
    return sorted(scores, key=lambda s: s.total, reverse=True)
