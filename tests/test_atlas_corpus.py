"""Public-source reader behavior, using synthetic data rather than user text."""
import bz2
import json

import pytest

from app.services.atlas_corpus import (
    CorpusFormatError,
    iter_ipa_entries,
    iter_sentence_windows,
    iter_tatoeba_entries,
    iter_thesaurus_entries,
    load_manifest,
)


def source(tmp_path, content, name="source.tsv"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.parametrize("manifest", [
    {"sources": [{"id": "open", "license": "CC BY-SA", "author": "Contributor"}]},
    [{"id": "one", "license": {"name": "CC BY", "version": "2.0 FR"}}],
])
def test_manifest_retains_nested_license_and_attribution(tmp_path, manifest):
    path = source(tmp_path, json.dumps(manifest), "manifest.json")
    assert load_manifest(path) == manifest


def test_manifest_rejects_non_structured_value(tmp_path):
    with pytest.raises(CorpusFormatError, match="JSON object or array"):
        load_manifest(source(tmp_path, '"not a manifest"'))


def test_ipa_keeps_each_variant_spelling_and_provenance(tmp_path):
    original = "Backstage 2\t/ˈbɛksteɪd͡ʒ/, /ˈbɛksteːt͡ʃ/"
    rows = list(iter_ipa_entries(source(tmp_path, "\n" + original + "\nÖzdemir\t/ˈøzdemɪʁ/\n"), "de", "ipa-de"))
    assert [row["ipa"] for row in rows] == ["/ˈbɛksteɪd͡ʒ/", "/ˈbɛksteːt͡ʃ/", "/ˈøzdemɪʁ/"]
    assert rows[0]["text"] == "Backstage 2"
    assert rows[0]["source_ref"] == {"line_no": 2, "original_entry": original, "variant_index": 0}
    assert rows[1]["source_ref"]["variant_index"] == 1
    assert rows[0]["kind"] == "phrase" and rows[2]["kind"] == "word"
    assert all(row["origin"] == "dictionary" and row["source_id"] == "ipa-de" for row in rows)


def test_ipa_keeps_loanwords_digits_and_unknown_phones(tmp_path):
    path = source(tmp_path, "'bout\t/ˈbaʊt/\nC++\t/siː☃/\nB2B\t/biːtuːbiː/\n")
    assert [row["text"] for row in iter_ipa_entries(path, "en", "ipa-en")] == ["'bout", "C++", "B2B"]


def test_reader_is_lazy_and_reports_malformed_ipa_instead_of_skipping(tmp_path):
    reader = iter_ipa_entries(source(tmp_path, "word\t/wɝd/\nbroken\n"), "en", "ipa")
    assert next(reader)["text"] == "word"
    with pytest.raises(CorpusFormatError, match=":2:"):
        next(reader)


def test_thesaurus_removes_registers_retains_lexical_and_unknown_parentheses(tmp_path):
    path = source(tmp_path, "# License: retained by manifest\n(nicht) koscher (ugs.);dubios (geh., veraltet);X 42 (unbekannt 123)\n", "thesaurus.txt")
    rows = list(iter_thesaurus_entries(path, "open-thesaurus"))
    assert [row["text"] for row in rows] == ["(nicht) koscher", "dubios", "X 42 (unbekannt 123)"]
    assert rows[0]["source_ref"]["register"] == ["ugs."]
    assert rows[1]["source_ref"]["register"] == ["geh.", "veraltet"]
    assert rows[2]["source_ref"]["unclassified_qualifiers"] == ["unbekannt 123"]
    assert rows[0]["source_ref"]["original_entry"] == "(nicht) koscher (ugs.)"
    assert rows[0]["source_ref"]["group"] == 2
    assert rows[0]["relations"] == ["dubios", "X 42 (unbekannt 123)"]
    assert rows[1]["kind"] == "word" and rows[0]["kind"] == "phrase"
    assert all(row["language"] == "de" and row["ipa"] is None for row in rows)


def test_unknown_mixed_register_is_preserved_as_a_whole(tmp_path):
    rows = list(iter_thesaurus_entries(source(tmp_path, "Wort (ugs., 77);anderes\n"), "th"))
    assert rows[0]["text"] == "Wort (ugs., 77)"
    assert rows[0]["source_ref"]["register"] == []


def test_empty_thesaurus_term_is_reported(tmp_path):
    with pytest.raises(CorpusFormatError, match="empty term"):
        list(iter_thesaurus_entries(source(tmp_path, "word;;another\n"), "th"))


def test_tatoeba_preserves_exact_sentence_and_author_attribution(tmp_path):
    sentence = "  Überm Fluss,  sagt Jo: ‚Hello-world!‘  "
    path = source(tmp_path, f"77\tdeu\t{sentence}\tauthor-name\t\\N\t2010-10-11 09:53:14\n")
    row, = iter_tatoeba_entries(path, "tatoeba-de")
    assert row["text"] == sentence
    assert row["origin"] == "attested_phrase" and row["kind"] == "phrase"
    assert row["language"] == "de"
    assert row["source_ref"] == {
        "sentence_id": 77, "author": "author-name",
        "url": "https://tatoeba.org/en/sentences/show/77",
        "date_added": None, "date_modified": "2010-10-11 09:53:14",
        "line_no": 1, "language_code": "deu",
    }


def test_unknown_language_and_missing_author_are_not_discarded(tmp_path):
    row, = iter_tatoeba_entries(source(tmp_path, "123\txxx\tUnknown word.\t\\N\t\\N\t\\N\n"), "source")
    assert row["language"] == "xxx" and row["source_ref"]["author"] is None


@pytest.mark.parametrize("line", ["1\tdeu\tText\n", "bad-id\tdeu\tText\tauthor\t\\N\t\\N\n"])
def test_malformed_tatoeba_rows_are_reported(tmp_path, line):
    with pytest.raises(CorpusFormatError, match=":1:"):
        list(iter_tatoeba_entries(source(tmp_path, line), "source"))


def test_compressed_sources_stream_without_a_different_contract(tmp_path):
    path = tmp_path / "source.tsv.bz2"
    with bz2.open(path, "wt", encoding="utf-8") as handle:
        handle.write("word\t/wɝd/\n")
    assert next(iter_ipa_entries(path, "en", "compressed"))["text"] == "word"


def test_no_hidden_ten_thousand_sentence_limit(tmp_path):
    path = source(tmp_path, "".join(f"{i}\tdeu\tWort {i}.\tauthor\t\\N\t\\N\n" for i in range(1, 10003)))
    assert sum(1 for _ in iter_tatoeba_entries(path, "source")) == 10002


def test_windows_retain_exact_spans_context_and_attribution_without_mutating_row():
    text = "  C++ und R&B,  sagt Anne-Marie: läuft's?  "
    row = {"text": text, "language": "de", "source_id": "source", "ipa": "/whole/", "source_ref": {"sentence_id": 8, "author": "A"}}
    windows = list(iter_sentence_windows(row, 2, 3))
    assert windows[0]["text"] == "C++ und"
    assert windows[1]["text"] == "und R&B"
    assert windows[2]["text"] == "R&B,  sagt"
    assert any(window["text"] == "sagt Anne-Marie: läuft's" for window in windows)
    for window in windows:
        ref = window["source_ref"]
        assert text[ref["char_start"]:ref["char_end"]] == window["text"]
        assert ref["context"] == text and ref["author"] == "A" and ref["sentence_id"] == 8
        assert window["ipa"] is None
        assert 2 <= ref["end_word"] - ref["start_word"] <= 3
    windows[0]["source_ref"]["author"] = "Changed"
    assert row["source_ref"] == {"sentence_id": 8, "author": "A"}
    assert row["ipa"] == "/whole/"


def test_windows_support_one_word_and_entire_long_sentence():
    text = " ".join(f"Wort{i}" for i in range(12))
    windows = list(iter_sentence_windows({"text": text}, 1, None))
    assert len(windows) == 12 * 13 // 2
    assert windows[0]["kind"] == "word" and windows[-1]["text"] == text
    assert windows[-1]["source_ref"]["end_word"] == 12


@pytest.mark.parametrize("minimum,maximum", [(0, 3), (2, 1), (True, 2), (1, False), (1, 2.5)])
def test_windows_validate_explicit_bounds(minimum, maximum):
    with pytest.raises(ValueError):
        list(iter_sentence_windows({"text": "word"}, minimum, maximum))


def test_no_windows_for_a_short_or_wordless_sentence():
    assert list(iter_sentence_windows({"text": "Wort."})) == []
    assert list(iter_sentence_windows({"text": "…?!"}, 1, None)) == []
