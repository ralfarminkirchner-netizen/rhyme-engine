"""Discovery, ordered mapping and persistence with a small invented corpus."""
import json

import pytest
from fastapi.testclient import TestClient

from app.services.rhyme_atlas import AtlasStore


@pytest.fixture
def store(tmp_path):
    target = AtlasStore(tmp_path / "atlas.sqlite")
    target.initialize()
    for source_id in ("ipa-de", "ipa-en", "tatoeba-de"):
        target.register_source(source_id, source_id, {"url": "https://example.org/source", "license": "Fixture"})
    entries = [
        ("Hase", "/ˈhaːzə/", "de", "word"),
        ("Nase", "/ˈnaːzə/", "de", "word"),
        ("Base", "/ˈbaːzə/", "de", "word"),
        ("Haus", "/haʊs/", "de", "word"),
        ("Maus", "/maʊs/", "de", "word"),
        ("Wiesennase", "/ˈviːzənˌnaːzə/", "de", "compound"),
        ("leise Gassen", "/ˈlaɪzə ˈɡasən/", "de", "phrase"),
        ("weise Massen", "/ˈvaɪzə ˈmasən/", "de", "phrase"),
        ("weite Wiesen", "/ˈvaɪtə ˈviːzən/", "de", "phrase"),
        ("im", "/ɪm/", "de", "word"),
        ("IM", "/iˈʔɛm/", "de", "word"),
        ("in", "/ɪn/", "de", "word"),
        ("IN", "/iˈʔɛn/", "de", "word"),
        ("rat", "/ʁaːt/", "de", "word"),
        ("rat", "/ɹæt/", "en", "word"),
        ("cat", "/kæt/", "en", "word"),
    ]
    target.insert_entries([target.prepare_entry({"text": text, "ipa": ipa, "language": lang,
        "kind": kind, "origin": "dictionary", "source_id": "ipa-" + lang,
        "source_ref": {"line_no": index + 1}}) for index, (text, ipa, lang, kind) in enumerate(entries)])
    target.refresh_statistics()
    return target


def options(**changes):
    return {"query": "Hase", "min_syllables": 1, "max_syllables": 32,
            "kind": "all", "mode": "dirty", "languages": ["de", "en"],
            "origin": "all", "include_combinations": False, "limit": 40, **changes}


def test_discovers_new_rhymes_and_excludes_all_query_anchors(store):
    found = store.search(options(query="Hase\nNase", mode="strict", kind="word"))
    assert [row["text"] for row in found["results"]] == ["Base"]
    assert found["results"][0]["source"]["license"] == "Fixture"
    assert found["results"][0]["source_ref"]["line_no"] == 3
    with store.connect() as conn:
        assert conn.execute("select count(*) from rhyme_neighbors").fetchone()[0] == 1


def test_one_syllable_search_stays_in_one_syllable_layer(store):
    found = store.search(options(query="Haus", kind="word", min_syllables=1, max_syllables=1))
    assert [row["text"] for row in found["results"]] == ["Maus"]
    assert all(row["syllable_count"] == 1 for row in found["results"])


def test_function_words_preserve_case_distinction_from_acronyms(store):
    for word in ("im", "in"):
        assert store.pronounce(word)[0]["syllable_count"] == 1
        assert store.pronounce(word.upper())[0]["syllable_count"] == 2
    assert store.pronounce("in im")[0]["syllable_count"] == 2


def test_map_filters_and_stable_length_axis(store):
    all_regions = store.map(options(limit=300))
    word_regions = store.map(options(kind="word", limit=300))
    assert all_regions["total_entries"] == 16
    positions = {row["id"]: (row["x"], row["y"]) for row in all_regions["regions"]}
    assert all(positions[row["id"]] == (row["x"], row["y"]) for row in word_regions["regions"])
    one = next(row for row in all_regions["regions"] if row["syllables"] == 1)
    four = next(row for row in all_regions["regions"] if row["syllables"] == 4)
    assert one["x"] + one["y"] < four["x"] + four["y"]
    assert store.map(options(kind="compound"))["total_entries"] == 1


def test_full_order_distinguishes_interior_sequences_in_same_region(store):
    region = {"syllables": 4, "first_family": "ai", "last_family": "schwa"}
    detail = store.neighborhood(region, options())
    assert {item["signature"] for item in detail["signatures"]} == {"ai-schwa-a-schwa", "ai-schwa-i-schwa"}
    selected = store.search(options(query="", region={**region, "signature": "ai-schwa-i-schwa"}))
    assert [row["text"] for row in selected["results"]] == ["weite Wiesen"]


def test_expand_preserves_native_english_pronunciation(store):
    with store.connect() as conn:
        native_id = conn.execute("select id from entries where text='rat' and language='en'").fetchone()[0]
    found = store.expand(native_id, options(mode="strict", kind="word"))
    assert found["anchors"][0]["ipa"] == "/ɹæt/"
    assert [row["text"] for row in found["results"]] == ["cat"]


