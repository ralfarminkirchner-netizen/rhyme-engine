"""Rap-rhyme behavior using invented, explicitly pronounced four-syllable data.

These fixtures exercise a capability, not the user's private lyric examples or
an exact implementation score. The spellings deliberately carry no rhyme cue.
"""

import pytest

from app.schemas.rhyme_graph import GraphBuildRequest, PronunciationOverride
from app.services.rhyme_graph import build_rhyme_graph


def compare(left, right, *, mode="dirty", labels=("Alpha", "Beta"), stresses=None):
    patterns = stresses or ([1, 0, 0, 1], [1, 0, 0, 1])
    overrides = [
        PronunciationOverride(
            line_index=index,
            word_index=0,
            word_text=labels[index],
            syllables=syllables,
            stress=patterns[index],
        )
        for index, syllables in enumerate((left, right))
    ]
    return build_rhyme_graph(GraphBuildRequest(
        text="\n".join(labels),
        mode=mode,
        min_syllables=4,
        max_syllables=4,
        max_syllable_delta=1,
        include_internal=False,
        overrides=overrides,
    ))


@pytest.mark.parametrize("ending", [["n", "t"], ["l", "t"], ["ŋ"]])
def test_dirty_four_syllable_rhyme_survives_changing_onsets_and_supported_end_codas(ending):
    left = [["m", "a"], ["n", "ə", "n"], ["l", "ɪ", "m"], ["t", "ɛ", "n", "t"]]
    right = [["ʃ", "l", "a", "f"], ["v", "ɪ", "n"], ["d", "ə", "m"], ["k", "ɛ", *ending]]

    graph = compare(left, right)

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1, "A distributed four-syllable correspondence must not be vetoed by changing inner onsets."
    edge = graph.edges[0]
    assert edge.kind == "slant"
    assert len(edge.alignment) == 4
    assert all(row.left_index is not None and row.right_index is not None for row in edge.alignment)
    assert edge.status == "proposed"
    assert edge.deviations, "The visible analysis must retain the imperfect sound correspondence."

    # Reversing the query must not turn the same relation into an unrelated pair.
    reverse = compare(right, left)
    assert len(reverse.edges) == 1
    assert reverse.edges[0].kind == "slant"

    # A usable rap rhyme is not permission to call every sound identical.
    assert compare(left, right, mode="strict").edges == []


def test_same_terminal_rhyme_does_not_validate_three_unrelated_preceding_syllables():
    left = [["m", "a"], ["n", "ə"], ["l", "ɪ"], ["t", "ɛ", "n", "t"]]
    right = [["k", "uː"], ["f", "aʊ"], ["b", "oː"], ["ʃ", "ɛ", "n", "t"]]

    assert compare(left, right).edges == []


def test_four_vowels_without_any_consonant_grip_do_not_become_a_strong_rhyme():
    left = [["m", "a", "p"], ["n", "ə", "t"], ["l", "ɪ", "k"], ["t", "ɛ", "p"]]
    right = [["k", "a", "ʒ"], ["f", "ə", "ŋ"], ["b", "ɪ", "f"], ["ʃ", "ɛ", "ʃ"]]

    # Assonance can be discussed separately; a strong rhyme claim additionally
    # needs support from the rime/consonant structure and its end anchor.
    assert compare(left, right).edges == []


def test_similar_spelling_cannot_override_incompatible_spoken_nuclei():
    left = [["m", "a"], ["n", "ə"], ["l", "ɪ"], ["t", "ɛ", "n", "t"]]
    right = [["m", "uː"], ["n", "aʊ"], ["l", "oː"], ["t", "yː", "n", "t"]]

    assert compare(left, right, labels=("Klangbild", "Klangbilder")).edges == []


def test_deviating_guessed_stress_does_not_erase_a_distributed_four_syllable_rhyme():
    left = [["m", "a"], ["n", "ə", "n"], ["l", "ɪ", "m"], ["t", "ɛ", "l", "t"]]
    right = [["ʃ", "l", "a", "f"], ["v", "ɪ", "n"], ["d", "ə", "m"], ["k", "ɛ", "l", "t"]]

    graph = compare(left, right, stresses=([1, 0, 0, 1], [1, 1, 1, 1]))

    assert len(graph.edges) == 1
    assert graph.edges[0].kind == "slant"
    assert any(not row.stress_match for row in graph.edges[0].alignment)
    assert any("Betonung" in note for note in graph.edges[0].deviations)
