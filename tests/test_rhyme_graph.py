"""Behavioral checks for provenance, exact rhyme claims and bounded flex."""
import pytest
from pydantic import ValidationError

from app.schemas.rhyme_graph import GraphBuildRequest, PronunciationOverride
from app.services.rhyme_graph import MAX_COMPARISONS, build_rhyme_graph


def correction(line, word, syllables, stress, word_text=None):
    return PronunciationOverride(
        line_index=line, word_index=word, word_text=word_text,
        syllables=syllables, stress=stress,
    )


def pair(graph, left, right):
    return next(edge for edge in graph.edges if {edge.source, edge.target} == {left, right})


def test_exact_multisyllabic_phrase_crosses_word_boundaries_and_keeps_sources():
    text = "Sehen wir Licht\nGehen wir Licht"
    graph = build_rhyme_graph(GraphBuildRequest(text=text, mode="strict"), {
        1: {"document_id": "test-document", "line": 9, "version": "original"},
    })
    edge = pair(graph, "l0-s0-4", "l1-s0-4")
    assert edge.kind == "clean"
    assert edge.score == pytest.approx(1)
    assert edge.status == "proposed"
    assert all(row.left_index == row.right_index for row in edge.alignment)
    node = next(node for node in graph.nodes if node.id == "l1-s0-4")
    assert node.text == text[node.char_start:node.char_end] == "Gehen wir Licht"
    assert node.start_word == 0 and node.end_word == 3
    assert node.source["document_id"] == "test-document"


def test_same_vowels_with_changed_inner_onsets_are_never_clean():
    overrides = [
        correction(0, 0, [["m", "a"], ["n", "ə"], ["l", "aɪ", "n"]], [1, 0, 1]),
        correction(1, 0, [["b", "a"], ["t", "ə"], ["l", "aɪ", "n"]], [1, 0, 1]),
    ]
    strict = build_rhyme_graph(GraphBuildRequest(
        text="Alpha\nBeta", mode="strict", overrides=overrides,
        min_syllables=3, max_syllables=3,
    ))
    assert strict.edges == []
    balanced = build_rhyme_graph(GraphBuildRequest(
        text="Alpha\nBeta", overrides=overrides, min_syllables=3, max_syllables=3,
    ))
    assert balanced.edges and balanced.edges[0].kind == "slant"
    assert balanced.edges[0].profile.vowels == 1
    assert balanced.edges[0].profile.consonants < 1
    assert any("Konsonanten" in message for message in balanced.edges[0].deviations)


def test_extra_syllable_has_explicit_gap_and_is_not_relabelled_clean():
    overrides = [
        correction(0, 0, [["m", "a"], ["n", "ə"], ["l", "aɪ", "n"]], [1, 0, 1]),
        correction(1, 0, [["b", "a"], ["n", "ə"], ["t", "ə"], ["l", "aɪ", "n"]], [1, 0, 0, 1]),
    ]
    graph = build_rhyme_graph(GraphBuildRequest(
        text="Alpha\nBeta", overrides=overrides, min_syllables=3, max_syllables=4,
        max_syllable_delta=1,
    ))
    edge = pair(graph, "l0-s0-3", "l1-s0-4")
    assert edge.kind == "flex"
    assert sum(row.left_index is None or row.right_index is None for row in edge.alignment) == 1
    assert [row.left_index for row in edge.alignment if row.left_index is not None] == [0, 1, 2]
    assert [row.right_index for row in edge.alignment if row.right_index is not None] == [0, 1, 2, 3]
    assert edge.alignment[-1].left_index == 2 and edge.alignment[-1].right_index == 3
    assert any("ungepaart" in message for message in edge.deviations)
    assert any("keine fehlenden Laute" in message for message in graph.warnings)
    no_gaps = build_rhyme_graph(GraphBuildRequest(
        text="Alpha\nBeta", overrides=overrides, min_syllables=3, max_syllables=4,
        max_syllable_delta=0,
    ))
    assert all(edge.kind != "flex" for edge in no_gaps.edges)


