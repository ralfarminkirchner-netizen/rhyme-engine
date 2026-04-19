from __future__ import annotations
from typing import List, Optional
from app.schemas.rhyme import ParsedWord

# ── Phoneminventar ────────────────────────────────────────────────────────────

VOWELS = {
    "a", "aː", "ɛ", "eː", "ɪ", "iː", "ɔ", "oː",
    "ʊ", "uː", "œ", "øː", "ʏ", "yː", "ə", "ɐ",
}
DIPHTHONGS = {"aɪ", "aʊ", "ɔʏ"}
LETTER_VOWELS = set("aeiouäöüy")

VOICELESS_FINAL: dict[str, str] = {
    "b": "p", "d": "t", "g": "k",
    "z": "s", "v": "f", "ʒ": "ʃ",
}

UNSTRESSED_PREFIXES = {"be", "ge", "ver", "zer", "ent", "emp", "er"}

# ── v → /v/ statt /f/ — Fremdwort-Lexikon ───────────────────────────────────
# Default: v → /f/ (Vater, Volk, vier, viel, von, vor).
# Ausnahmen: Lehnwörter mit /v/-Aussprache.
# Strategie: vollständiges Wort-Lookup + Präfix-Whitelist für produktive Muster.
# Mittelfristig: größere Wortliste oder Override-Feld in Datenbankeinträgen.

# Vollständige Wörter die v = /v/ sprechen
V_WORDS: frozenset[str] = frozenset({
    # Klassische Lehnwörter
    "vase", "vanille", "villa", "virus", "visum", "violin", "viola",
    "vitamine", "vitamin", "video", "visa", "venus", "version",
    "vision", "vakuum", "vakanz", "vamp", "van", "veto",
    # Adjektiv-Endungen auf -iv, -ativ, -ativ (produktives Muster)
    "aktiv", "passiv", "relativ", "motiv", "progressiv", "intensiv",
    "kreativ", "kollektiv", "subjektiv", "objektiv", "negativ", "positiv",
    "sensitiv", "intuitiv", "primitiv", "reaktiv", "operativ",
    "naiv", "kursiv",
    # November/Revolution/Universität etc.
    "november", "revolte", "revolution", "evolution", "intervention",
    "innovation", "motivation", "derivat", "derivation",
    "universum", "universität", "universal",
    # Eigennamen (häufig)
    "viktor", "viviane", "viola", "virginia", "victoria", "vincent",
    "valentina", "valeria",
})

# Wort-Präfixe die /v/ indizieren (für Wörter die nicht im Lexikon stehen)
V_PREFIXES: tuple[str, ...] = (
    "viol",   # Violin, Viola, Violett
    "virus",  # Virus, Virusinfekt
    "vide",   # Video, Videokassette
    "vita",   # Vitamin, vital
    "vakuu",  # Vakuum
)

def _v_to_phoneme(word_lower: str) -> str:
    """Gibt /v/ oder /f/ für <v> zurück, abhängig vom Gesamtwort.

    Heuristik v1 — bewusst konservativ:
    - Vollständiges Wort im V_WORDS-Lexikon → /v/
    - Wort beginnt mit V_PREFIXES → /v/
    - Sonst: /f/ (Standarddeutsch-Default)
    """
    if word_lower in V_WORDS:
        return "v"
    for prefix in V_PREFIXES:
        if word_lower.startswith(prefix):
            return "v"
    return "f"

ALLOWED_ONSETS = {
    "p l", "p r", "b l", "b r", "d r", "f l", "f r",
    "g l", "g r", "k l", "k r", "t r",
    "ʃ p", "ʃ t", "ʃ l", "ʃ m", "ʃ n",
    "s p", "s t", "t͡s v",
}

# ── Ausnahmen ─────────────────────────────────────────────────────────────────

EXCEPTIONS: dict[str, dict] = {
    "sein":        {"phonetic": ["z","aɪ","n"],                              "stress": [1]},
    "schein":      {"phonetic": ["ʃ","aɪ","n"],                              "stress": [1]},
    "allein":      {"phonetic": ["a","l","aɪ","n"],                          "stress": [0,1]},
    "bewusstsein": {"phonetic": ["b","ə","v","ʊ","s","t","t͡s","aɪ","n"],    "stress": [0,1,0]},
    "verstehen":   {"phonetic": ["f","ɛ","ɐ","ʃ","t","eː","ə","n"],         "stress": [0,1,0]},
    "besser":      {"phonetic": ["b","ɛ","s","ɐ"],                           "stress": [1,0]},
    "lieb":        {"phonetic": ["l","iː","p"],                              "stress": [1]},
    "buch":        {"phonetic": ["b","uː","x"],                              "stress": [1]},
    "ich":         {"phonetic": ["ɪ","ç"],                                   "stress": [1]},
    "gehen":       {"phonetic": ["g","eː","ə","n"],                          "stress": [1,0]},
    "sehen":       {"phonetic": ["z","eː","ə","n"],                          "stress": [1,0]},
}

# ── Helfer ────────────────────────────────────────────────────────────────────

def is_vowel(p: str) -> bool:
    return p in VOWELS or p in DIPHTHONGS

