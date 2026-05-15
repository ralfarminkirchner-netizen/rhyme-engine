from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.schemas.rhyme import FeatureTarget, RawWeights, Thresholds
from app.services.parser import parse_german_word
from app.services.rhyme_engine import (
    ANCHOR_GATE_CAP,
    ANCHOR_GATE_THRESHOLD,
    RhymeEngine,
    _vowel_distance,
)


REAL_END_RHYMES = {"internet", "parkett", "tablett", "respekt"}
FALSE_POSITIVES = {
    "aktienkapitals",
    "attentäterin",
    "attenborough",
    "patientenkontakt",
}

CORPUS = [
    "internet",
    "parkett",
    "tablett",
    "respekt",
    "aktienkapitals",
    "attentäterin",
    "attenborough",
    "patientenkontakt",
]

BALANCED_WEIGHTS = RawWeights(stress=0.30, vowelCore=0.35, tail=0.25, syllableFlex=0.10)
OPEN_THRESHOLDS = Thresholds(
    maxSyllableDelta=10,
    maxStressDistance=10,
    maxVowelDistance=1.0,
    minTailSimilarity=0.0,
)


def _rank_with_end_anchor(query: str, candidates: list[str]) -> dict[str, float]:
    q = parse_german_word(query)
    engine = RhymeEngine([parse_german_word(w) for w in candidates])

    scored: list[tuple[str, float]] = []
    for candidate in engine.word_list:
        validation = engine._validate(q, candidate, OPEN_THRESHOLDS, FeatureTarget.TERMINAL)
        score, _breakdown = engine._score(validation, BALANCED_WEIGHTS, OPEN_THRESHOLDS)
        scored.append((candidate.text, score))

    return dict(sorted(scored, key=lambda item: item[1], reverse=True))


def test_false_positives_rank_below_real_end_rhymes():
    scores = _rank_with_end_anchor("schattenkabinett", CORPUS)

    worst_real = min(scores[word] for word in REAL_END_RHYMES)
    best_false_positive = max(scores[word] for word in FALSE_POSITIVES)

    assert worst_real > best_false_positive


def test_real_end_rhymes_are_top_cluster():
    scores = _rank_with_end_anchor("schattenkabinett", CORPUS)
    ranked_words = list(scores)

    assert set(ranked_words[:4]) == REAL_END_RHYMES


def test_internet_at_tail_threshold_is_not_capped():
    q = parse_german_word("schattenkabinett")
    internet = parse_german_word("internet")
    engine = RhymeEngine([internet])

    validation = engine._validate(q, internet, OPEN_THRESHOLDS, FeatureTarget.TERMINAL)
    score, _breakdown = engine._score(validation, BALANCED_WEIGHTS, OPEN_THRESHOLDS)

    assert validation.metrics.vowelDistance == 0.0
    assert validation.metrics.tailSimilarity == pytest.approx(ANCHOR_GATE_THRESHOLD)
    assert score > ANCHOR_GATE_CAP


def test_anchor_gate_caps_high_vowel_low_tail_pair():
    q = parse_german_word("schattenkabinett")
    weak_tail = parse_german_word("weck")
    engine = RhymeEngine([weak_tail])

    validation = engine._validate(q, weak_tail, OPEN_THRESHOLDS, FeatureTarget.TERMINAL)
    score, _breakdown = engine._score(validation, BALANCED_WEIGHTS, OPEN_THRESHOLDS)

    assert validation.metrics.vowelDistance == 0.0
    assert validation.metrics.tailSimilarity < ANCHOR_GATE_THRESHOLD
    assert score == pytest.approx(ANCHOR_GATE_CAP)


def test_vowel_distance_is_end_weighted():
    base = ["a", "i", "u", "e"]
    mismatch_front = ["o", "i", "u", "e"]
    mismatch_back = ["a", "i", "u", "o"]

    assert _vowel_distance(base, mismatch_back) > _vowel_distance(base, mismatch_front)


def test_vowel_distance_uses_last_four_vowels_only():
    assert _vowel_distance(
        ["a", "i", "u", "e", "o"],
        ["x", "i", "u", "e", "o"],
    ) == 0.0
