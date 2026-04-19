"""
Gold tests for the Phrase-Layer extractor.

Three gold patterns (derived from real German rap):

  Gold A – diphthong_anchor_chain
      "Leib Seele Probleme wie das Leben leicht nehmen"
      The stressed vowels of Leib and leicht both carry /aɪ/.
      Expected: anchor_nuclei.count("aɪ") >= 2, "eː" somewhere in vowel_run,
                tag "diphthong_anchor_chain", flow_shape != "flat".

  Gold B – parallel_question + diphthong chain
      "Wo bist du frei und wie entscheidest du dich?"
      A question with two question-words and two /aɪ/ anchors.
      Expected: parallel_shape == "question_parallel",
                anchor_nuclei.count("aɪ") >= 2,
                tags include both "question_parallel" and "diphthong_anchor_chain".

  Gold C – front_vowel_band
      "sehen setzen verletzen sprechen"
      Front vowels (eː, ɛ) dominate; grip consonants include t͡s and ç.
      Expected: tag "front_vowel_band", consonant_grip ∩ {t͡s, ç} non-empty.

Negative tests ensure that academic suffix clusters ("-aktiven", "-arischen")
do NOT accidentally trigger diphthong-anchor tags.
"""
from __future__ import annotations

import pytest
from app.services.rhyme_window_extractor import build_line_parse, extract_default_windows
from app.schemas.rhyme_window import LineParse, RhymeWindow


# ── Helpers ───────────────────────────────────────────────────────────────────

def full_window(text: str) -> RhymeWindow:
    """Parse *text* and return the full-line window (index 0)."""
    line = build_line_parse(text)
    windows = extract_default_windows(line)
    assert windows, f"No windows extracted for: {text!r}"
    return windows[0]


# ── build_line_parse ──────────────────────────────────────────────────────────

class TestBuildLineParse:
    def test_word_count(self):
        line = build_line_parse("sein schein allein")
        assert len(line.words) == 3

    def test_flat_stress_length_matches_syllables(self):
        line = build_line_parse("bewusstsein allein")
        assert len(line.flat_syllables) == len(line.flat_stress_slots)

    def test_flat_stress_is_binary(self):
        line = build_line_parse("Katastrophe Melodie Rhythmus")
        assert all(s in (0, 1) for s in line.flat_stress_slots)

    def test_sentence_shape_copy(self):
        line = build_line_parse("sein schein")
        assert line.sentence_shape == line.flat_stress_slots
        # Must be a separate list (no aliasing issue)
        line.flat_stress_slots.append(99)
        assert 99 not in line.sentence_shape

    def test_start_end_syllable_monotone(self):
        line = build_line_parse("sein schein allein")
        prev_end = 0
        for w in line.words:
            assert w.start_syllable == prev_end
            assert w.end_syllable > w.start_syllable
            prev_end = w.end_syllable

    def test_raw_text_preserved(self):
        text = "Leib und Seele"
        line = build_line_parse(text)
        assert line.raw_text == text

    def test_hyphenated_compound_splits(self):
        # "Leib-Seele-Probleme" must be split into 3 words
        line = build_line_parse("Leib-Seele-Probleme")
        assert len(line.words) == 3

    def test_punctuation_ignored(self):
        line1 = build_line_parse("sein schein allein")
        line2 = build_line_parse("sein, schein? allein!")
        assert len(line1.words) == len(line2.words)
        assert len(line1.flat_syllables) == len(line2.flat_syllables)

    def test_empty_string(self):
        line = build_line_parse("")
        assert line.words == []
        assert line.flat_syllables == []

    def test_single_word(self):
        line = build_line_parse("sein")
        assert len(line.words) == 1
        assert len(line.flat_syllables) == 1  # "sein" is monosyllabic


# ── extract_default_windows ───────────────────────────────────────────────────

