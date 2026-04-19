"""
Phrase-Layer extractor: text → LineParse → List[RhymeWindow].

Public API
----------
build_line_parse(text)               -> LineParse
extract_default_windows(line, idx)   -> List[RhymeWindow]
"""
from __future__ import annotations

import re
from collections import Counter
from typing import List

from app.schemas.rhyme import ParsedWord
from app.schemas.rhyme_window import LineParse, RhymeWindow, WordInLine
from app.services.parser import (
    detect_stress,
    is_vowel,
    parse_german_word,
    syllabify,
)

# ── Phoneme sets ──────────────────────────────────────────────────────────────

DIPHTHONG_SET: frozenset[str] = frozenset({"aɪ", "aʊ", "ɔʏ"})
LONG_VOWELS:   frozenset[str] = frozenset({"aː", "eː", "iː", "oː", "uː", "øː", "yː"})
FRONT_VOWELS:  frozenset[str] = frozenset({"ɛ", "eː", "ɪ", "iː", "œ", "øː", "ʏ", "yː"})
BACK_VOWELS:   frozenset[str] = frozenset({"a", "aː", "ɔ", "oː", "ʊ", "uː", "aʊ"})

# Consonants that create a "grip" — distinctive, perceptually salient
GRIP_CONSONANTS: frozenset[str] = frozenset({
    "t͡s", "t͡ʃ", "d͡ʒ", "pf",   # affricates
    "ç", "ʃ", "ʒ", "x",          # fricatives
    "s", "z", "f", "v",
    "k", "p", "t",
})

# German function words that don't carry rhyme stress
FUNCTION_WORDS: frozenset[str] = frozenset({
    "der", "die", "das", "ein", "eine", "einen", "einem", "einer", "eines",
    "und", "oder", "aber", "doch", "wenn", "als", "wie", "dass", "weil",
    "in", "auf", "an", "bei", "mit", "von", "zu", "aus", "nach", "vor",
    "über", "unter", "durch", "für", "gegen", "ohne", "um", "bis",
    "ist", "sind", "war", "waren", "hat", "haben", "wird", "werden",
    "ich", "du", "er", "sie", "es", "wir", "ihr",
    "nicht", "kein", "keine", "keinen",
    "auch", "noch", "schon", "ja", "nein",
    "sich", "mir", "dir", "ihm",
    "wo", "was", "wer", "wann", "warum", "wohin", "woher", "wieso",
})

QUESTION_WORDS: frozenset[str] = frozenset({
    "wer", "was", "wo", "wann", "warum", "wie", "welche", "welcher",
    "welches", "wohin", "woher", "wieso", "weshalb", "wozu",
})


