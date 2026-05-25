from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FeatureTarget(str, Enum):
    RHYME = "rhyme"
    TERMINAL = "terminal"


class Mode(str, Enum):
    STRICT = "strict"
    BALANCED = "balanced"
    DIRTY = "dirty"
    MULTISYLLABIC = "multisyllabic"
    HARDCORE = "hardcore"
    END_RHYME = "endRhyme"


class RawWeights(ApiModel):
    stress: float = Field(0.35, ge=0, le=1)
    vowelCore: float = Field(0.35, ge=0, le=1)
    tail: float = Field(0.2, ge=0, le=1)
    syllableFlex: float = Field(0.1, ge=0, le=1)


class Thresholds(ApiModel):
    maxSyllableDelta: int
    maxStressDistance: int
    maxVowelDistance: float
    minTailSimilarity: float


class ModePreset(ApiModel):
    description: str
    target: FeatureTarget
    thresholds: Thresholds
    defaultWeights: RawWeights


class ModesResponse(ApiModel):
    modes: dict[Mode, ModePreset]


class AnalyzeRequest(ApiModel):
    word: str = Field(min_length=1)


class SearchRequest(ApiModel):
    query: str = Field(min_length=1)
    mode: Mode = Mode.BALANCED
    weights: Optional[RawWeights] = None
    limit: int = Field(30, ge=1, le=500)
    debug: bool = False


class ValidationMetrics(ApiModel):
    syllableDelta: int
    stressDistance: int
    vowelDistance: float
    tailSimilarity: float


class ValidationResult(ApiModel):
    valid: bool
    reasons: List[str]
    metrics: ValidationMetrics


class ScoreBreakdown(ApiModel):
    stress: float
    vowelCore: float
    tail: float
    syllableFlex: float


# Internes Domain-Modell (snake_case)
class ParsedWord(BaseModel):
    text: str
    phonetic: List[str]
    syllable_count: int
    stress_pattern: List[int]
    rhyme_span: List[str]
    vowel_spine: List[str]
    tail: List[str]
    terminal_span: List[str]
    terminal_vowel_spine: List[str]
    terminal_tail: List[str]


# API-DTO (camelCase)
class PhoneticFeatures(ApiModel):
    text: str
    phonetic: List[str]
    syllableCount: int
    stressPattern: List[int]
    rhymeSpan: List[str]
    vowelSpine: List[str]
    tail: List[str]
    terminalSpan: List[str]
    terminalVowelSpine: List[str]
    terminalTail: List[str]

    @classmethod
    def from_parsed(cls, p: ParsedWord) -> "PhoneticFeatures":
        return cls(
            text=p.text,
            phonetic=p.phonetic,
            syllableCount=p.syllable_count,
            stressPattern=p.stress_pattern,
            rhymeSpan=p.rhyme_span,
            vowelSpine=p.vowel_spine,
            tail=p.tail,
            terminalSpan=p.terminal_span,
            terminalVowelSpine=p.terminal_vowel_spine,
            terminalTail=p.terminal_tail,
        )


class RankedCandidate(PhoneticFeatures):
    score: float
    breakdown: ScoreBreakdown
    validation: ValidationResult
    activeVowels: List[str]
    activeTail: List[str]


class RejectedCandidate(PhoneticFeatures):
    validation: ValidationResult
    activeVowels: List[str]
    activeTail: List[str]


class SearchResponse(ApiModel):
    query: PhoneticFeatures
    mode: Mode
    target: FeatureTarget
    thresholds: Thresholds
    weights: RawWeights
    results: List[RankedCandidate]
    rejected: Optional[List[RejectedCandidate]] = None
