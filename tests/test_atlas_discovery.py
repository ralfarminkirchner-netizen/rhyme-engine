"""Small public synthetic corpora exercise real SQLite/FTS discovery."""
import json

import pytest

from app.services.atlas_discovery import discover
from app.services.atlas_phonetics import parse_ipa
from app.services.rhyme_atlas import AtlasStore


@pytest.fixture
def store(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite")
    store.initialize()
    words = {
        "Kara": "/ˈkaː.ra/", "Mara": "/ˈmaː.ra/", "Nell": "/nɛl/", "Pell": "/pɛl/",
        "liebt": "/liːpt/", "sieht": "/ziːt/", "sagt": "/zaːkt/", "Tom": "/tɔm/",
        "im": "/ɪm/", "IM": "/iː.ɛm/",
    }
    store.insert_entries([store.prepare_entry({"text": text, "ipa": ipa, "language": "de", "source_id": "ipa-de"}, frequency=100) for text, ipa in words.items()])
    with store.connect(True) as conn:
        for identifier, text in enumerate(["Kara liebt Nell.", "Mara sieht Nell.", "Nell sagt: Mara liebt Tom."], 1):
            ref = {"sentence_id": identifier, "author": "Synthetic Author", "url": f"https://example.org/{identifier}"}
            conn.execute("insert into corpus_sentences(id,source_id,sentence_id,text,source_ref) values(?,?,?,?,?)", (identifier, "synthetic-corpus", str(identifier), text, json.dumps(ref)))
            conn.execute("insert into corpus_fts(rowid,text) values(?,?)", (identifier, text))
    return store


def anchor(text="Zara sieht Pell"):
    return {"text": text, **parse_ipa("/ˈzaː.ra ziːt pɛl/")}


def options(**overrides):
    return {"mode": "dirty", "min_syllables": 4, "max_syllables": 4, "kind": "phrase", "discovery_seconds": 3, **overrides}


def test_discovers_acoustically_useful_exact_corpus_spans_with_attribution(store):
    rows = discover(store, [anchor()], options())
    assert rows
    found = next(row for row in rows if row["text"] == "Kara liebt Nell")
    assert found["origin"] == "attested_phrase" and found["source_id"] == "synthetic-corpus"
    assert found["data"]["syllable_count"] == 4
    ref = found["source_ref"]
    assert ref["author"] == "Synthetic Author" and ref["sentence_id"] == 1
    assert ref["context"][ref["char_start"]:ref["char_end"]] == found["text"]
    assert ref["discovery"]["bounded"] is True


def test_nested_data_anchors_are_also_supported_and_anchors_are_excluded(store):
    flat = anchor("Kara liebt Nell")
    rows = discover(store, [{"text": flat["text"], "data": flat}], options())
    assert rows and all(row["text"] != "Kara liebt Nell" for row in rows)


def test_constructed_paths_require_attested_join_and_retain_parts_not_whole_author(store):
    rows = discover(store, [anchor()], options(include_combinations=True, origin="constructed"))
    found = next(row for row in rows if row["text"] == "Mara liebt Nell")
    assert found["origin"] == "constructed" and found["source_id"] == "atlas-combinations"
    ref = found["source_ref"]
    assert "author" not in ref and "sentence_id" not in ref
    assert ref["join_evidence"]["text"] == "liebt Nell"
    assert [part["text"] for part in ref["parts"]] == ["Mara liebt", "Nell"]
    for part in ref["parts"]:
        evidence = part["source_ref"]
        assert evidence["context"][evidence["char_start"]:evidence["char_end"]] == part["text"]
    assert all(row["origin"] == "constructed" for row in rows)


def test_include_combinations_false_and_attested_filter_really_exclude_constructions(store):
    assert all(row["origin"] != "constructed" for row in discover(store, [anchor()], options(include_combinations=False)))
    assert all(row["origin"] != "constructed" for row in discover(store, [anchor()], options(include_combinations=True, origin="attested")))
    assert discover(store, [anchor()], options(include_combinations=False, origin="constructed")) == []


def test_unattested_join_is_never_invented(store):
    rows = discover(store, [anchor()], options(include_combinations=True, origin="constructed"))
    with store.connect() as conn:
        contexts = [row[0] for row in conn.execute("select text from corpus_sentences")]
    for row in rows:
        assert row["source_ref"]["join_evidence"]["text"] in " ".join(contexts)
        assert row["text"] not in contexts


@pytest.mark.parametrize("overrides", [{"languages": ["en"]}, {"kind": "compound"}, {"min_syllables": 20, "max_syllables": 30}])
def test_discovery_respects_language_kind_and_syllable_filters(store, overrides):
    assert discover(store, [anchor()], options(**overrides)) == []


def test_output_limit_and_syllable_bounds_are_obeyed(store):
    rows = discover(store, [anchor()], options(discovery_limit=1, include_combinations=True))
    assert len(rows) == 1 and rows[0]["data"]["syllable_count"] == 4


def test_read_only_discovery_does_not_materialize_or_modify_corpus(store):
    with store.connect() as conn:
        before = conn.execute("select count(*) from entries").fetchone()[0]
    discover(store, [anchor()], options(include_combinations=True))
    with store.connect() as conn:
        assert conn.execute("select count(*) from entries").fetchone()[0] == before
        assert conn.execute("select count(*) from corpus_sentences").fetchone()[0] == 3


def test_empty_anchors_are_a_noop(store):
    assert discover(store, [], options()) == []


def test_word_view_works_and_never_emits_constructed_phrases(store):
    rows = discover(store, [{"text": "Pell", **parse_ipa("/pɛl/")}], options(
        kind="word", min_syllables=1, max_syllables=1, include_combinations=True,
    ))
    assert rows and all(row["kind"] == "word" and row["origin"] == "attested_phrase" for row in rows)
    assert any(row["text"] == "Nell" for row in rows)


def test_long_windows_are_not_limited_to_six_words(store):
    sentence = "Kara liebt Nell Kara liebt Nell Kara liebt Nell."
    with store.connect(True) as conn:
        conn.execute("insert into corpus_sentences(id,source_id,sentence_id,text,source_ref) values(4,'synthetic-corpus','4',?,?)", (sentence, json.dumps({"sentence_id": 4, "author": "Synthetic Author"})))
        conn.execute("insert into corpus_fts(rowid,text) values(4,?)", (sentence,))
    long_anchor = {"text": "Zara sieht Pell Zara sieht Pell Zara sieht Pell", **parse_ipa("/za.ra ziːt pɛl za.ra ziːt pɛl za.ra ziːt pɛl/")}
    rows = discover(store, [long_anchor], options(mode="balanced", min_syllables=12, max_syllables=12))
    assert any(row["text"] == sentence[:-1] and row["data"]["syllable_count"] == 12 for row in rows)


def test_batch_lookup_preserves_case_priority_for_im(store):
    from app.services.atlas_discovery import _word_profiles
    from time import monotonic
    with store.connect() as conn:
        profiles = _word_profiles(conn, store, {"im", "IM"}, monotonic() + 2)
    assert profiles["im"]["data"]["syllable_count"] == 1
    assert profiles["IM"]["data"]["syllable_count"] == 2


def test_dirty_defaults_to_two_internal_extra_syllables(store):
    sentence = "Kara sagt sieht liebt Nell."
    with store.connect(True) as conn:
        conn.execute("insert into corpus_sentences(id,source_id,sentence_id,text,source_ref) values(4,'synthetic-corpus','4',?,?)", (sentence, json.dumps({"sentence_id": 4, "author": "Synthetic Author"})))
        conn.execute("insert into corpus_fts(rowid,text) values(4,?)", (sentence,))
    rows = discover(store, [anchor()], options(min_syllables=1, max_syllables=10))
    assert any(row["text"] == sentence[:-1] and row["data"]["syllable_count"] == 6 for row in rows)
    assert rows[0]["source_ref"]["discovery"]["syllables"] == [2, 3, 4, 5, 6]
    bounded = discover(store, [anchor()], options(min_syllables=1, max_syllables=10, syllable_flex=1))
    assert all(row["data"]["syllable_count"] <= 5 for row in bounded)


@pytest.mark.parametrize("mode", ["strict", "balanced", "dirty"])
def test_two_syllable_anchor_has_no_automatic_flex(store, mode):
    rows = discover(store, [{"text": "Zara", **parse_ipa("/ˈzaː.ra/")}], options(
        mode=mode, kind="all", min_syllables=1, max_syllables=10,
    ))
    assert rows and all(row["data"]["syllable_count"] == 2 for row in rows)
    assert rows[0]["source_ref"]["discovery"]["syllables"] == [2]


def test_public_matcher_family_prefilter_is_used_for_discovery(store, monkeypatch):
    import app.services.atlas_discovery as module
    from app.services.atlas_matching import candidate_families
    calls = []
    def families(family, mode):
        calls.append((family, mode))
        return candidate_families(family, mode)
    monkeypatch.setattr(module, "candidate_families", families)
    assert discover(store, [anchor()], options())
    assert ("a", "dirty") in calls and ("e", "dirty") in calls
