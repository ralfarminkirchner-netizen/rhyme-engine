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
from app.services.rhyme_window_extractor import build_line_parse, extract_default_windows


def _syllable_delta(a: int, b: int) -> int:
    return abs(a - b)

def _stress_distance(a: List[int], b: List[int]) -> int:
    return sum(
        (a[i] if i < len(a) else 0) != (b[i] if i < len(b) else 0)
        for i in range(max(len(a), len(b)))
    )

def _vowel_distance(a: List[str], b: List[str]) -> float:
    n = max(len(a), len(b))
    if n == 0: return 1.0
    penalty = total = 0.0
    for i in range(n):
        av = a[i] if i < len(a) else "_"
        bv = b[i] if i < len(b) else "_"
        w = n - i
        total += w
        if av != bv: penalty += w
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

def _anchors_for(word: ParsedWord) -> List[str]:
    """
    Extract anchor_nuclei (stressed vowels) for a single word via the
    phrase-layer extractor.  Falls back to vowel_spine when the extractor
    returns no window (should never happen for a non-empty word).

    Anchor nuclei capture the *dominant* vowel colour of a word rather than
    its raw suffix pattern.  This prevents suffix-heavy academic words
    (e.g. -aktiven, -arischen) from matching words whose primary vowel is
    completely different.
    """
    line = build_line_parse(word.text)
    wins = extract_default_windows(line)
    if wins and wins[0].anchor_nuclei:
        return wins[0].anchor_nuclei
    return list(word.vowel_spine)  # safe fallback


class RhymeEngine:
    def __init__(self, word_list: Sequence[ParsedWord]):
        self.word_list = list(word_list)
        # Pre-compute anchor_nuclei for every word in the corpus.
        # Cheap at init; avoids N-times re-parsing during search calls.
        self._anchors: dict[str, List[str]] = {
            w.text: _anchors_for(w) for w in self.word_list
        }

    def get_modes(self) -> ModesResponse:
        return ModesResponse(modes=get_all_presets())

    def _to_dto(self, p: ParsedWord) -> PhoneticFeatures:
        return PhoneticFeatures.from_parsed(p)

    def _validate(
        self, query: ParsedWord, candidate: ParsedWord,
        thresholds: Thresholds, target: FeatureTarget,
        query_anchors: Optional[List[str]] = None,
        cand_anchors:  Optional[List[str]] = None,
    ) -> ValidationResult:
        _, qt = _select_features(query,     target)
        _, ct = _select_features(candidate, target)

        if target == FeatureTarget.TERMINAL:
            # Classical end-rhyme: compare the terminal vowel spine as before
            qv, _ = _select_features(query,     target)
            cv, _ = _select_features(candidate, target)
            vowel_dist = _vowel_distance(qv, cv)
        else:
            # Rap / phrase-aware rhyme: compare anchor nuclei (stressed vowels).
            # This prevents suffix-pattern matches like -aktiven / -arischen
            # from passing when the primary stressed vowel is completely different.
            qa = query_anchors  if query_anchors  is not None else list(query.vowel_spine)
            ca = cand_anchors   if cand_anchors   is not None else list(candidate.vowel_spine)
            vowel_dist = _vowel_distance(qa, ca)

        metrics = ValidationMetrics(
            syllableDelta   = _syllable_delta(query.syllable_count, candidate.syllable_count),
            stressDistance  = _stress_distance(query.stress_pattern, candidate.stress_pattern),
            vowelDistance   = vowel_dist,
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

        # Anchor nuclei for the query (computed once per search call).
        # For phrase queries (multi-word) the full window's anchors are used;
        # for single words this degrades gracefully to the word's stressed vowels.
        q_anchors = _anchors_for(query)

        for candidate in self.word_list:
            if candidate.text == query.text:
                continue
            c_anchors = self._anchors.get(candidate.text, _anchors_for(candidate))
            val  = self._validate(query, candidate, thresholds, target,
                                  query_anchors=q_anchors, cand_anchors=c_anchors)
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
