"""Streaming readers for public atlas sources, retaining evidence and spelling.

Readers do not download, store, rank, or limit a corpus. In particular, an
unfamiliar spelling, name, loanword, or annotation is not a reason to drop an
entry. Licensing metadata belongs to the source manifest and passes through
``load_manifest`` unchanged.
"""
from __future__ import annotations

import bz2
import gzip
import json
import lzma
from pathlib import Path
import re
from typing import Iterator, TextIO

from app.services.atlas_phonetics import split_ipa_variants


class CorpusFormatError(ValueError):
    """A source row could not be read without losing its meaning."""


def _open_text(path: str | Path) -> TextIO:
    path = Path(path)
    opener = {".bz2": bz2.open, ".gz": gzip.open, ".xz": lzma.open}.get(path.suffix, open)
    return opener(path, "rt", encoding="utf-8-sig", newline="")


def _error(path: str | Path, line_no: int, explanation: str) -> CorpusFormatError:
    # The diagnostic identifies the location without copying an entire source
    # sentence into logs. The reader never silently truncates or discards it.
    return CorpusFormatError(f"{path}:{line_no}: {explanation}")


def _kind(text: str) -> str:
    return "phrase" if any(char.isspace() for char in text) else "word"


def load_manifest(path: str | Path) -> dict | list:
    """Read a JSON manifest without changing attribution or license fields."""
    with _open_text(path) as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, (dict, list)):
        raise CorpusFormatError(f"{path}: manifest must contain a JSON object or array")
    return manifest


def iter_ipa_entries(
    path: str | Path, language: str, source_id: str,
) -> Iterator[dict]:
    """Yield every spelling and each attested pronunciation in an IPA TSV.

    ``text`` retains the spelling exactly; ``original_entry`` retains the whole
    row except its line ending. Multiple IPA alternatives are separate entries,
    never concatenated into an invented pronunciation.
    """
    with _open_text(path) as handle:
        for line_no, line in enumerate(handle, 1):
            original = line.rstrip("\r\n")
            if not original.strip():
                continue
            fields = original.split("\t")
            if len(fields) != 2 or not fields[0].strip() or not fields[1].strip():
                raise _error(path, line_no, "expected a nonempty spelling and IPA field separated by one tab")
            text, ipa_field = fields
            variants = split_ipa_variants(ipa_field)
            if not variants:
                raise _error(path, line_no, "IPA field contains no pronunciation")
            for variant_index, ipa in enumerate(variants):
                yield {
                    "text": text, "ipa": ipa, "language": language,
                    "source_id": source_id, "origin": "dictionary", "kind": _kind(text),
                    "source_ref": {
                        "line_no": line_no, "original_entry": original,
                        "variant_index": variant_index,
                    },
                }


_PARENTHETICAL = re.compile(r"\(([^()]*)\)")
# These are metadata markers, not optional lexical components such as '(nicht)',
# '(sich)', or '(jemandem)'. Unknown markers remain visible in the source text.
_REGISTER_MARKERS = frozenset({
    "ugs.", "fachspr.", "fig.", "geh.", "veraltet", "veraltend", "derb",
    "schweiz.", "österr.", "engl.", "lat.", "franz.", "griechisch",
    "ital.", "span.", "niederl.", "japanisch", "russ.", "arabisch",
    "Hauptform", "Nebenform", "Abkürzung", "Kurzform", "variabel",
    "abwertend", "aufwertend", "regional", "salopp", "Spruch", "scherzhaft",
    "ironisch", "ironisierend", "literarisch", "Kindersprache", "amtlich",
    "Jargon", "norddeutsch", "süddeutsch", "westdeutsch", "ostdeutsch",
    "selten", "weibl.", "männl.", "floskelhaft", "bildungssprachlich",
    "botanisch", "technisch", "Amtsdeutsch", "historisch", "auch figurativ",
    "euphemistisch", "verhüllend", "pejorativ", "vulgär", "umgangssprachlich",
})


def _thesaurus_term(raw: str) -> tuple[str, list[str], list[str]]:
    registers, unknown = [], []

    def replace(match: re.Match) -> str:
        content = match.group(1)
        markers = [part.strip() for part in content.split(",")]
        if markers and all(marker in _REGISTER_MARKERS for marker in markers):
            registers.extend(markers)
            return ""
        unknown.append(content)
        return match.group(0)

    cleaned = _PARENTHETICAL.sub(replace, raw)
    # Whitespace left behind by removed register labels is not lexical data.
    # The exact pre-cleaning token remains available in original_entry.
    return re.sub(r"[ \t]+", " ", cleaned).strip(), registers, unknown


