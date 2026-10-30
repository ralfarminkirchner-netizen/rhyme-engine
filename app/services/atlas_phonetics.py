"""Fast IPA decoding for the atlas' attested pronunciation dictionaries.

This is an index representation, not a replacement for the source IPA. It
retains the exact input and reports approximations and unknown symbols. Sound
families deliberately group related vowels; equality of those families is
never a claim of an exact rhyme or an identical pronunciation.

Symbol/diacritic basis: International Phonetic Association, official chart:
https://www.internationalphoneticassociation.org/IPAcharts/IPA_charts_EI/IPA_charts_EI.html
"""
from __future__ import annotations

from functools import lru_cache
import re
import unicodedata


# Explicit IPA diphthongs are one nucleus. The optional non-syllabic mark is
# common in the German Wiktionary-derived data; English uses bare sequences.
_TOKEN = re.compile(
    r"(?:[^\W\d_][͜͡][^\W\d_][\u0300-\u036fːˑʲʰˠʶ]*|tʃ|dʒ|pf|"
    r"(?:aɪ|ai|ɑɪ|aʊ|au|ɑʊ|ɔɪ|ɔʏ|oi|ɔy|eɪ|ei|oʊ|ou)[̯̑̆ːˑ]*|"
    r"[^\W\d_][\u0300-\u036fːˑʲʰˠʶ]*|.)",
    re.UNICODE,
)
_SLASH_VARIANT = re.compile(r"/[^/]+/")
_BRACKET_VARIANT = re.compile(r"\[[^\]]+\]")
_COMBINING = re.compile(r"[\u0300-\u036fːˑʲʰˠʶ]")
_VOWELS = frozenset("aeiouyɑɒæɛɜɞɘəɐɤɨɪʉʊʌɔœøɶɯɚɝʏ")
_CONSONANTS = frozenset("pbtdʈɖcɟkgɡqɢʔmɱnɳɲŋɴʙrʀɾɽɸβfvθðszʃʒʂʐɕʑçʝxɣχʁħʕhɦɬɮʋɹɻjɰlwɥʍʎʟɺɓɗʄɠʛǀǁǃǂ")
_SYLLABIC = frozenset({"n", "m", "l", "r", "ɹ", "ŋ", "ɱ"})
_DIPHTHONG_FAMILY = {
    "aɪ": "ai", "ai": "ai", "ɑɪ": "ai", "aʊ": "au", "au": "au", "ɑʊ": "au",
    "ɔɪ": "oi", "ɔʏ": "oi", "oi": "oi", "ɔy": "oi",
    "eɪ": "ei", "ei": "ei", "oʊ": "ou", "ou": "ou",
}
_FAMILY = {
    "a": "a", "ɑ": "a", "ɒ": "o", "æ": "a", "ɶ": "oe",
    "e": "e", "ɛ": "e", "ɜ": "schwa", "ɞ": "schwa", "ɘ": "schwa",
    "i": "i", "ɪ": "i", "ɨ": "i", "ʉ": "u", "ɯ": "u",
    "o": "o", "ɔ": "o", "u": "u", "ʊ": "u", "ʌ": "a", "ɤ": "o",
    "y": "ue", "ʏ": "ue", "ø": "oe", "œ": "oe",
    "ə": "schwa", "ɐ": "schwa", "ɚ": "schwa", "ɝ": "schwa",
}
_DIPHTHONG_CANONICAL = {
    "ai": "aɪ", "ɑɪ": "aɪ", "au": "aʊ", "ɑʊ": "aʊ",
    "ɔɪ": "ɔʏ", "oi": "ɔʏ", "ɔy": "ɔʏ", "ei": "eɪ", "ou": "oʊ",
}
_NORMAL_CONSONANT = {"ɡ": "g", "ɫ": "l"}
# These are conventional permissible onset clusters, not a word exception list.
# A glottal stop or an explicit IPA word/syllable/stress boundary takes priority.
_ONSETS = frozenset({
    (first, second)
    for first in ("p", "b", "t", "d", "k", "g", "f", "v", "ʃ", "s", "θ")
    for second in ("l", "r", "ʁ", "ɹ", "j", "w")
}) | frozenset({
    ("ʃ", "p"), ("ʃ", "t"), ("ʃ", "n"), ("ʃ", "m"), ("s", "p"),
    ("s", "t"), ("s", "k"), ("t͡s", "j"), ("t͡s", "v"),
    ("s", "t", "r"), ("s", "p", "r"), ("s", "k", "r"),
    ("ʃ", "t", "ʁ"), ("ʃ", "p", "ʁ"), ("s", "t", "ɹ"),
    ("s", "p", "ɹ"), ("s", "k", "ɹ"),
})


