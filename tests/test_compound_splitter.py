"""Tests fuer die deutsche Komposita-Zerlegung (compound_splitter)."""
import pytest

from app.services import compound_splitter as cs

# Wenn split-words nicht installiert ist, pruefen wir nur den harten Fallback.
HAS_MODEL = cs.is_available()
requires_model = pytest.mark.skipif(not HAS_MODEL, reason="split-words/CharSplit nicht installiert")


def test_fallback_never_raises_and_returns_word():
    # Egal ob Modell da ist: ein Simplex/leeres Wort bleibt heil.
    assert cs.split_compound("") == [""]
    assert cs.split_compound("haus")[-1] == "haus"


@requires_model
def test_real_compound_is_split_with_last_component_stress_bearer():
    parts = cs.split_compound("schattenkabinett")
    assert parts == ["schatten", "kabinett"]
    # Grundwort = Hauptakzent-Traeger
    assert cs.last_component("schattenkabinett") == "kabinett"
    assert cs.head_components("schattenkabinett") == ["schatten"]


@requires_model
def test_multipart_compound_splits_recursively():
    parts = cs.split_compound("haltbarkeitsdatum")
    assert parts[-1] == "datum"
    assert len(parts) >= 2


@requires_model
def test_non_compound_is_left_whole():
    # "beziehung" ist KEIN Kompositum -> negativer Score -> nicht splitten.
    assert cs.split_compound("beziehung") == ["beziehung"]


@requires_model
def test_components_preserve_original_and_reconstruct_word():
    word = "autobahnraststätte"
    parts = cs.split_compound(word)
    assert "".join(parts) == word                       # luekenlos, keine Zeichen verloren
    assert len(parts) >= 2                              # wurde zerlegt
    assert all(len(p) >= cs.MIN_PART_LEN for p in parts)  # keine Mini-Fragmente
    assert "raststätte" in parts or "stätte" in parts   # Grundwort-Region erfasst


@requires_model
def test_low_confidence_falsesplit_is_suppressed():
    # "plastikbesteck" wird vom Modell falsch (Plastikbe|Steck, Score<0) -> Gate
    # verhindert den Fehlsplit, Wort bleibt ganz.
    assert cs.split_compound("plastikbesteck") == ["plastikbesteck"]
