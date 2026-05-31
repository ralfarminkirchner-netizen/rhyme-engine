from app.services.rhyme_highlighter import highlight_rhyme_syllables


SAMPLE = """wach lieg im Bett
Wackelndes Brett, Wachstum verlässt. Aktienregress, Plastikbesteck, Schattengewächs, straff wie ein Netz, schattungsgesetz.
schattenkabinett
absichtlich erschreckt, lass die finger weg, abwasch lass ich jetzt, machen wir es jetzt, mathe aber schlecht, wackeliges brett, plastik im besteck, Nachtschattengewächs, passt einfach perfekt"""


def _groups_for_text(analysis, text):
    return {
        segment.rhyme_group
        for line in analysis.lines
        for segment in line.segments
        if segment.text.lower() == text.lower() and segment.rhyme_group
    }


def test_highlighter_groups_four_syllable_ett_slants_by_color():
    analysis = highlight_rhyme_syllables(SAMPLE, context_radius=8)

    bett_group = next(iter(_groups_for_text(analysis, "Bett")))
    for syllable in ["Brett", "lässt", "ress", "teck", "wächs", "Netz", "setz"]:
        assert bett_group in _groups_for_text(analysis, syllable)


def test_highlighter_groups_five_syllable_end_rhyme_family_by_color():
    analysis = highlight_rhyme_syllables(SAMPLE, context_radius=8)

    nett_group = next(iter(_groups_for_text(analysis, "nett")))
    for syllable in ["reckt", "weg", "jetzt", "schlecht", "brett", "teck", "fekt"]:
        assert nett_group in _groups_for_text(analysis, syllable)


def test_highlight_endpoint_exposes_colored_syllables():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=True)
    response = client.post("/api/rhymes/highlight-rhymes", json={"text": SAMPLE, "context_radius": 8})

    assert response.status_code == 200
    data = response.json()
    assert data["colored_syllable_count"] > 20
    assert data["rhyme_groups"]
    assert any(
        segment.get("text") == "Bett" and segment.get("color")
        for line in data["lines"]
        for segment in line["segments"]
    )


def test_highlighter_does_not_color_every_function_word_in_full_text():
    from pathlib import Path

    text = Path("app/data/training/raki_dich_lyric.txt").read_text("utf-8")
    analysis = highlight_rhyme_syllables(text, context_radius=6)

    assert analysis.colored_syllable_count < analysis.accented_syllable_count * 0.25
    low_value_hits = [
        segment.word.lower()
        for line in analysis.lines
        for segment in line.segments
        if segment.rhyme_group and segment.word and segment.word.lower() in {"der", "die", "das", "im", "und", "wer"}
    ]
    assert low_value_hits == []