# ── Tokenisation ──────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """
    Split text into word tokens using only alphabetic characters.
    Hyphens inside compounds (e.g. "Leib-Seele-Probleme") are treated as
    word boundaries, so each component is parsed independently.
    """
    return re.findall(r"[A-Za-zÄÖÜäöüß]+", text)


# ── LineParse ─────────────────────────────────────────────────────────────────

def build_line_parse(text: str) -> LineParse:
    """
    Tokenise *text*, G2P-parse each token, and build the flat syllable / stress
    arrays needed for window extraction.
    """
    tokens = _tokenize(text)
    words: List[WordInLine] = []
    flat_syllables: List[List[str]] = []
    flat_stress: List[int] = []

    for wi, token in enumerate(tokens):
        parsed: ParsedWord = parse_german_word(token)
        syls: List[List[str]] = syllabify(parsed.phonetic)

        # Guard: stress list must match syllable count
        stress: List[int] = list(parsed.stress_pattern)
        while len(stress) < len(syls):
            stress.append(0)
        stress = stress[: len(syls)]

        start_syl = len(flat_syllables)
        for syl, s in zip(syls, stress):
            flat_syllables.append(list(syl))
            flat_stress.append(s)
        end_syl = len(flat_syllables)

        words.append(
            WordInLine(
                text=token,
                parsed=parsed,
                word_index=wi,
                start_syllable=start_syl,
                end_syllable=end_syl,
            )
        )

    return LineParse(
        raw_text=text,
        words=words,
        flat_syllables=flat_syllables,
        flat_stress_slots=flat_stress,
        sentence_shape=flat_stress[:],
    )


# ── Feature helpers ───────────────────────────────────────────────────────────

def _vowels_in(syl: List[str]) -> List[str]:
    return [p for p in syl if is_vowel(p)]


def _consonants_in(syl: List[str]) -> List[str]:
    return [p for p in syl if not is_vowel(p)]


def _anchor_nuclei(syllable_span: List[List[str]], stress_slots: List[int]) -> List[str]:
    out: List[str] = []
    for syl, s in zip(syllable_span, stress_slots):
        if s == 1:
            out.extend(_vowels_in(syl))
    return out


def _support_vowels(syllable_span: List[List[str]], stress_slots: List[int]) -> List[str]:
    out: List[str] = []
    for syl, s in zip(syllable_span, stress_slots):
        if s == 0:
            out.extend(_vowels_in(syl))
    return out


def _vowel_run(syllable_span: List[List[str]]) -> List[str]:
    return [p for syl in syllable_span for p in syl if is_vowel(p)]


def _consonant_grip(syllable_span: List[List[str]], stress_slots: List[int]) -> List[str]:
    """
    Collect distinctive consonants from the window.

    Stressed-syllable consonants are listed first (they set the primary colour);
    unstressed-syllable consonants follow.  The full set matters for pattern
    fingerprinting (e.g. t͡s and ç appear in unstressed codas of German words
    like "setzen" and "sprechen" but are perceptually essential to the grip).

    Result is deduplicated while preserving order of first occurrence.
    """
    primary: List[str] = []
    for syl, s in zip(syllable_span, stress_slots):
        if s == 1:
            for c in _consonants_in(syl):
                if c in GRIP_CONSONANTS:
                    primary.append(c)

    secondary: List[str] = []
    for syl, s in zip(syllable_span, stress_slots):
        if s == 0:
            for c in _consonants_in(syl):
                if c in GRIP_CONSONANTS:
                    secondary.append(c)

    combined = primary + secondary
    seen: set[str] = set()
    result: List[str] = []
    for c in combined:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


def _flow_shape(vowel_run: List[str], stress_slots: List[int]) -> str:
    """
    Classify the rhythmic / vocalic character of the window.

    stretched : ≥50 % of vowels are long or diphthongs
    banded    : one vowel type accounts for ≥50 %, OR front vowels ≥55 %
    rolling   : none of the above, but ≥3 vowels → varied, moving pattern
    clipped   : very few vowels (< 3)
    flat      : empty
    """
    if not vowel_run:
        return "flat"

    n = len(vowel_run)
    long_n = sum(1 for v in vowel_run if v in LONG_VOWELS or v in DIPHTHONG_SET)

    if long_n / n >= 0.50:
        return "stretched"

    counts = Counter(vowel_run)
    _, top_n = counts.most_common(1)[0]
    if top_n / n >= 0.50:
        return "banded"

    front_n = sum(1 for v in vowel_run if v in FRONT_VOWELS)
    if front_n / n >= 0.55:
        return "banded"

    if n >= 3:
        return "rolling"

    return "clipped"


def _parallel_shape(line_raw: str, window_words: List[WordInLine]) -> str:
    """Detect structural parallel patterns in the line."""
    word_lower = {w.text.lower() for w in window_words}
    q_count = sum(1 for wl in word_lower if wl in QUESTION_WORDS)
    if q_count >= 1 and "?" in line_raw:
        return "question_parallel"
    return "none"


def _technique_tags(
    anchor_nuclei: List[str],
    vowel_run: List[str],
    consonant_grip: List[str],
    flow_shape: str,
    parallel_shape: str,
) -> List[str]:
    tags: List[str] = []

    # ── diphthong_anchor_chain: same diphthong appears ≥2× in stressed positions
    dph_counts = Counter(a for a in anchor_nuclei if a in DIPHTHONG_SET)
    if any(cnt >= 2 for cnt in dph_counts.values()):
        tags.append("diphthong_anchor_chain")

    if vowel_run:
        # Reduced vowels (schwa, ɐ) are vocalic but carry no colour —
        # exclude them when measuring front/back character.
        REDUCED = frozenset({"ə", "ɐ"})
        coloured = [v for v in vowel_run if v not in REDUCED]

        if coloured:
            nc = len(coloured)
            # front_vowel_band: ≥55 % of coloured vowels are front
            front_n = sum(1 for v in coloured if v in FRONT_VOWELS)
            if front_n / nc >= 0.55:
                tags.append("front_vowel_band")

            # back_vowel_band: ≥55 % back
            back_n = sum(1 for v in coloured if v in BACK_VOWELS)
            if back_n / nc >= 0.55:
                tags.append("back_vowel_band")

    if parallel_shape == "question_parallel":
        tags.append("question_parallel")

    if len(consonant_grip) >= 3:
        tags.append("tight_consonant_grip")

    return tags


# ── Window builder ────────────────────────────────────────────────────────────

def _build_window(
    line: LineParse,
    start: int,
    end: int,
    line_index: int,
) -> RhymeWindow:
    syllable_span = line.flat_syllables[start:end]
    stress_slots = line.flat_stress_slots[start:end]

    # Words that overlap with [start, end)
    window_words = [
        w for w in line.words
        if w.start_syllable < end and w.end_syllable > start
    ]
    raw_text = " ".join(w.text for w in window_words)

    anchors  = _anchor_nuclei(syllable_span, stress_slots)
    support  = _support_vowels(syllable_span, stress_slots)
    vrun     = _vowel_run(syllable_span)
    grip     = _consonant_grip(syllable_span, stress_slots)
    fshape   = _flow_shape(vrun, stress_slots)
    pshape   = _parallel_shape(line.raw_text, window_words)
    tags     = _technique_tags(anchors, vrun, grip, fshape, pshape)

    return RhymeWindow(
        raw_text=raw_text,
        line_index=line_index,
        start_syllable=start,
        end_syllable=end,
        syllable_span=syllable_span,
        stress_slots=stress_slots,
        anchor_nuclei=anchors,
        support_vowels=support,
        vowel_run=vrun,
        consonant_grip=grip,
        flow_shape=fshape,
        parallel_shape=pshape,
        technique_tags=tags,
    )


# ── extract_default_windows ───────────────────────────────────────────────────

def extract_default_windows(line: LineParse, line_index: int = 0) -> List[RhymeWindow]:
    """
    Derive rhyme windows from a parsed line.

    Window strategy:
    1. **Full-line window** – covers the whole line; good for detecting
       distributed vowel patterns (diphthong chains, vowel bands).
    2. **Tail window** – from one syllable before the last main-stress (in a
       non-function word) to end of line; captures the classic "rhyme tail"
       for multi-syllabic matching.  Only emitted when the line has ≥ 4
       syllables and the tail window starts at a different position from 0.
    """
    n_syls = len(line.flat_syllables)
    if n_syls == 0:
        return []

    windows: List[RhymeWindow] = []

    # ── Window 1: full line ───────────────────────────────────────────────────
    windows.append(_build_window(line, 0, n_syls, line_index))

    # ── Window 2: tail window ─────────────────────────────────────────────────
    if n_syls >= 4:
        last_main_stress: int | None = None
        for w in reversed(line.words):
            if w.text.lower() in FUNCTION_WORDS:
                continue
            for si in range(w.start_syllable, w.end_syllable):
                if line.flat_stress_slots[si] == 1:
                    last_main_stress = si
                    break
            if last_main_stress is not None:
                break

        if last_main_stress is not None and last_main_stress > 0:
            tail_start = max(0, last_main_stress - 1)
            if tail_start < n_syls:
                windows.append(_build_window(line, tail_start, n_syls, line_index))

    return windows
