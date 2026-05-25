import pytest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.services.parser import parse_german_word

# ── Invarianten ────────────────────────────────────────────────────────────────

def test_sein_terminal():
    r = parse_german_word("sein")
    assert r.terminal_span  == ["aɪ","n"]
    assert r.terminal_tail  == ["n"]
    assert r.syllable_count == 1
    assert r.stress_pattern == [1]

def test_bewusstsein():
    r = parse_german_word("bewusstsein")
    assert r.syllable_count       == 3
    assert r.stress_pattern       == [0,1,0]
    assert r.rhyme_span[0]        == "ʊ"
    assert r.terminal_span        == ["aɪ","n"]
    assert r.vowel_spine          == ["ʊ","aɪ"]
    assert r.terminal_vowel_spine == ["aɪ"]

def test_buch_ach_laut():
    r = parse_german_word("Buch")
    assert "x" in r.phonetic
    assert "ç" not in r.phonetic

def test_ich_laut():
    r = parse_german_word("ich")
    assert "ç" in r.phonetic
    assert "x" not in r.phonetic

def test_verstehen_prefix():
    r = parse_german_word("verstehen")
    assert r.stress_pattern[0] == 0
    assert 1 in r.stress_pattern

def test_lieb_auslautverhaertung():
    r = parse_german_word("lieb")
    assert r.phonetic[-1] == "p"

def test_besser_r_vokalisierung():
    r = parse_german_word("besser")
    assert "ɐ" in r.phonetic