class TestExtractDefaultWindows:
    def test_always_returns_at_least_one_window(self):
        line = build_line_parse("sein schein")
        assert len(extract_default_windows(line)) >= 1

    def test_full_window_covers_all_syllables(self):
        line = build_line_parse("sein schein allein")
        w = extract_default_windows(line)[0]
        assert w.start_syllable == 0
        assert w.end_syllable == len(line.flat_syllables)

    def test_tail_window_emitted_for_long_lines(self):
        # A line with 5+ syllables should emit a tail window
        line = build_line_parse("bewusstsein allein schein")
        windows = extract_default_windows(line)
        assert len(windows) >= 2

    def test_short_line_only_one_window(self):
        line = build_line_parse("sein")   # 1 syllable → no tail window
        assert len(extract_default_windows(line)) == 1

    def test_vowel_run_not_empty(self):
        w = full_window("sein schein allein")
        assert len(w.vowel_run) > 0

    def test_stress_slots_binary(self):
        w = full_window("sein schein allein")
        assert all(s in (0, 1) for s in w.stress_slots)

    def test_anchor_nuclei_are_vowels(self):
        from app.services.parser import is_vowel
        w = full_window("sein schein allein")
        for v in w.anchor_nuclei:
            assert is_vowel(v), f"Non-vowel in anchor_nuclei: {v!r}"

    def test_line_index_preserved(self):
        line = build_line_parse("sein schein")
        windows = extract_default_windows(line, line_index=7)
        assert all(w.line_index == 7 for w in windows)

    def test_no_window_for_empty_line(self):
        line = build_line_parse("")
        assert extract_default_windows(line) == []


# ── Gold A: diphthong_anchor_chain ────────────────────────────────────────────

class TestGoldA_DiphthongAnchorChain:
    """
    "Leib Seele Probleme wie das Leben leicht nehmen"
    The perceptually dominant anchors are the two /aɪ/ diphthongs in
    Leib and leicht — a classic diphthong anchor chain.
    """
    LINE = "Leib Seele Probleme wie das Leben leicht nehmen"

    def test_two_or_more_ai_in_anchors(self):
        w = full_window(self.LINE)
        assert w.anchor_nuclei.count("aɪ") >= 2, (
            f"Expected ≥2 'aɪ' in anchor_nuclei, got: {w.anchor_nuclei}"
        )

    def test_ee_in_vowel_run(self):
        w = full_window(self.LINE)
        assert "eː" in w.vowel_run, (
            f"Expected 'eː' (from Seele / nehmen) in vowel_run, got: {w.vowel_run}"
        )

    def test_diphthong_anchor_chain_tag(self):
        w = full_window(self.LINE)
        assert "diphthong_anchor_chain" in w.technique_tags, (
            f"Expected tag 'diphthong_anchor_chain', got: {w.technique_tags}"
        )

    def test_flow_shape_not_flat(self):
        w = full_window(self.LINE)
        assert w.flow_shape != "flat", (
            f"flow_shape should not be 'flat' for a rich diphthong line, got: {w.flow_shape!r}"
        )

    def test_anchor_count_gte_support(self):
        # A line with real content words must have meaningful stressed vowels
        w = full_window(self.LINE)
        assert len(w.anchor_nuclei) >= 2


# ── Gold B: parallel_question + diphthong_anchor_chain ───────────────────────

class TestGoldB_ParallelQuestionRhyme:
    """
    "Wo bist du frei und wie entscheidest du dich?"
    Two question words + "?" → question_parallel.
    Both "frei" and "entscheidest" carry /aɪ/ → diphthong_anchor_chain.
    """
    LINE = "Wo bist du frei und wie entscheidest du dich?"

    def test_question_parallel_shape(self):
        w = full_window(self.LINE)
        assert w.parallel_shape == "question_parallel", (
            f"Expected 'question_parallel', got: {w.parallel_shape!r}"
        )

    def test_question_parallel_tag(self):
        w = full_window(self.LINE)
        assert "question_parallel" in w.technique_tags, (
            f"Expected tag 'question_parallel', got: {w.technique_tags}"
        )

    def test_two_ai_anchors(self):
        w = full_window(self.LINE)
        assert w.anchor_nuclei.count("aɪ") >= 2, (
            f"Expected ≥2 'aɪ' anchors (frei + entscheidest), got: {w.anchor_nuclei}"
        )

    def test_diphthong_anchor_chain_tag(self):
        w = full_window(self.LINE)
        assert "diphthong_anchor_chain" in w.technique_tags, (
            f"Tags: {w.technique_tags}"
        )