def split_ipa_variants(field: str) -> list[str]:
    """Split a dictionary pronunciation field, retaining each exact IPA form."""
    variants = _SLASH_VARIANT.findall(field) or _BRACKET_VARIANT.findall(field)
    if not variants:
        variants = [item.strip() for item in field.split(",") if item.strip()]
    return list(dict.fromkeys(variants))


@lru_cache(maxsize=4096)
def _phone(token: str) -> tuple[str, bool, str, str | None]:
    """Canonical symbol, nucleus flag, coarse family, optional operation note."""
    base = _COMBINING.sub("", token)
    if base in _DIPHTHONG_FAMILY:
        canonical = _DIPHTHONG_CANONICAL.get(base, base) + ("ː" if "ː" in token else ("ˑ" if "ˑ" in token else ""))
        return canonical, True, _DIPHTHONG_FAMILY[base], (
            f"Diphthongschreibung {token} im Klangindex als {canonical} vereinheitlicht."
            if token != canonical else None
        )
    if base in {"ts", "tʃ", "dʒ", "pf"}:
        canonical = {"ts": "t͡s", "tʃ": "t͡ʃ", "dʒ": "d͡ʒ", "pf": "pf"}[base]
        return canonical, False, "", None
    if len(base) == 2 and ("͡" in token or "͜" in token) and all(symbol in _CONSONANTS for symbol in base):
        return base[0] + "͡" + base[1], False, "", None
    if len(base) == 1 and base in _VOWELS:
        if "̯" in token or "̑" in token:
            # Keeping the non-syllabic token avoids creating a fictitious
            # extra syllable in /ɐ̯/ or in a loanword's /i̯/ glide.
            return base + "̯", False, "", (
                f"Unsilbischer Vokal {token} bleibt als Gleitlaut ohne eigenen Silbenkern erhalten."
            )
        length = "ː" if "ː" in token else ("ˑ" if "ˑ" in token else "")
        nasal = "̃" if "̃" in token else ""
        canonical = base + nasal + length
        detail = _COMBINING.sub("", token) != token and canonical != token
        return canonical, True, _FAMILY[base], (
            f"Detaildiakritika von {token} für den Klangindex vereinfacht; Roh-IPA bleibt erhalten."
            if detail else None
        )
    if len(base) == 1 and (base in _CONSONANTS or base == "ɫ"):
        canonical = _NORMAL_CONSONANT.get(base, base)
        if ("̩" in token or "̍" in token) and base in _SYLLABIC:
            return canonical + "̩", True, "schwa", (
                "Silbischer Sonorant im groben Klangindex bei Reduktionssilben eingeordnet."
            )
        return canonical, False, "", (
            f"IPA-Variante {token} im Klangindex als {canonical} vereinheitlicht."
            if token != canonical else None
        )
    return token, False, "", None


def nucleus_family(symbol: str) -> str:
    """Return the atlas' coarse family for a nucleus or an empty string."""
    return _phone(unicodedata.normalize("NFD", symbol))[2]


def _chunk_syllables(
    phones: list[str], nuclei: list[int], hard: set[int],
) -> list[tuple[int, int]]:
    if not nuclei:
        return [(0, len(phones))] if phones else []
    boundaries = [0]
    for previous, following in zip(nuclei, nuclei[1:]):
        explicit = [index for index in hard if previous < index <= following]
        if explicit:
            boundary = max(explicit)
        else:
            cluster = phones[previous + 1:following]
            if "ʔ" in cluster:
                boundary = previous + 1 + cluster.index("ʔ")
            else:
                onset = min(1, len(cluster))
                for size in range(min(3, len(cluster)), 1, -1):
                    if tuple(cluster[-size:]) in _ONSETS:
                        onset = size
                        break
                boundary = following - onset
        boundaries.append(boundary)
    boundaries.append(len(phones))
    return list(zip(boundaries, boundaries[1:]))


