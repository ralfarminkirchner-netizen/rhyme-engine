"""
Tests fuer die graduelle artikulatorische Distanz (Holtman-Prinzipien).

Reim-Aehnlichkeit ist graduell, nicht binaer:
- Konsonanten gleicher Artikulationsstelle (nur Stimmhaftigkeit verschieden) ~ nah.
- Vokale, die sich nur in Spannung/Laenge (ATR) oder leicht in der Hoehe
  unterscheiden, sind hochkompatibel.
- Nasale reimen ueber Artikulationsorte hinweg (-amm/-ann/-ing).
"""
from app.services.phonological_distance import phoneme_similarity as sim


def test_identity_is_one():
    assert sim("a", "a") == 1.0
    assert sim("t", "t") == 1.0


def test_voicing_pairs_same_place_are_close():
    # gleicher Ort, nur Stimmhaftigkeit -> hoch
    for a, b in [("p", "b"), ("t", "d"), ("k", "g"), ("f", "v"), ("s", "z"), ("ʃ", "ʒ")]:
        assert sim(a, b) >= 0.80, f"{a}/{b} sollte nah sein: {sim(a,b):.2f}"


def test_atr_length_vowel_pairs_are_highly_compatible():
    # gespannt/ungespannt (ATR) ueber Laenge -> sehr hoch
    for a, b in [("iː", "ɪ"), ("eː", "ɛ"), ("uː", "ʊ"), ("oː", "ɔ"), ("yː", "ʏ"), ("aː", "a")]:
        assert sim(a, b) >= 0.90, f"{a}/{b} ATR sollte hochkompatibel sein: {sim(a,b):.2f}"


def test_nasals_rhyme_across_place():
    # Holtman: Nasale minimal-distant; im Rap reimen -amm/-ann, -ing/-inn.
    for a, b in [("m", "n"), ("n", "ŋ"), ("m", "ŋ")]:
        s = sim(a, b)
        assert 0.70 <= s < 1.0, f"{a}/{b} sollte nah, aber nicht identisch sein: {s:.2f}"


def test_nasals_closer_than_different_place_plosives():
    # gleicher Manner (nasal) naeher als verschiedener Ort bei Plosiven
    assert sim("m", "n") > sim("t", "k")
    assert sim("n", "ŋ") > sim("p", "t")


def test_coronal_fricatives_are_close():
    assert sim("s", "ʃ") >= 0.80


def test_far_vowels_lower_than_near_vowels():
    # front/back-Distanz schlaegt durch
    assert sim("iː", "ɪ") > sim("iː", "uː")
    assert sim("ɛ", "eː") > sim("ɛ", "ɔ")


def test_unknown_phoneme_is_zero():
    assert sim("a", "QQQ") == 0.0
