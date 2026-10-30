"""Explicit, bounded graph DTOs; no graph relation implies user acceptance."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import Field, model_validator

from app.schemas.rhyme import ApiModel
from app.services.parser import is_vowel
from app.services.phonological_distance import FEATURES


SYLLABIC_CONSONANTS = frozenset({"n̩", "m̩", "l̩"})
MANUAL_PHONES = frozenset(FEATURES) | SYLLABIC_CONSONANTS


class PronunciationOverride(ApiModel):
    line_index: int = Field(ge=0)
    word_index: int = Field(ge=0)
    word_text: Optional[str] = Field(default=None, max_length=500)
    syllables: list[list[str]] = Field(min_length=1, max_length=64)
    stress: list[Literal[0, 1]] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_pronunciation(self) -> "PronunciationOverride":
        if len(self.syllables) != len(self.stress):
            raise ValueError("Pro Silbe ist genau ein Betonungswert (0 oder 1) erforderlich.")
        for syllable in self.syllables:
            if not 1 <= len(syllable) <= 24:
                raise ValueError("Eine Silbe muss 1 bis 24 einzelne Lautsymbole enthalten.")
            if any(phone not in MANUAL_PHONES for phone in syllable):
                raise ValueError("Unbekanntes Lautsymbol: einzelne IPA-Symbole des Parserinventars verwenden.")
            # A vowel followed immediately by vocalised r may be a single
            # nucleus plus offglide. A separately supplied [ɐ] remains a nucleus.
            nuclei = sum(
                (is_vowel(phone) or phone in SYLLABIC_CONSONANTS)
                and not (phone == "ɐ" and index > 0 and is_vowel(syllable[index - 1]) and syllable[index - 1] != "ɐ")
                for index, phone in enumerate(syllable)
            )
            if nuclei != 1:
                raise ValueError("Jede Silbe braucht genau einen Kern; Diphthonge z.B. als 'aɪ' eingeben.")
        return self


class GraphBuildRequest(ApiModel):
    text: str = Field(min_length=1, max_length=16000)
    mode: Literal["strict", "balanced", "dirty"] = "balanced"
    min_syllables: int = Field(default=3, ge=2, le=8)
    max_syllables: int = Field(default=8, ge=2, le=12)
    max_syllable_delta: int = Field(default=1, ge=0, le=2)
    include_internal: bool = True
    min_similarity: float = Field(default=0.67, ge=0, le=1)
    max_nodes: int = Field(default=120, ge=2, le=160)
    max_edges: int = Field(default=180, ge=1, le=300)
    overrides: list[PronunciationOverride] = Field(default_factory=list, max_length=512)

    @model_validator(mode="after")
    def validate_window(self) -> "GraphBuildRequest":
        if self.text.count("\n") >= 64:
            raise ValueError("Höchstens 64 LF-getrennte Zeilen pro Graph; einen Ausschnitt auswählen.")
        tokens = re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)*", self.text, re.UNICODE)
        if not tokens:
            raise ValueError("Der Text muss mindestens ein Wort enthalten.")
        if any(len(token) > 160 for token in tokens):
            raise ValueError("Ein Wort darf höchstens 160 Zeichen enthalten; außergewöhnlich lange Folgen aufteilen.")
        if self.max_syllables < self.min_syllables:
            raise ValueError("max_syllables darf nicht kleiner als min_syllables sein.")
        keys = [(item.line_index, item.word_index) for item in self.overrides]
        if len(keys) != len(set(keys)):
            raise ValueError("Eine Wortstelle darf nur eine Aussprachekorrektur erhalten.")
        if sum(len(syllable) for item in self.overrides for syllable in item.syllables) > 8192:
            raise ValueError("Höchstens 8192 manuelle Lautsymbole pro Graph; einen Ausschnitt auswählen.")
        return self


class GraphWord(ApiModel):
    word_index: int
    text: str
    char_start: int
    char_end: int
    start_syllable: int
    end_syllable: int
    phonetic_syllables: list[list[str]]
    stress: list[int]
    origin: Literal["rule_based", "manual"]
    analysis_notes: list[str] = Field(default_factory=list)


class GraphLine(ApiModel):
    line_index: int
    text: str
    char_start: int
    char_end: int
    words: list[GraphWord]
    phonetic_syllables: list[list[str]]
    stress: list[int]


class GraphNode(ApiModel):
    id: str
    line_index: int
    char_start: int
    char_end: int
    start_word: int
    end_word: int
    start_syllable: int
    end_syllable: int
    text: str
    phonetic_syllables: list[list[str]]
    stress: list[int]
    kind: Literal["terminal", "internal"]
    origin: Literal["rule_based", "manual"]
    source: Optional[dict[str, Any]] = None


class GraphProfile(ApiModel):
    anchor: float = Field(ge=0, le=1)
    terminal: float = Field(ge=0, le=1)
    vowels: float = Field(ge=0, le=1)
    consonants: float = Field(ge=0, le=1)
    stress: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    rap_anchors: float = Field(default=0, ge=0, le=1)
    consonant_grip: float = Field(default=0, ge=0, le=1)


class SyllableAlignment(ApiModel):
    left_index: Optional[int]
    right_index: Optional[int]
    vowel_similarity: float
    coda_similarity: float
    stress_match: bool


class GraphEdge(ApiModel):
    id: str
    source: str
    target: str
    kind: Literal["clean", "slant", "flex"]
    score: float
    profile: GraphProfile
    alignment: list[SyllableAlignment]
    deviations: list[str]
    required_operations: list[str]
    basis: Literal["exact", "segment", "rap_pattern"] = "segment"
    evidence: list[str] = Field(default_factory=list)
    status: Literal["proposed"] = "proposed"


class GraphResponse(ApiModel):
    version: str = "reimgraph/2"
    text: str
    mode: Literal["strict", "balanced", "dirty"]
    lines: list[GraphLine]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    warnings: list[str]
    analysis_notes: list[str] = Field(default_factory=list)
    truncated: bool
