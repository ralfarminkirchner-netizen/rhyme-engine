from pathlib import Path

from app.services.rap_text_analyzer import (
    analyze_rap_text,
    extract_lyric_lines,
    extract_lyric_sections,
)


FIXTURE = Path("app/data/training/raki_dich_lyric.txt")


def load_text() -> str:
    return FIXTURE.read_text("utf-8")


def line_with(analysis, needle: str):
    for line in analysis.lines:
        if needle in line.text:
            return line
    raise AssertionError(f"line not found: {needle!r}")


def test_extracts_only_lyric_lines_from_raki_training_text():
    lines = extract_lyric_lines(load_text())

    assert len(lines) == 72
    assert lines[0].startswith("Leib-Seele-Probleme")
    assert not any(line.startswith("Hook") or line.startswith("Part") for line in lines)


def test_extracts_section_map_with_stable_line_ranges():
    sections = extract_lyric_sections(load_text())

    assert [section.name for section in sections] == [
        "Hook 1",
        "Part 1",
        "Hook 2",
        "Part 2",
        "Hook 3",
        "Hook 3 – WDH Variante",
    ]
    assert [(section.start_line, section.end_line) for section in sections] == [
        (1, 8),
        (9, 29),
        (30, 37),
        (38, 56),
        (57, 64),
        (65, 72),
    ]


def test_hook_opening_carries_multiple_visible_techniques():
    analysis = analyze_rap_text(load_text())
    opening = line_with(analysis, "wie das Leben leicht nehmen")

    assert "diphthong_anchor_chain" in opening.window_tags
    assert "front_vowel_band" in opening.window_tags
    assert "tight_consonant_grip" in opening.window_tags
    assert opening.anchor_nuclei.count("aɪ") >= 2


def test_grenzen_line_exposes_internal_rhyme_chain():
    analysis = analyze_rap_text(load_text())
    line = line_with(analysis, "Grenzen weder sehen noch setzen")

    words = {word.lower() for chain in line.internal_rhyme_chains for word in chain.words}
    assert {"sehen", "setzen", "übergehen", "verletzen"} <= words


def test_affekt_block_forms_terminal_rhyme_chain():
    analysis = analyze_rap_text(load_text())

    matching = [
        chain for chain in analysis.terminal_rhyme_chains
        if {"perfekt", "Affekt", "überdeckt"} <= set(chain.words)
    ]

    assert matching, [
        {"words": chain.words, "lines": chain.line_indices, "floor": chain.similarity_floor}
        for chain in analysis.terminal_rhyme_chains
    ]


def test_entdeckst_affekt_is_internal_terminal_slant():
    analysis = analyze_rap_text(load_text())
    line = line_with(analysis, "entdeckst, wirst du dein Vater im Affekt")

    words = {word.lower() for chain in line.internal_rhyme_chains for word in chain.words}
    assert {"entdeckst", "affekt"} <= words


def test_recognises_refrain_variants_across_hooks():
    analysis = analyze_rap_text(load_text())
    groups = {group.key: group for group in analysis.refrain_groups}

    assert groups["leib seele probleme"].line_indices == [1, 30, 57, 65]
    assert groups["im licht der"].line_indices == [5, 34, 61, 69]


def test_motif_repetition_tracks_hidden_structural_words():
    analysis = analyze_rap_text(load_text())

    assert analysis.motif_counts["leben"] >= 4
    assert analysis.motif_counts["seele"] >= 4
    assert analysis.motif_counts["wahrheit"] >= 3
    assert analysis.motif_counts["körper"] >= 3


def test_detects_all_named_hermeneutic_spirals():
    analysis = analyze_rap_text(load_text())
    structures = {structure.key: structure for structure in analysis.deep_structures}

    assert set(structures) >= {
        "embodiment_wound",
        "shadow_integration",
        "conditioning_will_karma",
        "stillness_insight",
        "witness_critic",
        "nondual_simplicity",
    }
    assert any("Traumata" in analysis.lines[i - 1].text for i in structures["embodiment_wound"].line_indices)
    assert any("Integriere Schattenseiten" in analysis.lines[i - 1].text for i in structures["shadow_integration"].line_indices)
    assert any("Karma" in analysis.lines[i - 1].text for i in structures["conditioning_will_karma"].line_indices)
    assert any("Stille" in analysis.lines[i - 1].text for i in structures["stillness_insight"].line_indices)
    assert any("inneren Zeugen" in analysis.lines[i - 1].text for i in structures["witness_critic"].line_indices)
    assert any("Jetzt und Hier" in analysis.lines[i - 1].text for i in structures["nondual_simplicity"].line_indices)


def test_refrain_evolution_maps_problem_to_identity():
    analysis = analyze_rap_text(load_text())
    evolutions = {evolution.key: evolution for evolution in analysis.refrain_evolutions}
    stages = evolutions["leib seele probleme"].stages

    assert [stage.role for stage in stages] == [
        "problem_as_wound",
        "life_confrontation",
        "nondual_identity",
        "nondual_identity",
    ]


def test_question_arc_moves_from_agency_to_nondual_mirror():
    analysis = analyze_rap_text(load_text())
    keys = [move.key for move in analysis.question_arc]

    assert "agency" in keys
    assert "value_origin" in keys
    assert "conditioned_self" in keys
    assert "body_soul_polarity" in keys
    assert keys[-1] == "nondual_mirror"