def test_manual_pronunciation_changes_analysis_but_not_original_and_checks_stale_word():
    text = "\nGeh’ – nach Haus!\r\nSehen wir Licht"
    override = correction(1, 0, [["g", "eː"]], [1], "Geh’")
    # Apostrophe must have a following letter to remain part of a token.
    with pytest.raises(ValueError, match="word_text"):
        build_rhyme_graph(GraphBuildRequest(text=text, overrides=[override]))
    override.word_text = "Geh"
    graph = build_rhyme_graph(GraphBuildRequest(text=text, overrides=[override]))
    assert graph.text == text
    assert graph.lines[0].text == ""
    word = graph.lines[1].words[0]
    assert word.origin == "manual" and word.phonetic_syllables == [["g", "eː"]]
    assert text[word.char_start:word.char_end] == "Geh"
    assert text[graph.lines[2].char_start:graph.lines[2].char_end] == "Sehen wir Licht"
    assert graph.lines[1].phonetic_syllables[0] == ["g", "eː"]


def test_nonoverlapping_internal_phrase_links_to_terminal_phrase():
    graph = build_rhyme_graph(GraphBuildRequest(
        text="Sehen wir Licht und gehen wir Licht", mode="strict",
        min_syllables=4, max_syllables=4,
    ))
    nodes = {node.id: node for node in graph.nodes}
    assert any(
        {nodes[edge.source].kind, nodes[edge.target].kind} == {"terminal", "internal"}
        for edge in graph.edges
    )
    for edge in graph.edges:
        left, right = nodes[edge.source], nodes[edge.target]
        assert left.end_syllable <= right.start_syllable or right.end_syllable <= left.start_syllable


def test_transitive_membership_is_not_used_as_a_rhyme_claim():
    # Two endpoints share the same terminal anchor but only one identical phrase.
    overrides = [
        correction(0, 0, [["m", "a"], ["n", "ə"], ["l", "aɪ", "n"]], [1, 0, 1]),
        correction(1, 0, [["b", "a"], ["n", "ə"], ["l", "aɪ", "n"]], [1, 0, 1]),
        correction(2, 0, [["b", "ʊ"], ["k", "ɪ"], ["l", "aɪ", "n"]], [1, 0, 1]),
    ]
    graph = build_rhyme_graph(GraphBuildRequest(
        text="Alpha\nBeta\nGamma", mode="strict", overrides=overrides,
        min_syllables=3, max_syllables=3,
    ))
    assert len(graph.edges) == 1
    assert {graph.edges[0].source, graph.edges[0].target} == {"l0-s0-3", "l1-s0-3"}


@pytest.mark.parametrize("kwargs", [
    {"syllables": [["a"]], "stress": [1, 0]},
    {"syllables": [[]], "stress": [1]},
    {"syllables": [["a", "ɛ"]], "stress": [1]},
    {"syllables": [["a", "ɐ", "ɛ"]], "stress": [1]},
    {"syllables": [["a", "ɐ", "ɐ"]], "stress": [1]},
    {"syllables": [["unknown"]], "stress": [1]},
    {"syllables": [["a"]], "stress": [2]},
])
def test_invalid_manual_pronunciations_are_rejected(kwargs):
    with pytest.raises(ValidationError):
        PronunciationOverride(line_index=0, word_index=0, **kwargs)


def test_request_limits_and_override_references_are_validated():
    for text in ("   ", "\n!!!\n", "123456", "a" * 161, "\n" * 64 + "Licht"):
        with pytest.raises(ValidationError):
            GraphBuildRequest(text=text)
    with pytest.raises(ValidationError):
        GraphBuildRequest(text="Licht", min_syllables=5, max_syllables=3)
    with pytest.raises(ValidationError):
        GraphBuildRequest(text="Licht", max_nodes=161)
    with pytest.raises(ValidationError):
        GraphBuildRequest(text="Licht", max_edges=301)
    item = correction(0, 0, [["l", "ɪ", "ç", "t"]], [1])
    with pytest.raises(ValidationError):
        GraphBuildRequest(text="Licht", overrides=[item, item])
    with pytest.raises(ValueError, match="fehlende Stelle"):
        build_rhyme_graph(GraphBuildRequest(text="\nLicht", overrides=[item]))


def test_caps_are_reported_and_graph_is_deterministic():
    request = GraphBuildRequest(
        text="\n".join(["Sehen wir Licht und gehen wir Licht"] * 14),
        max_nodes=36, max_edges=5,
    )
    graph = build_rhyme_graph(request)
    assert len(graph.nodes) == 36 and len(graph.edges) == 5
    assert graph.truncated
    assert any("Segmentlimit" in warning for warning in graph.warnings)
    assert any("Kantenlimit" in warning for warning in graph.warnings)
    assert build_rhyme_graph(request).model_dump() == graph.model_dump()
    assert MAX_COMPARISONS < 160 * 159 // 2