def iter_thesaurus_entries(path: str | Path, source_id: str) -> Iterator[dict]:
    """Yield every OpenThesaurus term and its other terms in the same group.

    Recognized register labels move to metadata. Lexical parentheses and
    unknown qualifiers stay in ``text`` and are recorded separately, so a
    parser update cannot silently turn '(nicht) koscher' into 'koscher'.
    """
    with _open_text(path) as handle:
        for line_no, line in enumerate(handle, 1):
            original = line.rstrip("\r\n")
            if not original.strip() or original.lstrip().startswith("#"):
                continue
            raw_terms = original.split(";")
            terms = [_thesaurus_term(term) for term in raw_terms]
            if any(not text for text, _, _ in terms):
                raise _error(path, line_no, "thesaurus group contains an empty term")
            texts = [term[0] for term in terms]
            for index, (text, registers, unknown) in enumerate(terms):
                source_ref = {
                    "group": line_no, "line_no": line_no, "register": registers,
                    "original_entry": raw_terms[index],
                }
                if unknown:
                    source_ref["unclassified_qualifiers"] = unknown
                yield {
                    "text": text, "ipa": None, "language": "de", "source_id": source_id,
                    "origin": "dictionary_phrase", "kind": _kind(text),
                    "source_ref": source_ref,
                    "relations": [other for at, other in enumerate(texts) if at != index],
                }


_LANGUAGES = {"deu": "de", "eng": "en"}


def _nullable(value: str) -> str | None:
    return None if value == r"\N" else value


def iter_tatoeba_entries(path: str | Path, source_id: str) -> Iterator[dict]:
    """Read the six-column Tatoeba detailed export, with author attribution.

    Whole sentences have no length limit. This reader preserves their exact
    text, including punctuation and whitespace, for later attested windows.
    """
    with _open_text(path) as handle:
        for line_no, line in enumerate(handle, 1):
            original = line.rstrip("\r\n")
            if not original.strip():
                continue
            fields = original.split("\t")
            if len(fields) != 6:
                raise _error(path, line_no, "expected six Tatoeba detailed TSV columns")
            sentence_id, language, text, author, added, modified = fields
            if not sentence_id.isdecimal() or not language or not text.strip():
                raise _error(path, line_no, "expected sentence ID, language, and nonempty sentence")
            identifier = int(sentence_id)
            yield {
                "text": text, "ipa": None,
                "language": _LANGUAGES.get(language, language), "source_id": source_id,
                "origin": "attested_phrase", "kind": "phrase",
                "source_ref": {
                    "sentence_id": identifier, "author": _nullable(author),
                    "url": f"https://tatoeba.org/en/sentences/show/{identifier}",
                    "date_added": _nullable(added), "date_modified": _nullable(modified),
                    "line_no": line_no, "language_code": language,
                },
            }


# Include Unicode letters/digits, intraword apostrophes and hyphens, and common
# lexical spellings such as R&B, C++, and C#. Offsets refer to source codepoints.
_WORD = re.compile(r"[^\W_]+(?:[’'\-‐‑&][^\W_]+)*(?:\+{1,2}|#)?", re.UNICODE)


def iter_sentence_windows(
    row: dict, min_words: int = 2, max_words: int | None = 6,
) -> Iterator[dict]:
    """Yield contiguous attested word spans, retaining exact source substrings.

    Offsets are zero-based, with exclusive ends. ``max_words=None`` expands
    through the entire sentence; a finite bound is explicit caller policy,
    not a hidden corpus cap. No cross-source word combinations are invented.
    """
    if isinstance(min_words, bool) or not isinstance(min_words, int) or min_words < 1:
        raise ValueError("min_words must be a positive integer")
    if max_words is not None and (
        isinstance(max_words, bool) or not isinstance(max_words, int) or max_words < min_words
    ):
        raise ValueError("max_words must be None or an integer at least min_words")
    text = row["text"]
    words = list(_WORD.finditer(text))
    longest = len(words) if max_words is None else min(max_words, len(words))
    for width in range(min_words, longest + 1):
        for start in range(len(words) - width + 1):
            end = start + width
            char_start, char_end = words[start].start(), words[end - 1].end()
            source_ref = dict(row.get("source_ref", {}))
            source_ref.update({
                "context": text, "char_start": char_start, "char_end": char_end,
                "start_word": start, "end_word": end,
            })
            yield {
                **row, "text": text[char_start:char_end], "ipa": None,
                "origin": "attested_phrase", "kind": "word" if width == 1 else "phrase",
                "source_ref": source_ref,
            }