def test_technique_inventory_reports_song_level_density():
    analysis = analyze_rap_text(load_text())
    inventory = analysis.technique_inventory

    assert inventory.window_tag_counts["front_vowel_band"] >= 40
    assert inventory.window_tag_counts["tight_consonant_grip"] >= 40
    assert inventory.internal_chain_count >= 100
    assert inventory.terminal_chain_count >= 40
    assert inventory.refrain_group_count >= 6
    assert inventory.rhetorical_device_count >= 10
    assert inventory.echo_pattern_count >= 10


def test_rhetorical_devices_capture_hidden_non_phonetic_techniques():
    analysis = analyze_rap_text(load_text())
    devices = analysis.rhetorical_devices
    kinds = {device.kind for device in devices}

    assert "anaphoric_refrain" in kinds
    assert "body_soul_chiasmus" in kinds
    assert "truth_lie_antithesis" in kinds
    assert "mirror_koan" in kinds
    assert "process_parallelism" in kinds
    assert "self_reflexive_repetition" in kinds
    assert "dream_frame_turn" in kinds

    chiasmus_lines = [
        device.evidence[0] for device in devices
        if device.kind == "body_soul_chiasmus"
    ]
    assert any("Körper mit Seele oder Seele mit Körper" in line for line in chiasmus_lines)
    assert any("Seele im Körper oder Körper in einer Seele" in line for line in chiasmus_lines)


def test_echo_patterns_find_derivational_wordplay():
    analysis = analyze_rap_text(load_text())
    echoes = {
        (echo.line_index, echo.stem): {word.lower() for word in echo.words}
        for echo in analysis.echo_patterns
    }

    assert {"beenden", "enden"} <= echoes[(27, "enden")]
    assert {"muster"} <= {word.lower() for echo in analysis.echo_patterns for word in echo.words}
    assert any(
        {"traumleben", "traum"} <= {word.lower() for word in echo.words}
        for echo in analysis.echo_patterns
    )


def test_structural_arc_is_complete_and_ordered():
    analysis = analyze_rap_text(load_text())
    arc = analysis.structural_arcs[0]

    assert arc.key == "trauma_to_nonduality_spiral"
    assert arc.complete
    assert arc.ordered
    assert [stage.key for stage in arc.stages] == [
        "survival_and_wound",
        "conditioning_and_repetition",
        "integration_and_confrontation",
        "stillness_and_witness",
        "nondual_resolution",
    ]
    assert arc.stages[0].line_indices[0] < arc.stages[-1].line_indices[0]


def test_bypassing_audit_proves_body_and_shadow_before_nondual_resolution():
    analysis = analyze_rap_text(load_text())
    audit = analysis.bypassing_audit

    assert audit.trauma_before_nondual
    assert audit.integration_before_nondual
    assert audit.first_trauma_line == 2
    assert audit.first_integration_line == 18
    assert audit.first_specific_nondual_line == 57


def test_completion_audit_marks_all_required_hidden_structures_as_covered():
    analysis = analyze_rap_text(load_text())
    audit = analysis.completion_audit
    items = {item.key: item for item in audit.items}

    assert audit.complete
    assert audit.covered_count == audit.total_count
    assert audit.missing_keys == []
    assert set(items) >= {
        "lyric_sections",
        "diphthong_anchor_chain",
        "front_vowel_band",
        "tight_consonant_grip",
        "internal_rhyme_density",
        "terminal_rhyme_density",
        "refrain_transformation",
        "integrated_registers",
        "embodied_layer_fusion",
        "conditioned_action_without_blame",
        "embodiment_wound",
        "shadow_integration",
        "conditioning_will_karma",
        "stillness_insight",
        "witness_critic",
        "nondual_simplicity",
        "question_arc",
        "body_soul_chiasmus",
        "mirror_koan",
        "truth_lie_antithesis",
        "morphological_echoes",
        "ordered_spiral",
        "anti_bypassing",
    }
    assert items["anti_bypassing"].covered
    assert items["ordered_spiral"].covered
    assert items["morphological_echoes"].covered
    assert items["refrain_transformation"].covered
    assert items["integrated_registers"].covered
    assert items["embodied_layer_fusion"].covered
    assert items["conditioned_action_without_blame"].covered


def test_analyze_text_api_exposes_deep_structure_output():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=True)
    response = client.post("/api/rhymes/analyze-text", json={"text": load_text()})

    assert response.status_code == 200
    data = response.json()
    assert len(data["lines"]) == 72
    assert {s["key"] for s in data["deep_structures"]} >= {
        "embodiment_wound",
        "shadow_integration",
        "nondual_simplicity",
    }
    assert data["refrain_evolutions"][0]["stages"][0]["role"] == "problem_as_wound"
    assert {d["kind"] for d in data["rhetorical_devices"]} >= {
        "body_soul_chiasmus",
        "mirror_koan",
        "truth_lie_antithesis",
    }
    assert data["structural_arcs"][0]["complete"] is True
    assert data["bypassing_audit"]["trauma_before_nondual"] is True
    assert data["completion_audit"]["complete"] is True
    assert data["completion_audit"]["missing_keys"] == []