@lru_cache(maxsize=32768)
def _parse_cached(raw: str, language: str) -> tuple:
    body = raw.strip()
    if (body.startswith("/") and body.endswith("/")) or (body.startswith("[") and body.endswith("]")):
        body = body[1:-1]
    body = unicodedata.normalize("NFD", body)
    syllables, stresses, nucleus_symbols, families = [], [], [], []
    unknown, notes = set(), set()
    word_boundaries = [0]
    phones, nuclei, syllable_hard, anchors = [], [], set(), []

    def flush() -> None:
        if not phones:
            return
        if not nuclei:
            notes.add("Mindestens ein Quellausschnitt besitzt keinen erkannten Silbenkern und bleibt entsprechend unbestimmt.")
        ranges = _chunk_syllables(phones, nuclei, syllable_hard)
        chunk_stress = [0] * len(ranges)
        for position, level in anchors:
            next_nucleus = next((index for index in nuclei if index >= position), None)
            if next_nucleus is not None:
                for index, (start, end) in enumerate(ranges):
                    if start <= next_nucleus < end:
                        if chunk_stress[index] != 1:
                            chunk_stress[index] = level
                        break
        for index, (start, end) in enumerate(ranges):
            syllables.append(tuple(phones[start:end]))
            stresses.append(chunk_stress[index])
            in_range = [at for at in nuclei if start <= at < end]
            if in_range:
                symbol = phones[in_range[0]]
                nucleus_symbols.append(symbol)
                families.append(nucleus_family(symbol))
            else:
                nucleus_symbols.append("")
                families.append("")
        if word_boundaries[-1] != len(syllables):
            word_boundaries.append(len(syllables))
        phones.clear()
        nuclei.clear()
        syllable_hard.clear()
        anchors.clear()

    for match in _TOKEN.finditer(body):
        token = match.group()
        if token in {"‿", "⁀"}:
            notes.add("Verbindungszeichen der Quelle ohne künstliche Trennung der Lautfolge indexiert; Roh-IPA bleibt erhalten.")
            continue
        if token.isspace() or token in {"|", "‖", ",", ";", ":", "!", "?"}:
            if token in {",", ";", ":", "!", "?"}:
                notes.add("Quellinterpunktion als Phrasengrenze indexiert; Roh-IPA bleibt erhalten.")
            flush()
            continue
        if token in {"ˈ", "ˌ"}:
            anchors.append((len(phones), 1 if token == "ˈ" else 2))
            syllable_hard.add(len(phones))
            continue
        if token == ".":
            syllable_hard.add(len(phones))
            continue
        if token in {"↗", "↘"}:
            notes.add("Intonationspfeile verbleiben im Roh-IPA und gehen nicht in den Lautindex ein.")
            continue
        symbol, is_nucleus, family, note = _phone(token)
        if note:
            notes.add(note)
        base = _COMBINING.sub("", token)
        known_tied = len(base) == 2 and ("͡" in token or "͜" in token) and all(symbol in _CONSONANTS for symbol in base)
        if not is_nucleus and not family and base not in _CONSONANTS and base not in {"ɫ", "ts", "tʃ", "dʒ", "pf"} and not known_tied:
            # Non-syllabic vowel glides are recognized even though they are
            # neither ordinary consonants nor nuclei.
            if not (base in _VOWELS and ("̯" in token or "̑" in token)):
                unknown.add(token)
        if is_nucleus:
            nuclei.append(len(phones))
        phones.append(symbol)
    flush()
    if not any(stresses) and syllables:
        notes.add("Die Quelle markiert hier keinen Wortakzent; es wurde keiner erfunden.")
    return (
        tuple(syllables), tuple(stresses), tuple(nucleus_symbols), tuple(families),
        tuple(sorted(unknown)), tuple(sorted(notes)), tuple(word_boundaries),
    )


def parse_ipa(ipa: str, language: str = "de") -> dict:
    """Decode IPA without losing provenance or inventing a heard performance.

    ``stress`` uses 0=unmarked, 1=primary, 2=secondary. ``word_boundaries``
    contains syllable offsets including 0 and the end for gaps/groups that
    are explicit in the IPA (not a guessed alignment to a separate spelling).
    """
    syllables, stress, nuclei, families, unknown, notes, boundaries = _parse_cached(ipa, language)
    return {
        "syllables": [list(syllable) for syllable in syllables],
        "stress": list(stress), "nuclei": list(nuclei), "families": list(families),
        "first_family": families[0] if families else "",
        "last_family": families[-1] if families else "",
        "signature": "-".join(families), "raw_ipa": ipa,
        "unknown": list(unknown), "notes": list(notes),
        "syllable_count": len(syllables), "word_boundaries": list(boundaries),
        "parser_version": "atlas-ipa/1",
    }
