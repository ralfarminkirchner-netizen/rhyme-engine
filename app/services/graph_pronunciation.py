"""Conservative offline repairs around the legacy graph G2P.

The word, its spelling and every source occurrence remain untouched. Returned
rules describe hypotheses, not a recording-derived transcription. This module
does not register phrase-specific rhyme partners or modify the legacy parser.

Primary pronunciation references for the repaired classes:
https://www.duden.de/rechtschreibung/Patient (pa-tsi̯ɛnt, not pa-tiːnt)
https://www.duden.de/rechtschreibung/Klient (hiatus kli-ɛnt)
https://www.duden.de/rechtschreibung/Orient (standard oː-ri-ɛnt)
https://www.duden.de/hilfe/aussprache (Schwa, vowel quantity, non-syllabic i)
https://shop.duden.de/media/7e/3d/ca/1719879346/Leseprobe_9783411040636_Das_Fremdw%C3%B6rterbuch.pdf
(C contexts and ti before a vowel in loans). /j/ approximates non-syllabic
/i̯/ within the existing inventory; this approximation is explicitly reported.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from app.services.parser import (
    detect_stress, graphemes_to_phonemes, is_vowel, syllabify,
)


LONG_OPEN_VOWELS = {"a": "aː", "ɛ": "eː", "ɪ": "iː", "ɔ": "oː", "ʊ": "uː", "œ": "øː", "ʏ": "yː"}
ACCENTS = {"é": "eː", "è": "ɛ", "ê": "ɛ", "á": "aː", "à": "a", "í": "iː", "ó": "oː", "ú": "uː"}


def _standalone_c_values(word: str) -> List[str]:
    """Map only C characters that the legacy scanner does not consume as ch/ck."""
    values, index = [], 0
    while index < len(word):
        if word.startswith(("ch", "ck"), index):
            index += 2
            continue
        if word[index] == "c":
            following = word[index + 1:index + 2]
            values.append("t͡s" if following and following in "eiäöüy" else "k")
        index += 1
    return values


def _replace_sequence(phones: List[str], old: List[str], new: List[str]) -> Tuple[List[str], int | None]:
    for index in range(len(phones) - len(old), -1, -1):
        if phones[index:index + len(old)] == old:
            return phones[:index] + new + phones[index + len(old):], index
    return phones, None


def _loan_ie(word: str, phones: List[str], notes: List[str]) -> Tuple[List[str], int | None]:
    # German dien- inflections have genuine /iː/: do not reinterpret diente,
    # bedient or verdienten as Romance -ient words merely because of spelling.
    if re.fullmatch(r"(?:be|ver)?dien(?:t|te|ten|test|tet)", word):
        return phones, None
    match = re.search(r"ie(?=n[tz](?:en|in|innen|e|er|es|em)?$)", word)
    if not match:
        return phones, None
    # The legacy scanner collapses written ie to /iː/. This loses the final
    # open e nucleus in the entire -ient/-ienz class.
    old_end = ["iː", "n", "t͡s" if word[match.end() + 1] == "z" else "t"]
    has_hiatus = word.startswith(("klient", "orient"))
    replacement = ["iː", "ɛ"] if has_hiatus else ["j", "ɛ"]
    changed, index = _replace_sequence(phones, old_end, replacement + old_end[1:])
    if index is None:
        return phones, None
    if not has_hiatus and index and changed[index - 1] == "t":
        changed[index - 1] = "t͡s"
    notes.append(
        "Lehnwortfolge -ient/-ienz: e bleibt als /ɛ/-Kern erhalten; "
        + ("lexikalisch belegter Hiatus wird getrennt gesprochen." if has_hiatus else "unsilbisches i wird im bestehenden Lautinventar als /j/ angenähert.")
    )
    # Orient has lexical initial stress; Klient and the productive suffix
    # class stress their /ɛ/ nucleus, including inflected forms.
    return changed, (0 if word.startswith("orient") else index + 1)


def pronounce_graph_word(word: str) -> Tuple[List[str], List[int], List[str]]:
    """Return phones, pre-r-grouping stress and explicit rule notes.

    The caller can retain its existing r-offglide grouping. Stress has one
    entry per legacy ``syllabify(phones)`` syllable before that grouping.
    No network access, model loading or global parser mutation occurs.
    """
    written = word.strip().lower()
    phones = list(graphemes_to_phonemes(written))
    notes: List[str] = []

    c_values = iter(_standalone_c_values(written))
    if "c" in phones:
        phones = [next(c_values, "k") if phone == "c" else phone for phone in phones]
        notes.append("Einfaches c nach Lehnwortkontext als /k/ oder /t͡s/ gelesen; ch und ck bleiben unberührt.")
    if any(phone in ACCENTS for phone in phones):
        phones = [ACCENTS.get(phone, phone) for phone in phones]
        notes.append("Akzentmarkierte Vokalbuchstaben ins vorhandene IPA-Inventar übertragen.")

    phones, lexical_anchor = _loan_ie(written, phones, notes)

    # German consonant double letters normally mark preceding vowel quantity,
    # not two independent consonant segments. Preserve the short vowel and use
    # one consonant, instead of making -ell artificially longer than -elt.
    deduplicated = []
    for phone in phones:
        if deduplicated and phone == deduplicated[-1] and not is_vowel(phone):
            continue
        deduplicated.append(phone)
    if deduplicated != phones:
        notes.append("Doppelte Konsonantenbuchstaben als einzelnen Laut gelesen; kurze Vokalqualität bleibt erhalten.")
        # The suffix anchor is recomputed below from its /ɛ/ nucleus, because
        # deduplication can move its absolute phone position.
        if lexical_anchor is not None and not written.startswith("orient"):
            lexical_anchor = max(i for i, phone in enumerate(deduplicated) if phone == "ɛ")
        phones = deduplicated

    syllables = syllabify(phones)
    pattern = list(detect_stress(written, len(syllables)))
    pattern = (pattern + [0] * len(syllables))[:len(syllables)]
    if len(syllables) > 1 and written[-1:] in {"é", "á", "í", "ó", "ú"}:
        pattern = [0] * (len(syllables) - 1) + [1]
        notes.append("Geschriebener finaler Akut als Hinweis auf betonten Vollvokal verwendet.")
    if lexical_anchor is not None:
        pattern = [0] * len(syllables)
        consumed = 0
        for index, syllable in enumerate(syllables):
            if consumed <= lexical_anchor < consumed + len(syllable):
                pattern[index] = 1
                break
            consumed += len(syllable)

    # Unaccented inflectional e after a stem-final d/t: bad-et, red-est,
    # wart-et, arbeit-et. This does not reinterpret Paket/Filet as inflections.
    if re.search(r"[dt]e(?:t|st)$", written) and len(syllables) > 1:
        flat_index = sum(len(syllable) for syllable in syllables[:-1])
        for index in range(flat_index, len(phones)):
            if phones[index] == "ɛ":
                phones[index] = "ə"
                pattern[-1] = 0
                if not any(pattern):
                    pattern[0] = 1
                notes.append("Flexions-e nach d/t als unbetontes Schwa gelesen.")
                break

    syllables = syllabify(phones)
    # An ordinary final written e yielding /ə/ is not a primary stress anchor.
    # This specifically removes the overly broad legacy -age suffix rule from
    # native forms such as Frage, Tage, Klage; no heard stress is claimed.
    if len(syllables) > 1 and pattern[-1] and any(phone == "ə" for phone in syllables[-1]) and written.endswith("e"):
        pattern[-1] = 0
        if not any(pattern):
            pattern[0] = 1
        notes.append("Finales Schwa nicht als Hauptakzent behandelt; gewöhnliche Wortbetonung bleibt eine Heuristik.")

    # The transparent open-syllable case improves native stems such as ba-den,
    # Fra-ge and Ha-se. Do not lengthen a closed syllable (Tasse, Kante, Kasten)
    # or unaccented vowel merely to make a rhyme. This is not a full lexicon.
    changed_length = False
    # The old syllabifier sometimes moves an entire cluster to the following
    # onset; spelling still prevents a false long vowel before ss/ck/st/nt.
    written_closed = bool(re.search(r"[aeiouäöüy][bcdfghjklmnpqrstvwxz]{2,}[aeiouäöüy]", written))
    offset = 0
    for syllable_index, syllable in enumerate(syllables):
        if not written_closed and len(syllables) > 1 and pattern[syllable_index] and syllable and syllable[-1] in LONG_OPEN_VOWELS:
            phone_index = offset + len(syllable) - 1
            phones[phone_index] = LONG_OPEN_VOWELS[syllable[-1]]
            changed_length = True
        offset += len(syllable)
    if changed_length:
        notes.append("Betonter Vokal in offener Silbe heuristisch lang gelesen.")

    return phones, pattern, notes
