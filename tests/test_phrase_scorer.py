import pytest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.phrase_scorer import rank_rhymes, score_rhyme


# ── Testfall 1: schattenkabinett ──────────────────────────────────────────────

FALSE_POSITIVES = ["aktienkapitals", "attentäterin", "attenborough"]
TRUE_RHYMES_1   = ["auf dem parkett", "mit dem tablett"]

def test_false_positives_capped():
    """aktienkapitals & Co. dürfen nie Top-Tier sein → Score ≤ 0.40"""
    for cand in FALSE_POSITIVES:
        s = score_rhyme("schattenkabinett", cand)
        assert s.total <= 0.40, f"{cand!r} scored {s.total:.3f} – must be ≤ 0.40"
        assert s.anchor_gated, f"{cand!r} should be anchor-gated"

def test_true_rhymes_rank_high():
    """Echte End-Reime müssen ≥ 0.90 erreichen"""
    for cand in TRUE_RHYMES_1:
        s = score_rhyme("schattenkabinett", cand)
        assert s.total >= 0.90, f"{cand!r} scored {s.total:.3f} – must be ≥ 0.90"

def test_true_rhymes_beat_false_positives():
    """Echte Reime müssen ALLE False-Positives schlagen"""
    ranked = rank_rhymes("schattenkabinett",
                         TRUE_RHYMES_1 + FALSE_POSITIVES)
    top2 = [r.phrase for r in ranked[:2]]
    for tr in TRUE_RHYMES_1:
        assert tr in top2, f"{tr!r} not in top 2 – got {top2}"

def test_kein_respekt_middle_tier():
    """kein respekt ist ein guter aber nicht perfekter Reim (~0.7-0.85)"""
    s = score_rhyme("schattenkabinett", "kein respekt")
    assert 0.65 <= s.total <= 0.90, f"Got {s.total:.3f}"


# ── Testfall 2: deutsche meisterschaft ───────────────────────────────────────

def test_scheidensaft_top():
    """läuft wie scheidensaft ist der beste Reim → top 1"""
    ranked = rank_rhymes("deutsche meisterschaft", [
        "läuft wie scheidensaft", "häufig leicht gemacht",
        "deutlich nein gesagt", "teufel weiter lacht",
        "europameisterschaft", "euphemistische",
    ])
    assert ranked[0].phrase == "läuft wie scheidensaft", \
        f"Expected scheidensaft #1, got {ranked[0].phrase!r}"

def test_europameisterschaft_suffix_penalized():
    """europameisterschaft wird durch Suffix-Trap penalisiert"""
    s = score_rhyme("deutsche meisterschaft", "europameisterschaft")
    assert s.suffix_penalized, "Should be suffix-penalized"
    # Muss unter den echten Phrase-Reimen liegen
    good = score_rhyme("deutsche meisterschaft", "läuft wie scheidensaft")
    assert good.total > s.total, \
        f"scheidensaft ({good.total:.3f}) should beat europameisterschaft ({s.total:.3f})"

def test_euphemistische_gated():
    """euphemistische hat keinen Reim-Anker → Anker-Gate"""
    s = score_rhyme("deutsche meisterschaft", "euphemistische")
    assert s.anchor_gated, "euphemistische should be anchor-gated"
    assert s.total <= 0.40

def test_good_candidates_above_gate():
    """Gute Kandidaten müssen deutlich über dem Gate-Niveau liegen"""
    for cand in ["läuft wie scheidensaft", "teufel weiter lacht", "häufig leicht gemacht"]:
        s = score_rhyme("deutsche meisterschaft", cand)
        assert s.total > 0.70, f"{cand!r} scored only {s.total:.3f}"


# ── Allgemeine Eigenschaften ──────────────────────────────────────────────────

def test_identical_phrase_perfect():
    """Eine Phrase reimt perfekt mit sich selbst"""
    s = score_rhyme("schattenkabinett", "schattenkabinett")
    assert s.total >= 0.95

def test_completely_unrelated():
    """Komplett unverwandte Wörter → sehr niedriger Score"""
    s = score_rhyme("schattenkabinett", "blaubeere")
    assert s.total <= 0.50

def test_ranking_is_sorted():
    """rank_rhymes gibt eine absteigende Liste zurück"""
    ranked = rank_rhymes("schattenkabinett", [
        "auf dem parkett", "aktienkapitals", "mit dem tablett", "euphemistische"
    ])
    scores = [r.total for r in ranked]
    assert scores == sorted(scores, reverse=True), "Not sorted descending"

def test_global_similarity_alone_not_enough():
    """
    Gleiche Silbenzahl + ähnliche globale Vokalstruktur reicht NICHT für hohen Score
    wenn der Anker nicht stimmt.
    """
    # aktienkapitals hat 5 Silben wie schattenkabinett, ähnliche Vokalstruktur
    # aber kein End-Reim → muss gedeckelt bleiben
    s = score_rhyme("schattenkabinett", "aktienkapitals")
    assert s.total <= 0.40
    assert s.anchor_gated
