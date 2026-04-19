"""
Phase-3 scoring tests.

Strategy: build real RhymeWindows via the extractor (no hand-mocked windows —
that would only test the math, not the perceptual claim), then assert ordering
between positive / borderline / negative candidates against a fixed query.

Query line (carries two /aɪ/ anchors, classic diphthong chain):
    "Leib Seele Probleme wie das Leben leicht nehmen"

Candidates:
    POS_1  "Eis Reise Themen wie das Schweben weit gehen"   ← matching /aɪ/ chain, parallel rhythm
    POS_2  "Zeit Beine Szenen wie das Leben weit drehen"    ← /aɪ/ + /eː/, similar rhythm
    BORD_1 "Leben Themen Probleme wie das Schweben"         ← /eː/-heavy, only one /aɪ/
    BORD_2 "Haus Maus Brause wie das Tauben laut rufen"     ← /aʊ/ chain (different diphthong)
    NEG_1  "interaktiven literarischen Suffixen"            ← academic, no /aɪ/ anchors
    NEG_2  "Buch Tisch Lampe"                               ← short, no anchor overlap
    NEG_3  "Ofen Boden Hose"                                ← back-vowel band, opposite colour
"""
from __future__ import annotations

import pytest
from app.services.rhyme_window_extractor import build_line_parse, extract_default_windows
from app.services.rhyme_window_scoring import (
    anchor_score, vowel_run_score, rhythm_score, grip_score,
    total_score, score_breakdown,
    W_ANCHOR, W_VOWEL_RUN, W_RHYTHM, W_GRIP,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

def window(text: str):
    line = build_line_parse(text)
    wins = extract_default_windows(line)
    assert wins, f"No window for: {text!r}"
    return wins[0]


QUERY_TEXT = "Leib Seele Probleme wie das Leben leicht nehmen"

CANDIDATES = {
    "POS_1":  "Eis Reise Themen wie das Schweben weit gehen",
    "POS_2":  "Zeit Beine Szenen wie das Leben weit drehen",
    "BORD_1": "Leben Themen Probleme wie das Schweben",
    "BORD_2": "Haus Maus Brause wie das Tauben laut rufen",
    "NEG_1":  "interaktiven literarischen Suffixen",
    "NEG_2":  "Buch Tisch Lampe",
    "NEG_3":  "Ofen Boden Hose",
}


@pytest.fixture(scope="module")
def query_window():
    return window(QUERY_TEXT)


@pytest.fixture(scope="module")
def cand_windows():
    return {k: window(v) for k, v in CANDIDATES.items()}


# ── Weight invariants ───────────────────────────────────────────────────────

class TestWeights:
    def test_weights_sum_to_one(self):
        assert abs((W_ANCHOR + W_VOWEL_RUN + W_RHYTHM + W_GRIP) - 1.0) < 1e-9

    def test_anchor_is_dominant(self):
        # Anchor must outweigh every other single component
        assert W_ANCHOR > W_VOWEL_RUN
        assert W_ANCHOR > W_RHYTHM
        assert W_ANCHOR > W_GRIP


# ── Self-match invariant ────────────────────────────────────────────────────

class TestSelfMatch:
    def test_self_match_total_is_one(self, query_window):
        assert total_score(query_window, query_window) == pytest.approx(1.0)

    def test_self_match_all_subscores_one(self, query_window):
        bd = score_breakdown(query_window, query_window)
        assert bd["anchor"]    == pytest.approx(1.0)
        assert bd["vowel_run"] == pytest.approx(1.0)
        assert bd["rhythm"]    == pytest.approx(1.0)
        assert bd["grip"]      == pytest.approx(1.0)

    def test_self_match_for_every_candidate(self, cand_windows):
        for name, w in cand_windows.items():
            assert total_score(w, w) == pytest.approx(1.0), f"self-match failed for {name}"


# ── Range invariants ────────────────────────────────────────────────────────

class TestRange:
    def test_all_subscores_in_unit_range(self, query_window, cand_windows):
        for name, w in cand_windows.items():
            bd = score_breakdown(query_window, w)
            for k, v in bd.items():
                assert 0.0 <= v <= 1.0, f"{name}.{k}={v} out of [0,1]"


# ── Ordering: positive > borderline > negative ──────────────────────────────

class TestOrdering:
    def test_pos1_beats_neg1(self, query_window, cand_windows):
        # Diphthong-chain match must beat academic suffix cluster
        s_pos = total_score(query_window, cand_windows["POS_1"])
        s_neg = total_score(query_window, cand_windows["NEG_1"])
        assert s_pos > s_neg, f"POS_1={s_pos:.3f} not > NEG_1={s_neg:.3f}"

    def test_pos1_beats_neg3(self, query_window, cand_windows):
        # Front /aɪ/-chain must beat back-vowel band
        s_pos = total_score(query_window, cand_windows["POS_1"])
        s_neg = total_score(query_window, cand_windows["NEG_3"])
        assert s_pos > s_neg, f"POS_1={s_pos:.3f} not > NEG_3={s_neg:.3f}"

    def test_pos2_beats_neg2(self, query_window, cand_windows):
        s_pos = total_score(query_window, cand_windows["POS_2"])
        s_neg = total_score(query_window, cand_windows["NEG_2"])
        assert s_pos > s_neg, f"POS_2={s_pos:.3f} not > NEG_2={s_neg:.3f}"

    def test_borderline_between_pos_and_neg(self, query_window, cand_windows):
        # BORD_1 has one /aɪ/ + lots of /eː/ — should land between POS_1 and NEG_1
        s_pos  = total_score(query_window, cand_windows["POS_1"])
        s_bord = total_score(query_window, cand_windows["BORD_1"])
        s_neg  = total_score(query_window, cand_windows["NEG_1"])
        assert s_pos >= s_bord, f"POS_1={s_pos:.3f} should be >= BORD_1={s_bord:.3f}"
        assert s_bord >= s_neg, f"BORD_1={s_bord:.3f} should be >= NEG_1={s_neg:.3f}"

    def test_different_diphthong_loses_to_same_diphthong(self, query_window, cand_windows):
        # /aʊ/-chain (BORD_2) vs /aɪ/-chain (POS_1) against /aɪ/ query
        s_pos  = total_score(query_window, cand_windows["POS_1"])
        s_bord = total_score(query_window, cand_windows["BORD_2"])
        assert s_pos > s_bord, (
            f"Same-diphthong POS_1={s_pos:.3f} should beat "
            f"different-diphthong BORD_2={s_bord:.3f}"
        )


# ── Sub-score sanity ────────────────────────────────────────────────────────

class TestSubScores:
    def test_anchor_zero_for_disjoint_anchors(self, query_window, cand_windows):
        # NEG_1 has no /aɪ/ at all → anchor overlap must be 0
        a = anchor_score(query_window, cand_windows["NEG_1"])
        assert a == 0.0, f"expected 0 anchor overlap with NEG_1, got {a}"

    def test_anchor_high_for_matching_diphthong_chain(self, query_window, cand_windows):
        a = anchor_score(query_window, cand_windows["POS_1"])
        assert a >= 0.4, f"expected meaningful anchor overlap, got {a}"

    def test_grip_below_one_for_disjoint_consonants(self, query_window, cand_windows):
        g = grip_score(query_window, cand_windows["NEG_2"])
        assert g < 1.0

    def test_rhythm_penalises_length_mismatch(self, query_window, cand_windows):
        # NEG_2 ("Buch Tisch Lampe") is much shorter than the query
        r = rhythm_score(query_window, cand_windows["NEG_2"])
        assert r < 0.8, f"expected length penalty, got {r}"


# ── Diagnostic dump (helps reading failures) ────────────────────────────────

class TestDiagnostic:
    def test_print_all_breakdowns(self, query_window, cand_windows, capsys):
        print(f"\nQuery: {QUERY_TEXT!r}")
        print(f"  anchors={query_window.anchor_nuclei}")
        rows = []
        for name, w in cand_windows.items():
            bd = score_breakdown(query_window, w)
            rows.append((name, bd))
        rows.sort(key=lambda r: r[1]["total"], reverse=True)
        for name, bd in rows:
            print(
                f"  {name:6s} total={bd['total']:.3f}  "
                f"anchor={bd['anchor']:.2f}  vrun={bd['vowel_run']:.2f}  "
                f"rhy={bd['rhythm']:.2f}  grip={bd['grip']:.2f}"
            )
        # This test always passes — it just emits diagnostic output
        assert True
