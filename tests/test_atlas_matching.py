"""Synthetic pronunciation pairs; no personal writing is embedded here."""
from copy import deepcopy

import pytest

from app.services.atlas_matching import compare_pronunciations
from app.services.atlas_phonetics import parse_ipa


def match(left, right, mode="dirty"):
    return compare_pronunciations(parse_ipa(left), parse_ipa(right), mode)


def test_strict_compares_all_phones_from_first_nucleus_and_ignores_initial_onset():
    result = match("/ˈkaː.ta.li.nɛl/", "/ˈʃaː.ta.li.nɛl/", "strict")
    assert result["kind"] == "exact" and result["matched_syllables"] == 4
    assert result["score"] == 1.0
    assert match("/kaː.ta.li.nɛl/", "/kaː.ta.mi.nɛl/", "strict") is None
    assert match("/kaː.ta.li.nɛl/", "/kaː.ta.li.nel/", "strict") is None


def test_strict_rejects_different_full_length_even_with_identical_suffix():
    assert match("/a.ta.li.nɛl/", "/ta.li.nɛl/", "strict") is None


def test_dirty_four_syllable_match_has_two_separated_anchors_and_variable_middle():
    result = match("/ˈkaː.ti.lo.nɛŋ/", "/ˈbaː.tə.la.mɛl/")
    assert result is not None and result["kind"] == "near"
    assert result["matched_syllables"] == 4
    assert result["details"]["anchor_count"] == 2
    assert result["details"]["alignment"][0]["left"] == 0
    assert result["details"]["alignment"][-1]["left"] == 3
    assert match("/ˈkaː.ti.lo.nɛŋ/", "/ˈbaː.tə.la.mɛl/", "balanced") is None


def test_balanced_accepts_ordered_near_vowels_and_weights_consonants():
    result = match("/ˈkaː.tɛ.lo.nɛl/", "/ˈbaː.deː.lo.nɛl/", "balanced")
    assert result is not None and result["matched_syllables"] == 4
    assert .76 <= result["score"] <= 1
    assert result["details"]["cadence_score"] == 1


def test_cross_language_e_ei_and_o_ou_near_families():
    left = parse_ipa("/ˈmeː.loː.ti.nɛl/", "de")
    right = parse_ipa("/ˈmeɪ.loʊ.di.nɛl/", "en")
    result = compare_pronunciations(left, right, "balanced")
    assert result is not None and result["kind"] == "near"
    assert result["details"]["alignment"][0]["nucleus_similarity"] == .86
    assert result["details"]["alignment"][1]["nucleus_similarity"] == .86
    assert compare_pronunciations(left, right, "strict") is None


@pytest.mark.parametrize("extra", ["mə", "mə.nə"])
def test_dirty_flex_aligns_internal_extra_syllables_and_keeps_endpoints(extra):
    result = match("/ˈkaː.tɛ.li.nɛl/", f"/ˈbaː.tɛ.{extra}.li.nɛl/")
    assert result is not None and result["kind"] == "flex"
    assert result["matched_syllables"] == 4
    assert result["details"]["gap_count"] == extra.count(".") + 1
    alignment = result["details"]["alignment"]
    assert alignment[0]["left"] == alignment[0]["right"] == 0
    assert alignment[-1]["left"] == 3
    assert alignment[-1]["right"] == 4 + extra.count(".")
    assert match("/ˈkaː.tɛ.li.nɛl/", f"/ˈbaː.tɛ.{extra}.li.nɛl/", "balanced") is None


def test_flex_is_symmetric_in_score_and_alignment():
    left, right = parse_ipa("/ˈkaː.tɛ.li.nɛl/"), parse_ipa("/ˈbaː.tɛ.mə.li.nɛl/")
    a = compare_pronunciations(left, right)
    b = compare_pronunciations(right, left)
    assert a["score"] == b["score"]
    assert [(item["left"], item["right"]) for item in a["details"]["alignment"]] == [
        (item["right"], item["left"]) for item in b["details"]["alignment"]
    ]


def test_shared_terminal_alone_cannot_become_a_four_syllable_match():
    assert match("/kaː.ti.lo.nɛl/", "/kuː.tu.mu.nɛl/") is None


def test_same_vowels_in_a_different_order_are_not_a_multisyllabic_rhyme():
    assert match("/kaː.ti.lo.nɛl/", "/kiː.to.na.mɛl/") is None


def test_long_sequences_need_more_than_first_and_last_anchor():
    assert match("/kaː.ti.lo.te.li.no.tɛl/", "/baː.tu.na.tu.na.ta.mɛl/") is None


def test_more_than_two_extra_syllables_and_short_suffix_coverage_are_rejected():
    assert match("/kaː.tɛ.li.nɛl/", "/baː.tɛ.mə.nə.lə.li.nɛl/") is None
    assert match("/kaː.nɛl/", "/baː.mə.nə.nɛl/") is None


def test_stress_changes_score_without_becoming_a_hard_gate():
    original = parse_ipa("/ˈkaː.tɛ.li.nɛl/")
    aligned = parse_ipa("/ˈbaː.deː.li.nɛl/")
    changed = deepcopy(aligned)
    changed["stress"] = [2, 0, 0, 0]
    a = compare_pronunciations(original, aligned, "balanced")
    b = compare_pronunciations(original, changed, "balanced")
    assert a is not None and b is not None
    assert a["score"] > b["score"]


def test_monosyllabic_shared_vowel_needs_coda_evidence():
    assert match("/kam/", "/kaf/") is None
    assert match("/kam/", "/ban/") is not None
    assert match("/zeː/", "/teː/")["kind"] == "exact"


def test_inputs_and_cached_parse_results_are_not_modified():
    left, right = parse_ipa("/kaː.tɛ.li.nɛl/"), parse_ipa("/baː.deː.li.nɛl/")
    originals = deepcopy((left, right))
    compare_pronunciations(left, right)
    assert (left, right) == originals


@pytest.mark.parametrize("bad", [{}, {"syllables": [["k"]]}, {"syllables": [["k"]], "nuclei": [""], "families": [""]}])
def test_missing_or_nonnuclear_pronunciations_do_not_match(bad):
    assert compare_pronunciations(bad, parse_ipa("/ka/")) is None


def test_invalid_mode_is_explicit():
    with pytest.raises(ValueError, match="mode"):
        compare_pronunciations({}, {}, "unknown")
