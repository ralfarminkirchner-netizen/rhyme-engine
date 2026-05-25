import pytest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.phonological_distance import tail_similarity, phoneme_similarity
from app.services.parser import parse_german_word
from app.services.rhyme_engine import RhymeEngine
from app.schemas.rhyme import Mode, RawWeights


# ── Phonologische Distanz ─────────────────────────────────────────────────────

def test_identical_tail():
    assert tail_similarity(["aɪ","n"], ["aɪ","n"]) == 1.0

def test_empty_tails():
    assert tail_similarity([], []) == 1.0

def test_different_vowel():
    # a vs ʊ haben unterschiedlichen Ort – Similarity deutlich unter 1.0
    sim = tail_similarity(["a","k"], ["ʊ","k"])
    assert sim < 0.85
    # und klar kleiner als identische Tails
    assert tail_similarity(["a","k"], ["a","k"]) > sim

def test_voicing_pair_similar():
    sim = phoneme_similarity("p","b")
    assert sim > 0.6

def test_same_phoneme():
    assert phoneme_similarity("iː","iː") == 1.0

def test_sein_schein_perfect():
    # Tail von "sein" == Tail von "schein" → 1.0
    s = parse_german_word("sein")
    sc= parse_german_word("schein")
    assert tail_similarity(s.tail, sc.tail) == 1.0


# ── Engine ────────────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    words = ["sein","schein","allein","bewusstsein","Licht","dicht","Bach","Fach",
             "Haus","Maus","lieb","gut","Hut","Zeit","weit"]
    return RhymeEngine([parse_german_word(w) for w in words])

def test_no_self_match(engine):
    q = parse_german_word("sein")
    r = engine.search(q, Mode.BALANCED)
    assert "sein" not in [c.text for c in r.results]

def test_mode_preserved(engine):
    q = parse_german_word("sein")
    r = engine.search(q, Mode.STRICT)
    assert r.mode == Mode.STRICT

def test_limit_respected(engine):
    q = parse_german_word("sein")
    r = engine.search(q, Mode.DIRTY, limit=2)
    assert len(r.results) <= 2

def test_debug_rejected(engine):
    q = parse_german_word("sein")
    r = engine.search(q, Mode.HARDCORE, include_debug=True)
    assert r.rejected is not None

def test_no_debug_no_rejected(engine):
    q = parse_german_word("sein")
    r = engine.search(q, Mode.BALANCED, include_debug=False)
    assert r.rejected is None

def test_rejected_has_no_score(engine):
    q = parse_german_word("sein")
    r = engine.search(q, Mode.HARDCORE, include_debug=True)
    if r.rejected:
        for rej in r.rejected:
            assert not hasattr(rej, "score") or "score" not in rej.model_fields_set

def test_custom_weights(engine):
    q = parse_german_word("sein")
    w = RawWeights(stress=0.1, vowelCore=0.1, tail=0.7, syllableFlex=0.1)
    r = engine.search(q, Mode.BALANCED, custom_weights=w)
    assert r is not None
    assert r.weights.tail == 0.7

def test_end_rhyme_uses_terminal(engine):
    q = parse_german_word("bewusstsein")
    r = engine.search(q, Mode.END_RHYME)
    assert r.target.value == "terminal"


# ── API ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    # Mini-Setup ohne Lifespan
    from fastapi import FastAPI
    from app.api.routes import rhymes as rr
    from app.services.rhyme_engine import RhymeEngine
    words = ["sein","schein","allein","Licht","dicht","Bach","Fach"]
    rr.set_engine(RhymeEngine([parse_german_word(w) for w in words]))
    from app.main import app
    return TestClient(app, raise_server_exceptions=True)

def test_health(client):
    r = client.get("/api/rhymes/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_modes_endpoint(client):
    r = client.get("/api/rhymes/modes")
    assert r.status_code == 200
    data = r.json()
    assert "modes" in data
    assert "balanced" in data["modes"]
    mode = data["modes"]["balanced"]
    assert "thresholds" in mode
    assert "defaultWeights" in mode

def test_analyze_endpoint(client):
    r = client.post("/api/rhymes/analyze", json={"word": "sein"})
    assert r.status_code == 200
    data = r.json()
    assert data["text"] == "sein"
    assert "aɪ" in data["phonetic"]
    assert data["syllableCount"] == 1

def test_search_endpoint(client):
    r = client.post("/api/rhymes/search", json={
        "query": "sein", "mode": "balanced", "limit": 10, "debug": False
    })
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "balanced"
    assert "results" in data
    assert data["rejected"] is None

def test_search_debug(client):
    r = client.post("/api/rhymes/search", json={
        "query": "sein", "mode": "hardcore", "limit": 10, "debug": True
    })
    assert r.status_code == 200
    data = r.json()
    assert data["rejected"] is not None

def test_analyze_empty(client):
    r = client.post("/api/rhymes/analyze", json={"word": ""})
    assert r.status_code == 422

def test_search_invalid_mode(client):
    r = client.post("/api/rhymes/search", json={"query": "sein", "mode": "invalid"})
    assert r.status_code == 422