def test_chain_preserves_selected_language_and_pronunciation_variant(store):
    with store.connect() as conn:
        native = dict(conn.execute("select * from entries where text='rat' and language='en'").fetchone())
    saved = store.save_chain("Native Variante", [{"text": "rat", "entry_id": native["id"]}])
    assert saved["members"][0]["ipa"] == "/ɹæt/"
    assert saved["members"][0]["language"] == "en"
    with pytest.raises(ValueError):
        store.save_chain("Falscher Bezug", [{"text": "Hase", "entry_id": native["id"]}])


def test_chain_keeps_original_spelling_when_dictionary_lookup_used_compact_alias(store):
    initial = store.save_chain("Getrennte Schreibung", ["Wiesen-Nase"])
    member = initial["members"][0]
    saved = store.save_chain("Übernommen", [{"text": member["text"], "entry_id": member["entry_id"]}])
    assert saved["members"][0]["text"] == "Wiesen-Nase"
    assert saved["members"][0]["entry_id"] == member["entry_id"]
    assert saved["members"][0]["ipa"] == "/ˈviːzənˌnaːzə/"


def test_index_prefilter_keeps_near_families_and_two_internal_extra_syllables(store):
    fixtures = [("Tür", "/tyːɐ̯/"), ("hier", "/hiːɐ̯/"),
                ("Alphafolge", "/ˈkaː.tɛ.li.nɛl/"), ("Betafolge", "/ˈbaː.tɛ.mə.nə.li.nɛl/")]
    store.materialize([{"text": text, "ipa": ipa, "source_id": "ipa-de", "language": "de", "kind": "word"} for text, ipa in fixtures])
    close = store.search(options(query="Tür", mode="balanced", kind="word"))
    assert "hier" in {row["text"] for row in close["results"]}
    flex = store.search(options(query="Alphafolge", kind="word"))
    assert "Betafolge" in {row["text"] for row in flex["results"]}


def test_materialized_paths_are_idempotent_and_constructed_is_separate(store):
    row = {"text": "Hase im Haus", "ipa": "/ˈhaːzə ɪm haʊs/", "language": "de", "kind": "phrase",
           "origin": "constructed", "source_id": "ipa-de", "source_ref": {"parts": [1, 4]}}
    first = store.materialize([row])[0]
    assert store.materialize([row])[0]["id"] == first["id"]
    assert store.status()["counts"]["pronunciations"] == 17
    assert store.map(options(origin="attested"))["total_entries"] == 16
    assert store.map(options(origin="constructed", include_combinations=True))["total_entries"] == 1
    assert store.map(options(origin="constructed", include_combinations=False))["total_entries"] == 0
    with store.connect() as conn:
        assert conn.execute("select count(*) from sound_edges").fetchone()[0] > 0


def test_chain_order_reopens_and_custom_segments_become_local_paths(store):
    saved = store.save_chain("Erfundene Folge", ["Nase", "Hase im Haus", "Base"])
    reopened = AtlasStore(store.path).chains()["chains"][0]
    assert saved == reopened
    assert [member["text"] for member in reopened["members"]] == ["Nase", "Hase im Haus", "Base"]
    assert [member["position"] for member in reopened["members"]] == [0, 1, 2]
    assert all(member["entry_id"] for member in reopened["members"])
    assert reopened["members"][1]["syllable_count"] == 4
    with store.connect() as conn:
        assert conn.execute("select origin from entries where text='Hase im Haus'").fetchone()[0] == "user"


def test_atlas_api_routes_validate_filter_and_return_real_results(store, monkeypatch):
    monkeypatch.setenv("REIM_ATLAS_DIR", str(store.path.parent))
    from app.main import app
    client = TestClient(app)
    assert client.get("/api/atlas/status").json()["counts"]["entries"] == 14
    found = client.post("/api/atlas/search", json=options(kind="word", mode="strict"))
    assert found.status_code == 200, found.text
    assert {row["text"] for row in found.json()["results"]} == {"Nase", "Base"}
    assert client.post("/api/atlas/search", json=options(min_syllables=9, max_syllables=1)).status_code == 422
    assert client.post("/api/atlas/search", json=options(languages=[])).status_code == 422
    assert client.post("/api/atlas/expand", json={**{key: value for key, value in options().items() if key != "query"}, "entry_id": 99999}).status_code == 404
    assert client.get("/api/atlas/neighborhood?syllables=4&first_family=ai&last_family=schwa").status_code == 200
    saved = client.post("/api/atlas/chains", json={"title": "Folge", "members": ["Hase", "Nase"]})
    assert saved.status_code == 201
    assert client.get("/api/atlas/chains").json()["chains"][0] == saved.json()
