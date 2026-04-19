"""Phrase-Layer data structures for line-level rap rhyme analysis."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

from app.schemas.rhyme import ParsedWord


@dataclass
class WordInLine:
    """A parsed word placed at a specific syllable position within a line."""
    text: str
    parsed: ParsedWord
    word_index: int       # 0-based position in the line
    start_syllable: int   # first syllable index in flat line array (inclusive)
    end_syllable: int     # last syllable index in flat line array (exclusive)


@dataclass
class LineParse:
    """A full line tokenised and phonetically parsed, with a flat syllable array."""
    raw_text: str
    words: List[WordInLine]
    flat_syllables: List[List[str]]   # every syllable's phoneme list, concatenated
    flat_stress_slots: List[int]      # 0/1 per flat syllable (mirrors stress_pattern)
    sentence_shape: List[int]         # alias of flat_stress_slots; reserved for future weighting


@dataclass
class RhymeWindow:
    """
    A contiguous slice of a line's syllables that forms a rhyme-relevant span.

    Features are computed from phoneme data, not orthography:

    - anchor_nuclei   : vowels / diphthongs at stressed syllable positions
    - support_vowels  : vowels at unstressed positions
    - vowel_run       : all vowels in order (= anchors + support, positionally ordered)
    - consonant_grip  : distinctive consonants (t͡s, ç, ʃ, …) around stressed positions
    - flow_shape      : "rolling" | "stretched" | "banded" | "clipped" | "flat"
    - parallel_shape  : "question_parallel" | "list_parallel" | "none"
    - technique_tags  : e.g. ["diphthong_anchor_chain", "front_vowel_band"]
    """
    raw_text: str                  # reconstructed word-text of the window
    line_index: int                # which line this window came from
    start_syllable: int            # start in flat line array (inclusive)
    end_syllable: int              # end in flat line array (exclusive)
    syllable_span: List[List[str]] # phoneme lists for each syllable in the window
    stress_slots: List[int]        # 0/1 per syllable in the window
    anchor_nuclei: List[str]       # vowels at stressed positions
    support_vowels: List[str]      # vowels at unstressed positions
    vowel_run: List[str]           # all vowels in window order
    consonant_grip: List[str]      # distinctive consonants (deduplicated, order-preserving)
    flow_shape: str
    parallel_shape: str
    technique_tags: List[str] = field(default_factory=list)