def is_back_vowel(p: str) -> bool:
    return p in {"a","aː","ɔ","oː","ʊ","uː","aʊ"}

# ── G2P ───────────────────────────────────────────────────────────────────────

def _choose_ch(prev: Optional[str]) -> str:
    return "x" if (prev and is_back_vowel(prev)) else "ç"

def _choose_s(w: str, i: int) -> str:
    prev = w[i-1] if i > 0 else ""
    nxt  = w[i+1] if i+1 < len(w) else ""
    if (i == 0 and nxt in LETTER_VOWELS) or (prev in LETTER_VOWELS and nxt in LETTER_VOWELS):
        return "z"
    return "s"

def _apply_final_devoicing(phones: List[str]) -> List[str]:
    if phones and phones[-1] in VOICELESS_FINAL:
        phones[-1] = VOICELESS_FINAL[phones[-1]]
    return phones

def _apply_r_vocalization(phones: List[str]) -> List[str]:
    out = phones[:]
    for i, p in enumerate(out):
        if p != "ʁ":
            continue
        prev = out[i-1] if i > 0 else None
        nxt  = out[i+1] if i+1 < len(out) else None
        if prev and is_vowel(prev) and (nxt is None or not is_vowel(nxt)):
            out[i] = "ɐ"
    return out

def graphemes_to_phonemes(word: str) -> List[str]:
    w = word.strip().lower()
    if w in EXCEPTIONS:
        return list(EXCEPTIONS[w]["phonetic"])

    out: List[str] = []
    i = 0
    while i < len(w):
        rest = w[i:]

        # 4-Zeichen
        if rest.startswith("tsch"): out.append("t͡ʃ"); i+=4; continue
        if rest.startswith("dsch"): out.append("d͡ʒ"); i+=4; continue
        # 3-Zeichen
        if rest.startswith("sch"):  out.append("ʃ");   i+=3; continue
        # 2-Zeichen Digraphe
        if rest.startswith("ei") or rest.startswith("ai") or rest.startswith("ey") or rest.startswith("ay"):
            out.append("aɪ"); i+=2; continue
        if rest.startswith("au"):   out.append("aʊ"); i+=2; continue
        if rest.startswith("eu") or rest.startswith("äu"): out.append("ɔʏ"); i+=2; continue
        if rest.startswith("ie"):   out.append("iː"); i+=2; continue
        if rest.startswith("aa") or rest.startswith("ah"): out.append("aː"); i+=2; continue
        if rest.startswith("ee") or rest.startswith("eh"): out.append("eː"); i+=2; continue
        if rest.startswith("oo") or rest.startswith("oh"): out.append("oː"); i+=2; continue
        if rest.startswith("uh"):   out.append("uː"); i+=2; continue
        if rest.startswith("öh") or rest.startswith("oe"): out.append("øː"); i+=2; continue
        if rest.startswith("üh") or rest.startswith("ue"): out.append("yː"); i+=2; continue
        if rest.startswith("ng"):   out.append("ŋ");   i+=2; continue
        if rest.startswith("pf"):   out.append("pf");  i+=2; continue
        if rest.startswith("tz"):   out.append("t͡s"); i+=2; continue
        if rest.startswith("ck"):   out.append("k");   i+=2; continue
        if rest.startswith("qu"):   out.extend(["k","v"]); i+=2; continue
        if rest.startswith("ph"):   out.append("f");   i+=2; continue
        if rest.startswith("ch"):
            out.append(_choose_ch(out[-1] if out else None)); i+=2; continue
        if rest.startswith("sp") and i == 0: out.extend(["ʃ","p"]); i+=2; continue
        if rest.startswith("st") and i == 0: out.extend(["ʃ","t"]); i+=2; continue
        # wortfinale Reduktionen
        if rest.startswith("er") and i+2 == len(w): out.append("ɐ"); i+=2; continue
        if rest.startswith("en") and i+2 == len(w): out.extend(["ə","n"]); i+=2; continue
        if rest == "e":                               out.append("ə");  i+=1; continue

        c = w[i]
        # Einzelbuchstaben → IPA (Python 3.9-kompatibel, kein match/case)
        if   c == "a": out.append("a")
        elif c == "e": out.append("ɛ")
        elif c == "i": out.append("ɪ")
        elif c == "o": out.append("ɔ")
        elif c == "u": out.append("ʊ")
        elif c == "ä": out.append("ɛ")
        elif c == "ö": out.append("œ")
        elif c in ("ü","y"): out.append("ʏ")
        elif c == "b": out.append("b")
        elif c == "d": out.append("d")
        elif c == "f": out.append("f")
        elif c == "g": out.append("g")
        elif c == "h": pass             # Dehnungs-h / stummes h
        elif c == "j": out.append("j")
        elif c == "k": out.append("k")
        elif c == "l": out.append("l")
        elif c == "m": out.append("m")
        elif c == "n": out.append("n")
        elif c == "p": out.append("p")
        elif c == "r": out.append("ʁ")
        elif c == "s": out.append(_choose_s(w, i))
        elif c == "ß": out.append("s")
        elif c == "t": out.append("t")
        elif c == "v": out.append(_v_to_phoneme(w))
        elif c == "w": out.append("v")
        elif c == "x": out.extend(["k","s"])
        elif c == "z": out.append("t͡s")
        else:          out.append(c)
        i += 1

    return _apply_final_devoicing(_apply_r_vocalization(out))

