from __future__ import annotations
from typing import List, Optional, Sequence
from app.schemas.rhyme import (
    FeatureTarget, Mode, ParsedWord, PhoneticFeatures, RawWeights,
    Thresholds, ValidationMetrics, ValidationResult,
    ScoreBreakdown, RankedCandidate, RejectedCandidate, SearchResponse,
)
from app.services.phonological_distance import tail_similarity
from app.services.presets import get_preset, get_all_presets
from app.schemas.rhyme import ModesResponse


def _syllable_delta(a: int, b: int) -> int:
    return abs(a - b)

def _stress_distance(a: List[int], b: List[int]) -> int:
    return sum(
        (a[i] if i < len(a) else 0) != (b[i] if i < len(b) else 0)
        for i in range(max(len(a), len(b)))
    )

_VOWEL_TAIL_WINDOW = 4

# End-Anchor-Gate: Tail-Schwelle, unter der ein Score auf ANCHOR_GATE_CAP gedeckelt wird.
ANCHOR_GATE_THRESHOLD = 0.5
ANCHOR_GATE_CAP = 0.35

def _vowel_distance(a: List[str], b: List[str]) -> float:
    """End-gewichteter Vokal-Vergleich mit rechtsbündigem Tail-Window.

    Endreim ist primary signal: nur die letzten _VOWEL_TAIL_WINDOW Vokale
    werden verglichen, rechtsbündig ausgerichtet und end-gewichtet (der letzte
    Vokal hat das höchste Gewicht).
    """
    a_tail = a[-_VOWEL_TAIL_WINDOW:] if a else []
    b_tail = b[-_VOWEL_TAIL_WINDOW:] if b else []
    n = max(len(a_tail), len(b_tail))
    if n == 0:
        return 1.0  # behält das Original-Semantik: keine Vokale → max Distanz
    # Rechtsbündig auffüllen: kürzere Liste bekommt Platzhalter LINKS,
    # damit Position n-1 immer der LETZTE Vokal ist.
    pa = ["_"] * (n - len(a_tail)) + a_tail
    pb = ["_"] * (n - len(b_tail)) + b_tail
    penalty = total = 0.0
    for i in range(n):
        w = i + 1  # i=0: Window-Anfang (kleinstes Gewicht); i=n-1: Endposition
        total += w
        if pa[i] != pb[i]:
            penalty += w
    return penalty / total if total else 1.0

def _normalize(w: RawWeights) -> RawWeights:
    s = w.stress + w.vowelCore + w.tail + w.syllableFlex
    if s <= 0: return w
    return RawWeights(stress=w.stress/s, vowelCore=w.vowelCore/s, tail=w.tail/s, syllableFlex=w.syllableFlex/s)

def _sim(distance: float, max_good: float) -> float:
    if max_good <= 0: return 1.0 if distance == 0 else 0.0
    return max(0.0, min(1.0, 1.0 - distance / max_good))

def _select_features(entry: ParsedWord, target: FeatureTarget):
    if target == FeatureTarget.TERMINAL:
        return entry.terminal_vowel_spine, entry.terminal_tail
    return entry.vowel_spine, entry.tail


class RhymeEngine:
    def __init__(self, word_list: Sequence[ParsedWord]):
        self.word_list = list(word_list)

    def get_modes(self) -> ModesResponse:
        return ModesResponse(modes=get_all_presets())

    def _to_dto(self, p: ParsedWord) -> PhoneticFeatures:
        return PhoneticFeatures.from_parsed(p)

    def _validate(
        self, query: ParsedWord, candidate: ParsedWord,
        thresholds: Thresholds, target: FeatureTarget,
    ) -> ValidationResult:
        qv, qt = _select_features(query, target)
        cv, ct = _select_features(candidate, target)
        metrics = ValidationMetrics(
            syllableDelta   = _syllable_delta(query.syllable_count, candidate.syllable_count),
            stressDistance  = _stress_distance(query.stress_pattern, candidate.stress_pattern),
            vowelDistance   = _vowel_distance(qv, cv),
            tailSimilarity  = tail_similarity(qt, ct),
        )
        reasons = []
        if metrics.syllableDelta  > thresholds.maxSyllableDelta:  reasons.append("Silbenzahl zu weit entfernt")
        if metrics.stressDistance > thresholds.maxStressDistance: reasons.append("Betonungsmuster passt nicht")
        if metrics.vowelDistance  > thresholds.maxVowelDistance:  reasons.append("Vokalkern zu unähnlich")
        if metrics.tailSimilarity < thresholds.minTailSimilarity: reasons.append("Ausklang zu unähnlich")
        return ValidationResult(valid=len(reasons)==0, reasons=reasons, metrics=metrics)

    def _score(
        self, validation: ValidationResult, weights: RawWeights, thresholds: Thresholds,
    ) -> tuple[float, ScoreBreakdown]:
        w = _normalize(weights)
        bd = ScoreBreakdown(
            stress      = _sim(validation.metrics.stressDistance, max(1, thresholds.maxStressDistance+1)),
            vowelCore   = 1.0 - validation.metrics.vowelDistance,
            tail        = validation.metrics.tailSimilarity,
            syllableFlex= _sim(validation.metrics.syllableDelta, max(1, thresholds.maxSyllableDelta+1)),
        )
        score = bd.stress*w.stress + bd.vowelCore*w.vowelCore + bd.tail*w.tail + bd.syllableFlex*w.syllableFlex
        # End-Anchor-Gate: Endreim ist primary signal. Wenn der Tail zu schwach
        # ist, darf der Score auch bei perfektem Vokal-Spine nicht über
        # ANCHOR_GATE_CAP hinaus. Hard cap, kein Smoothing.
        if validation.metrics.tailSimilarity < ANCHOR_GATE_THRESHOLD:
            score = min(score, ANCHOR_GATE_CAP)
        return score, bd

    def search(
        self,
        query: ParsedWord,
        mode: Mode,
        custom_weights: Optional[RawWeights] = None,
        limit: int = 30,
        include_debug: bool = False,
    ) -> SearchResponse:
        preset     = get_preset(mode)
        weights    = custom_weights or preset.defaultWeights
        thresholds = preset.thresholds
        target     = preset.target
        query_dto  = self._to_dto(query)

        results:  List[RankedCandidate]  = []
        rejected: List[RejectedCandidate]= []

        for candidate in self.word_list:
            if candidate.text == query.text:
                continue
            val  = self._validate(query, candidate, thresholds, target)
            dto  = self._to_dto(candidate)
            av, at = _select_features(candidate, target)
            payload = dto.model_dump()

            if val.valid:
                score, bd = self._score(val, weights, thresholds)
                results.append(RankedCandidate(**payload, activeVowels=av, activeTail=at, score=score, breakdown=bd, validation=val))
            elif include_debug:
                rejected.append(RejectedCandidate(**payload, activeVowels=av, activeTail=at, validation=val))

        results.sort(key=lambda x: x.score, reverse=True)
        return SearchResponse(
            query     = query_dto,
            mode      = mode,
            target    = target,
            thresholds= thresholds,
            weights   = weights,
            results   = results[:limit],
            rejected  = rejected if include_debug else None,
        )
