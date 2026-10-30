"""Attested IPA structure, without private lyric or phrase fixtures."""
import pytest

from app.services.atlas_phonetics import nucleus_family, parse_ipa, split_ipa_variants


@pytest.mark.parametrize("ipa,count,families", [
    ("/haʊ̯s/", 1, ["au"]),
    ("/ˈhaːzə/", 2, ["a", "schwa"]),
    ("/paˈt͡si̯ɛnt/", 2, ["a", "e"]),
    ("/ˈɡaʁtn̩/", 2, ["a", "schwa"]),
    ("/ˈbaʊ̯ɐ/", 2, ["au", "schwa"]),
    ("/biːɐ̯/", 1, ["i"]),
    ("/ˈlɛːʁə/", 2, ["e", "schwa"]),
    ("/ˈnaziɡoˈʁɛŋ/", 4, ["a", "i", "o", "e"]),
    ("/ˈbɛksteɪd͡ʒ/", 2, ["e", "ei"]),
    ("/ˈbɛksteːt͡ʃ/", 2, ["e", "e"]),
    ("/ˈbæˌtɝ/", 2, ["a", "schwa"]),
    ("/wɝld/", 1, ["schwa"]),
    ("/ˈlɛŋɡwɪd͡ʒ/", 2, ["e", "i"]),
    ("/ˈoʊpən/", 2, ["ou", "schwa"]),
    ("/ˈʌndɚ/", 2, ["a", "schwa"]),
    ("/bɔ̃ː/", 1, ["o"]),
    ("/ˈfʏlə/", 2, ["ue", "schwa"]),
    ("/aɪ̯ː/", 1, ["ai"]),
    ("/ă/", 1, ["a"]),
    ("/aɪ̑/", 1, ["ai"]),
])
def test_nucleus_counts_and_ordered_families(ipa, count, families):
    result = parse_ipa(ipa)
    assert result["raw_ipa"] == ipa
    assert result["syllable_count"] == count
    assert len(result["syllables"]) == len(result["stress"]) == len(result["nuclei"]) == count
    assert result["families"] == families
    assert result["signature"] == "-".join(families)
    assert result["first_family"] == families[0] and result["last_family"] == families[-1]
    assert result["unknown"] == []


def test_primary_and_secondary_stress_keep_different_levels():
    result = parse_ipa("/ˈhaʊ̯sˌtyːɐ̯/", "de")
    assert result["stress"] == [1, 2]
    assert result["syllable_count"] == 2
    assert result["syllables"][1] == ["t", "yː", "ɐ̯"]


def test_glottal_stop_preserves_compound_boundary_and_coda():
    result = parse_ipa("/ˈt͡saːnˌʔaːɐ̯t͡st/")
    assert result["syllables"] == [["t͡s", "aː", "n"], ["ʔ", "aː", "ɐ̯", "t͡s", "t"]]
    assert result["stress"] == [1, 2]


def test_explicit_word_boundaries_prevent_cross_word_resyllabification():
    result = parse_ipa("/am ˈanɡəˌɡeːbənən ˈɔʁt/")
    assert result["word_boundaries"] == [0, 1, 6, 7]
    assert result["syllables"][0] == ["a", "m"]
    assert result["syllables"][-1] == ["ɔ", "ʁ", "t"]
    assert result["stress"] == [0, 1, 0, 2, 0, 0, 1]


def test_explicit_syllable_separator_keeps_hiatus():
    result = parse_ipa("/a.i/")
    assert result["syllable_count"] == 2
    assert result["families"] == ["a", "i"]
    assert parse_ipa("/aɪ̯/")["syllable_count"] == 1


def test_patient_glide_and_affricate_belong_to_following_onset():
    result = parse_ipa("/paˈt͡si̯ɛnt/")
    assert result["syllables"] == [["p", "a"], ["t͡s", "i̯", "ɛ", "n", "t"]]
    assert result["stress"] == [0, 1]


def test_variants_keep_both_native_and_borrowed_pronunciations():
    field = "/ˈbɛksteɪd͡ʒ/, /ˈbɛksteːt͡ʃ/"
    variants = split_ipa_variants(field)
    assert variants == ["/ˈbɛksteɪd͡ʒ/", "/ˈbɛksteːt͡ʃ/"]
    assert len({parse_ipa(ipa)["signature"] for ipa in variants}) == 2
    assert split_ipa_variants("[haʊs], [haʊs]") == ["[haʊs]"]
    assert split_ipa_variants("haʊs, haʊz") == ["haʊs", "haʊz"]


def test_unknowns_are_retained_and_reported_not_silently_deleted():
    result = parse_ipa("/a☃t/")
    assert result["unknown"] == ["☃"]
    assert "☃" in result["syllables"][0]
    assert result["raw_ipa"] == "/a☃t/"


def test_phrase_punctuation_is_boundary_not_an_unknown_phone():
    result = parse_ipa("/ˈhaːzə, ˈkaːtə/")
    assert result["unknown"] == []
    assert result["word_boundaries"] == [0, 2, 4]
    assert any("Quellinterpunktion" in note for note in result["notes"])


def test_less_common_valid_palatal_and_tied_consonants():
    result = parse_ipa("/t͡ɕaʑa/")
    assert result["unknown"] == []
    assert result["syllable_count"] == 2
    assert result["syllables"][0][0] == "t͡ɕ"


def test_nucleusless_source_is_not_given_an_invented_vowel():
    result = parse_ipa("/pst/")
    assert result["nuclei"] == [""]
    assert result["first_family"] == ""
    assert any("keinen erkannten Silbenkern" in note for note in result["notes"])


def test_linking_mark_does_not_create_a_break():
    continuous = parse_ipa("/a‿ta/")
    separate = parse_ipa("/a ta/")
    assert continuous["word_boundaries"] == [0, 2]
    assert separate["word_boundaries"] == [0, 1, 2]
    assert continuous["unknown"] == []
    assert any("ohne künstliche Trennung" in note for note in continuous["notes"])


def test_missing_stress_is_not_guessed():
    result = parse_ipa("/haːzə/")
    assert result["stress"] == [0, 0]
    assert any("keinen Wortakzent" in note for note in result["notes"])


def test_normalization_preserves_source_and_explains_its_changes():
    original = " /ɡɑɪ̯ɫ/ "
    result = parse_ipa(original, "en_US")
    assert result["raw_ipa"] == original
    assert result["syllables"] == [["g", "aɪ", "l"]]
    assert result["notes"]
    assert result["unknown"] == []


def test_cached_results_are_independent_mutable_results():
    first = parse_ipa("/haʊ̯s/")
    first["syllables"][0].append("corruption")
    first["notes"].append("corruption")
    second = parse_ipa("/haʊ̯s/")
    assert "corruption" not in second["syllables"][0]
    assert "corruption" not in second["notes"]


@pytest.mark.parametrize("symbol,family", [("æ", "a"), ("ɝ", "schwa"), ("ɐ̯", ""), ("n̩", "schwa"), ("ɛ̃ː", "e"), ("t͡ʃ", "")])
def test_public_nucleus_family(symbol, family):
    assert nucleus_family(symbol) == family
