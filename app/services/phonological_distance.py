from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class PF:
    typ: str; place: str; voiced: bool; rounded: bool; long: bool; height: str = ""

FEATURES: Dict[str, PF] = {
    "a":   PF("vowel","central",True,False,False,"low"),
    "aː":  PF("vowel","central",True,False,True,"low"),
    "ɛ":   PF("vowel","front",True,False,False,"mid"),
    "eː":  PF("vowel","front",True,False,True,"mid"),
    "ɪ":   PF("vowel","front",True,False,False,"high"),
    "iː":  PF("vowel","front",True,False,True,"high"),
    "ɔ":   PF("vowel","back",True,True,False,"mid"),
    "oː":  PF("vowel","back",True,True,True,"mid"),
    "ʊ":   PF("vowel","back",True,True,False,"high"),
    "uː":  PF("vowel","back",True,True,True,"high"),
    "œ":   PF("vowel","front",True,True,False,"mid"),
    "øː":  PF("vowel","front",True,True,True,"mid"),
    "ʏ":   PF("vowel","front",True,True,False,"high"),
    "yː":  PF("vowel","front",True,True,True,"high"),
    "ə":   PF("vowel","central",True,False,False,"mid"),
    "ɐ":   PF("vowel","central",True,False,False,"mid"),
    "aɪ":  PF("diphthong","central",True,False,False),
    "aʊ":  PF("diphthong","back",True,True,False),
    "ɔʏ":  PF("diphthong","front",True,True,False),
    "p":   PF("plosive","labial",False,False,False),
    "b":   PF("plosive","labial",True,False,False),
    "t":   PF("plosive","alveolar",False,False,False),
    "d":   PF("plosive","alveolar",True,False,False),
    "k":   PF("plosive","velar",False,False,False),
    "g":   PF("plosive","velar",True,False,False),
    "f":   PF("fricative","labial",False,False,False),
    "v":   PF("fricative","labial",True,False,False),
    "s":   PF("fricative","alveolar",False,False,False),
    "z":   PF("fricative","alveolar",True,False,False),
    "ʃ":   PF("fricative","postalveolar",False,False,False),
    "ʒ":   PF("fricative","postalveolar",True,False,False),
    "ç":   PF("fricative","palatal",False,False,False),
    "x":   PF("fricative","velar",False,False,False),
    "h":   PF("fricative","glottal",False,False,False),
    "t͡s": PF("affricate","alveolar",False,False,False),
    "t͡ʃ": PF("affricate","postalveolar",False,False,False),
    "d͡ʒ": PF("affricate","postalveolar",True,False,False),
    "pf":  PF("affricate","labial",False,False,False),
    "m":   PF("nasal","labial",True,False,False),
    "n":   PF("nasal","alveolar",True,False,False),
    "ŋ":   PF("nasal","velar",True,False,False),
    "l":   PF("liquid","alveolar",True,False,False),
    "ʁ":   PF("liquid","uvular",True,False,False),
    "j":   PF("glide","palatal",True,False,False),
}

_HEIGHT = ["high","mid","low"]
_CORONAL = {"alveolar","postalveolar"}
_DORSAL  = {"palatal","velar","uvular"}

def _vowel_sim(a: PF, b: PF) -> float:
    h = 1.0 - abs(_HEIGHT.index(a.height) - _HEIGHT.index(b.height)) * 0.35 if a.height and b.height else 0.5
    p = 1.0 if a.place==b.place else (0.3 if {a.place,b.place}=={"front","back"} else 0.6)
    r = 1.0 if a.rounded==b.rounded else 0.7
    lo= 1.0 if a.long==b.long else 0.8
    return h*0.4 + p*0.3 + r*0.2 + lo*0.1

def _cons_sim(a: PF, b: PF) -> float:
    if a.place==b.place: ps=1.0
    elif a.place in _CORONAL and b.place in _CORONAL: ps=0.8
    elif a.place in _DORSAL  and b.place in _DORSAL:  ps=0.7
    else: ps=0.3
    vs = 1.0 if a.voiced==b.voiced else 0.6
    return ps*0.6 + vs*0.4

def phoneme_similarity(a: str, b: str) -> float:
    if a==b: return 1.0
    fa, fb = FEATURES.get(a), FEATURES.get(b)
    if not fa or not fb: return 0.0
    if fa.typ=="vowel" and fb.typ=="vowel":   return _vowel_sim(fa,fb)
    if fa.typ=="diphthong" and fb.typ=="diphthong":
        return 0.7 if fa.place==fb.place else 0.5
    consonant_types = {"plosive","fricative","affricate","nasal","liquid","glide"}
    if fa.typ in consonant_types and fb.typ in consonant_types:
        if fa.typ==fb.typ: return _cons_sim(fa,fb)
        similar = {frozenset({"plosive","affricate"}):0.7,
                   frozenset({"fricative","affricate"}):0.6,
                   frozenset({"nasal","liquid"}):0.5,
                   frozenset({"liquid","glide"}):0.6}
        return similar.get(frozenset({fa.typ,fb.typ}), 0.3)
    sonorants = {"vowel","diphthong","nasal","liquid","glide"}
    if fa.typ in sonorants and fb.typ in sonorants: return 0.5
    return 0.2

_INS: Dict[str,float] = {
    "vowel":0.6,"diphthong":0.7,"plosive":0.8,
    "fricative":0.75,"affricate":0.8,"nasal":0.65,
    "liquid":0.65,"glide":0.6,
}

def insertion_cost(p: str) -> float:
    if p in {"ə","ɐ"}: return 0.4
    f = FEATURES.get(p)
    return _INS.get(f.typ, 0.8) if f else 1.0

def substitution_cost(a: str, b: str) -> float:
    return 1.0 - phoneme_similarity(a, b)

def phonological_edit_distance(a: List[str], b: List[str]) -> float:
    if not a and not b: return 0.0
    if not a: return min(1.0, sum(insertion_cost(p) for p in b)/max(len(b),1))
    if not b: return min(1.0, sum(insertion_cost(p) for p in a)/max(len(a),1))

    rows, cols = len(a)+1, len(b)+1
    dp = [[0.0]*cols for _ in range(rows)]
    for i in range(1,rows): dp[i][0] = dp[i-1][0]+insertion_cost(a[i-1])
    for j in range(1,cols): dp[0][j] = dp[0][j-1]+insertion_cost(b[j-1])
    for i in range(1,rows):
        for j in range(1,cols):
            dp[i][j] = min(
                dp[i-1][j-1]+substitution_cost(a[i-1],b[j-1]),
                dp[i][j-1]  +insertion_cost(b[j-1]),
                dp[i-1][j]  +insertion_cost(a[i-1]),
            )
    max_cost = max(len(a),len(b))*0.8
    return min(1.0, dp[rows-1][cols-1]/max_cost) if max_cost else 0.0

def tail_similarity(a: List[str], b: List[str]) -> float:
    if not a and not b: return 1.0
    if not a or not b:  return 0.0
    return 1.0 - phonological_edit_distance(a, b)