def test_empty_and_short_lines_remain_traceable():
    graph = build_rhyme_graph(GraphBuildRequest(text="\n!!!\nLicht\n"))
    assert len(graph.lines) == 4
    assert graph.nodes == [] and graph.edges == []
    assert any("Keine Segmente" in warning for warning in graph.warnings)


@pytest.mark.parametrize("extra", [1, 2])
@pytest.mark.parametrize("reverse", [False, True])
def test_unstressed_end_overhang_is_explicit_symmetric_and_keeps_actual_terminal(extra, reverse):
    short = [["m", "a"], ["n", "ə"], ["l", "aɪ", "n"]]
    long = [["b", "a"], ["n", "ə"], ["l", "aɪ", "n"]] + [["ə"]] * extra
    variants = [(short, [1, 0, 1]), (long, [1, 0, 1] + [0] * extra)]
    if reverse:
        variants.reverse()
    overrides = [correction(index, 0, syllables, stress) for index, (syllables, stress) in enumerate(variants)]
    request = GraphBuildRequest(
        text="Alpha\nBeta", overrides=overrides, min_syllables=3, max_syllables=3 + extra,
        max_syllable_delta=extra,
    )
    graph = build_rhyme_graph(request)
    left_length, right_length = len(variants[0][0]), len(variants[1][0])
    edge = pair(graph, f"l0-s0-{left_length}", f"l1-s0-{right_length}")
    assert edge.kind == "flex"
    assert edge.profile.terminal < 0.5
    assert edge.profile.coverage == pytest.approx(3 / (3 + extra))
    assert edge.score == pytest.approx(0.84 if extra == 1 else 0.72)
    assert sum(row.left_index is None or row.right_index is None for row in edge.alignment) == extra
    assert edge.alignment[-1].left_index is None if not reverse else edge.alignment[-1].right_index is None
    assert any("Endüberhang" in deviation for deviation in edge.deviations)
    assert any("Tatsächlicher Terminalvergleich" in deviation for deviation in edge.deviations)
    assert any("nicht bestätigt" in operation for operation in edge.required_operations)
    strict = build_rhyme_graph(request.model_copy(update={"mode": "strict"}))
    assert not any({item.source, item.target} == {edge.source, edge.target} for item in strict.edges)


def test_stressed_tail_is_not_discarded_as_an_overhang():
    overrides = [
        correction(0, 0, [["m", "a"], ["n", "ə"], ["l", "aɪ", "n"]], [1, 0, 1]),
        correction(1, 0, [["b", "a"], ["n", "ə"], ["l", "aɪ", "n"], ["ə"]], [1, 0, 1, 1]),
    ]
    graph = build_rhyme_graph(GraphBuildRequest(
        text="Alpha\nBeta", overrides=overrides, min_syllables=3, max_syllables=4,
    ))
    assert not any({edge.source, edge.target} == {"l0-s0-3", "l1-s0-4"} for edge in graph.edges)


@pytest.mark.parametrize("word,count", [
    ("Garten", 2), ("wandern", 2), ("andern", 2), ("stark", 1),
    ("wir", 1), ("hier", 1), ("Bier", 1), ("Tier", 1), ("später", 2),
    ("Feuer", 2), ("Bauer", 2), ("Leier", 2), ("Geier", 2),
])
def test_graph_groups_r_offglides_but_preserves_genuine_er_nuclei(word, count):
    graph = build_rhyme_graph(GraphBuildRequest(text=word))
    parsed = graph.lines[0].words[0]
    assert len(parsed.phonetic_syllables) == count
    # The graph's automatically grouped IPA can be used unchanged as a manual override.
    override = correction(0, 0, parsed.phonetic_syllables, parsed.stress, word)
    corrected = build_rhyme_graph(GraphBuildRequest(text=word, overrides=[override]))
    assert corrected.lines[0].words[0].phonetic_syllables == parsed.phonetic_syllables


def test_manual_separate_r_vowels_are_not_silently_merged():
    override = correction(0, 0, [["v", "ɪ"], ["ɐ"]], [1, 0], "wir")
    graph = build_rhyme_graph(GraphBuildRequest(text="wir", overrides=[override]))
    assert graph.lines[0].words[0].phonetic_syllables == [["v", "ɪ"], ["ɐ"]]


def test_loanword_glide_cluster_remains_in_following_onset():
    graph = build_rhyme_graph(GraphBuildRequest(text="Patient"))
    word = graph.lines[0].words[0]
    assert word.phonetic_syllables == [["p", "a"], ["t͡s", "j", "ɛ", "n", "t"]]
    assert word.stress == [0, 1]
    assert word.analysis_notes
