"""General phonetic repairs; no private verse or rhyme-chain fixture."""
import pytest

from app.services.graph_pronunciation import pronounce_graph_word
from app.services.parser import graphemes_to_phonemes, syllabify
from app.services.phonological_distance import FEATURES


@pytest.mark.parametrize("word,expected", [
    ("Computer", "k"), ("Café", "k"), ("Celsius", "t͡s"), ("Circa", "t͡s"),
])
def test_standalone_c_is_a_known_phone(word, expected):
    phones, _, notes = pronounce_graph_word(word)
    assert phones[0] == expected
    assert "c" not in phones
    assert all(phone in FEATURES for phone in phones)
    assert notes


@pytest.mark.parametrize("word", ["Bach", "backen", "Schach", "Christ"])
def test_ch_and_ck_are_not_reinterpreted_as_standalone_c(word):
    phones, _, _ = pronounce_graph_word(word)
    original = graphemes_to_phonemes(word)
    assert phones == original


@pytest.mark.parametrize("word,count", [("Patient", 2), ("Patienten", 3), ("effizient", 3), ("Effizienz", 3)])
def test_romance_ient_ienz_keep_the_open_e_nucleus(word, count):
    phones, stress, notes = pronounce_graph_word(word)
    assert ["t͡s", "j", "ɛ"] in [phones[i:i + 3] for i in range(len(phones) - 2)]
    assert len(syllabify(phones)) == count
    assert sum(stress) == 1
    assert stress[1] == 1 if word.lower().startswith("patient") else stress[-1] == 1
    assert any("Lehnwortfolge" in note for note in notes)


def test_lexically_distinct_hiatus_is_preserved():
    phones, stress, _ = pronounce_graph_word("Klient")
    assert len(syllabify(phones)) == 2
    assert stress == [0, 1]
    assert "j" not in phones
    phones, stress, _ = pronounce_graph_word("Orient")
    assert len(syllabify(phones)) == 3
    assert stress == [1, 0, 0]


@pytest.mark.parametrize("word", ["dient", "diente", "bedient", "verdienten"])
def test_german_dien_inflections_do_not_become_romance_ient(word):
    phones, _, _ = pronounce_graph_word(word)
    assert "iː" in phones
    assert "j" not in phones
    assert not any(phones[i:i + 2] == ["j", "ɛ"] for i in range(len(phones) - 1))


@pytest.mark.parametrize("word", ["Frage", "Tage", "Klage", "Sage"])
def test_final_schwa_does_not_receive_legacy_french_age_stress(word):
    phones, stress, _ = pronounce_graph_word(word)
    assert stress == [1, 0]
    assert "aː" in phones
    assert phones[-1] == "ə"


@pytest.mark.parametrize("word", ["badet", "redet", "wartet", "arbeitet"])
def test_reduced_et_inflection_has_unstressed_schwa(word):
    phones, stress, _ = pronounce_graph_word(word)
    assert phones[-2:] == ["ə", "t"]
    assert stress[-1] == 0


@pytest.mark.parametrize("word", ["Paket", "Filet"])
def test_unrelated_loan_et_is_not_reduced_as_verb_inflection(word):
    phones, _, _ = pronounce_graph_word(word)
    assert phones[-2:] != ["ə", "t"]


@pytest.mark.parametrize("word", ["baden", "Hase", "Rabe"])
def test_open_stressed_native_syllable_has_long_vowel(word):
    phones, _, _ = pronounce_graph_word(word)
    assert "aː" in phones


@pytest.mark.parametrize("word", ["Tasse", "Kante", "Kasten"])
def test_closed_syllable_is_not_lengthened(word):
    phones, _, _ = pronounce_graph_word(word)
    assert "aː" not in phones


def test_service_does_not_mutate_legacy_parser():
    before = graphemes_to_phonemes("Patient")
    pronounce_graph_word("Patient")
    assert graphemes_to_phonemes("Patient") == before


def test_final_acute_full_vowel_keeps_its_stress():
    phones, stress, _ = pronounce_graph_word("Café")
    assert phones == ["k", "a", "f", "eː"]
    assert stress == [0, 1]