# ── Silbentrennung ────────────────────────────────────────────────────────────

def _split_cluster(cluster: List[str]) -> tuple[List[str], List[str]]:
    if not cluster:     return [], []
    if len(cluster)==1: return [], cluster
    for take in range(min(3, len(cluster)), 0, -1):
        right = cluster[-take:]
        if " ".join(right) in ALLOWED_ONSETS:
            return cluster[:-take], right
    return cluster[:-1], cluster[-1:]

def syllabify(phones: List[str]) -> List[List[str]]:
    nuclei = [i for i,p in enumerate(phones) if is_vowel(p)]
    if not nuclei:
        return [phones[:]]
    syllables: List[List[str]] = []
    start = 0
    for n in range(len(nuclei)-1):
        nuc      = nuclei[n]
        nxt_nuc  = nuclei[n+1]
        cluster  = phones[nuc+1:nxt_nuc]
        left, right = _split_cluster(cluster)
        end = nuc+1+len(left)
        syllables.append(phones[start:end])
        start = nxt_nuc - len(right)
    syllables.append(phones[start:])
    return syllables

# ── Betonung ──────────────────────────────────────────────────────────────────

STRESS_SUFFIX_RULES = [
    ("ieren", 2), ("ität", 1), ("ion", 1), ("iv", 1), ("ik", 1), ("ur", 1),
]

def detect_stress(word: str, syllable_count: int) -> List[int]:
    w = word.strip().lower()
    if w in EXCEPTIONS and "stress" in EXCEPTIONS[w]:
        pat = list(EXCEPTIONS[w]["stress"])
        while len(pat) < syllable_count: pat.append(0)
        return pat[:syllable_count]

    arr = [0] * max(1, syllable_count)
    if syllable_count <= 1:
        arr[0] = 1
        return arr

    for suffix, idx in STRESS_SUFFIX_RULES:
        if w.endswith(suffix):
            arr[min(syllable_count-idx, syllable_count-1)] = 1
            return arr

    if any(w.startswith(p) for p in UNSTRESSED_PREFIXES) and syllable_count > 1:
        arr[1] = 1
        return arr

    arr[0] = 1
    return arr

# ── Reim-Features ─────────────────────────────────────────────────────────────

def _last_stress_idx(stress: List[int]) -> int:
    for i in range(len(stress)-1, -1, -1):
        if stress[i] == 1:
            return i
    return max(0, len(stress)-1)

def _last_vowel_idx(phones: List[str]) -> int:
    for i in range(len(phones)-1, -1, -1):
        if is_vowel(phones[i]):
            return i
    return 0

def _collect_vowels(span: List[str]) -> List[str]:
    v = [p for p in span if is_vowel(p)]
    return v if v else (span[:1] if span else [])

def extract_rhyme_features(
    phones: List[str],
    syllables: List[List[str]],
    stress: List[int],
) -> dict:
    stressed_syl = _last_stress_idx(stress)

    # Startposition der betonten Silbe in phones[]
    offset = sum(len(syllables[k]) for k in range(stressed_syl))
    syl_phones = syllables[stressed_syl] if stressed_syl < len(syllables) else []

    # Ersten Vokal in der betonten Silbe finden
    rhyme_start = offset
    for j in range(len(syl_phones)):
        if is_vowel(syl_phones[j]):
            rhyme_start = offset + j
            break

    rhyme_span  = phones[rhyme_start:]
    vowel_spine = _collect_vowels(rhyme_span)
    tail        = phones[rhyme_start+1:]

    term_start         = _last_vowel_idx(phones)
    terminal_span      = phones[term_start:]
    terminal_vowel_spine = _collect_vowels(terminal_span)
    terminal_tail      = phones[term_start+1:]

    return {
        "rhyme_span": rhyme_span,
        "vowel_spine": vowel_spine,
        "tail": tail,
        "terminal_span": terminal_span,
        "terminal_vowel_spine": terminal_vowel_spine,
        "terminal_tail": terminal_tail,
    }

# ── Public API ────────────────────────────────────────────────────────────────

def parse_german_word(word: str) -> ParsedWord:
    phonetic   = graphemes_to_phonemes(word)
    syllables  = syllabify(phonetic)
    stress     = detect_stress(word, len(syllables))
    feats      = extract_rhyme_features(phonetic, syllables, stress)

    return ParsedWord(
        text=word,
        phonetic=phonetic,
        syllable_count=len(syllables),
        stress_pattern=stress,
        rhyme_span=feats["rhyme_span"],
        vowel_spine=feats["vowel_spine"],
        tail=feats["tail"],
        terminal_span=feats["terminal_span"],
        terminal_vowel_spine=feats["terminal_vowel_spine"],
        terminal_tail=feats["terminal_tail"],
    )