# ── Gold C: front_vowel_band ──────────────────────────────────────────────────

class TestGoldC_FrontVowelBand:
    """
    "sehen setzen verletzen sprechen"
    Front vowels (eː, ɛ) account for >55 % of the vowel run.
    Grip consonants include t͡s (setzen / verletzen) and ç (sprechen).
    """
    LINE = "sehen setzen verletzen sprechen"

    def test_front_vowel_band_tag(self):
        w = full_window(self.LINE)
        assert "front_vowel_band" in w.technique_tags, (
            f"Expected tag 'front_vowel_band', got: {w.technique_tags}\n"
            f"vowel_run={w.vowel_run}"
        )

    def test_front_vowel_dominance(self):
        from app.services.rhyme_window_extractor import FRONT_VOWELS
        REDUCED = frozenset({"ə", "ɐ"})
        w = full_window(self.LINE)
        coloured = [v for v in w.vowel_run if v not in REDUCED]
        nc = len(coloured)
        front_n = sum(1 for v in coloured if v in FRONT_VOWELS)
        assert nc > 0, "No coloured vowels found"
        assert front_n / nc >= 0.55, (
            f"Front vowel ratio {front_n}/{nc}={front_n/nc:.2f} < 0.55\n"
            f"coloured vowels={coloured}"
        )

    def test_grip_includes_affricate_or_palatal(self):
        w = full_window(self.LINE)
        target = {"t͡s", "ç"}
        assert target & set(w.consonant_grip), (
            f"Expected t͡s or ç in consonant_grip, got: {w.consonant_grip}"
        )

    def test_no_diphthong_anchor(self):
        w = full_window(self.LINE)
        assert "diphthong_anchor_chain" not in w.technique_tags


# ── Negative tests ────────────────────────────────────────────────────────────

class TestNegative:
    """
    Academic suffix clusters should NOT trigger diphthong tags.
    They may or may not trigger front_vowel_band (the shared suffix ɪ·v·ə·n
    is front-heavy), but they must never produce fake diphthong anchor chains.
    """

    def test_no_diphthong_anchor_in_academic_suffixes(self):
        w = full_window("interaktiven literarischen Suffixen")
        assert "diphthong_anchor_chain" not in w.technique_tags

    def test_no_ai_anchor_in_academic_suffixes(self):
        w = full_window("interaktiven literarischen Suffixen")
        assert "aɪ" not in w.anchor_nuclei

    def test_plain_noun_has_no_parallel_shape(self):
        w = full_window("Buch Tisch Lampe")
        assert w.parallel_shape == "none"

    def test_statement_without_question_mark_is_not_parallel(self):
        # "wie" appears but no "?" → should not be question_parallel
        w = full_window("Ich weiß wie das geht")
        assert w.parallel_shape == "none"

    def test_anchor_nuclei_only_diphthongs_for_simple_line(self):
        # "sein" → only /aɪ/ in phonetics
        w = full_window("sein")
        assert w.anchor_nuclei == ["aɪ"]


# ── Vowel-run ordering ────────────────────────────────────────────────────────

class TestVowelRunOrdering:
    def test_vowel_run_left_to_right(self):
        # "sein schein" → [aɪ, aɪ]
        w = full_window("sein schein")
        assert w.vowel_run == ["aɪ", "aɪ"]

    def test_support_vowels_from_unstressed(self):
        # "allein" → stress=[0,1], syl1=[a,l], syl2=[aɪ,n]
        # anchor = [aɪ], support = [a]
        w = full_window("allein")
        assert "aɪ" in w.anchor_nuclei
        assert "a" in w.support_vowels

    def test_vowel_run_equals_anchor_plus_support(self):
        w = full_window("sein schein allein")
        # Every vowel must appear in exactly anchor + support
        combined = sorted(w.anchor_nuclei + w.support_vowels)
        assert sorted(w.vowel_run) == combined
