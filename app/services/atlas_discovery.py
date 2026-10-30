"""Bounded discovery of source-backed phrase paths near pronunciation anchors.

This explores an FTS-selected corpus neighborhood, not the entire language.
Attested paths retain exact spans. Constructed paths retain both attested parts
and a separately attested joining bigram; they never inherit a whole-sentence
attribution. No database writes happen here.
"""
from __future__ import annotations

from collections import defaultdict
import json
import math
import re
import sqlite3
from time import monotonic
import unicodedata

from app.services.atlas_matching import candidate_families, compare_pronunciations
from app.services.atlas_phonetics import parse_ipa


_WORD = re.compile(r"[^\W_]+(?:[’'\-‐‑&][^\W_]+)*(?:\+{1,2}|#)?", re.UNICODE)
_VOCAB_CACHE: dict[tuple, tuple[float, list[dict]]] = {}


def _norm(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _compact(text):
    return "".join(char for char in _norm(text) if char.isalnum())


def _terminal_rank(anchor, candidate):
    """Prioritize useful FTS words; full-path scoring happens separately."""
    data = candidate["data"]
    nuclei = data.get("nuclei", [])
    if not nuclei:
        return -1
    a, b = anchor["nuclei"][-1], nuclei[-1]
    score = .5 if anchor["last_family"] == data.get("last_family") else .35
    if a.replace("ː", "") == b.replace("ː", ""):
        score += .12

    def coda(profile):
        syllable, nucleus = profile["syllables"][-1], profile["nuclei"][-1]
        try:
            return syllable[syllable.index(nucleus) + 1:]
        except ValueError:
            return []

    ac, bc = coda(anchor), coda(data)
    if ac == bc:
        score += .28
    elif ac and bc:
        shared = len(set(ac).intersection(bc)) / max(len(ac), len(bc))
        score += .22 * shared
        if ac[-1] in "mnŋlrʁɹ" and bc[-1] in "mnŋlrʁɹ":
            score += .06
    return score + min(.1, math.log1p(candidate["frequency"]) / 120)


def _vocabulary(conn, store, families, deadline):
    rows = []
    for family in sorted(families):
        if monotonic() >= deadline:
            break
        key = (str(store.path), family)
        cached = _VOCAB_CACHE.get(key)
        if cached and monotonic() - cached[0] < 120:
            rows.extend(cached[1])
            continue
        found = conn.execute("""select text,norm,ipa,phonetics,frequency from entries
            where language='de' and kind='word' and last_family=?
            and syllable_count between 1 and 4 and frequency>0
            order by frequency desc limit 1000""", (family,)).fetchall()
        unique = {}
        for item in found:
            item = dict(item)
            if not _WORD.fullmatch(item["text"]) or any(char.isdecimal() for char in item["text"]):
                continue
            if item["norm"] not in unique:
                item["data"] = json.loads(item.pop("phonetics"))
                unique[item["norm"]] = item
        value = list(unique.values())
        if len(_VOCAB_CACHE) >= 64:
            _VOCAB_CACHE.pop(next(iter(_VOCAB_CACHE)))
        _VOCAB_CACHE[key] = (monotonic(), value)
        rows.extend(value)
    return rows


def _word_profiles(conn, store, tokens, deadline):
    """Batch dictionary reads, choosing actual casing before normalization."""
    actual = defaultdict(set)
    for token in tokens:
        actual[_norm(token)].add(token)
    found = defaultdict(list)
    norms = list(actual)
    for start in range(0, len(norms), 350):
        if monotonic() >= deadline:
            break
        chunk = norms[start:start + 350]
        rows = conn.execute("""select text,norm,ipa,phonetics,frequency,source_id from entries
            where language='de' and norm in (""" + ",".join("?" for _ in chunk) + ")", chunk).fetchall()
        for row in rows:
            found[row["norm"]].append(dict(row))
    profiles = {}
    for norm, spellings in actual.items():
        for token in spellings:
            if monotonic() >= deadline:
                return profiles
            candidates = found.get(norm, [])
            if candidates:
                chosen = max(candidates, key=lambda row: (
                    row["text"] == token, row["source_id"] == "ipa-de", row["frequency"],
                ))
                data, ipa, frequency = json.loads(chosen["phonetics"]), chosen["ipa"], chosen["frequency"]
                evidence = "dictionary"
            else:
                data, ipa, _ = store.pronounce(token, "de", lexicon={})
                frequency, evidence = 0, "rule"
            profiles[token] = {"data": data, "ipa": ipa, "frequency": frequency, "evidence": evidence}
    return profiles


def _span(sentence, words, start, end, profiles):
    a, b = words[start].start(), words[end - 1].end()
    return {
        "text": sentence["text"][a:b], "source_id": sentence["source_id"],
        "source_ref": {
            **sentence["source_ref"], "context": sentence["text"],
            "char_start": a, "char_end": b, "start_word": start, "end_word": end,
        },
        "profiles": [profiles[word.group()] for word in words[start:end]],
        "first_word": _norm(words[start].group()), "last_word": _norm(words[end - 1].group()),
    }


def _pronunciation(profiles):
    ipa = "/" + " ".join(profile["ipa"].strip("/[] ") for profile in profiles) + "/"
    data = parse_ipa(ipa, "de")
    data["notes"] = list(dict.fromkeys([
        *data.get("notes", []), *(note for profile in profiles for note in profile["data"].get("notes", [])),
    ]))
    data["stress"] = [value for profile in profiles for value in profile["data"].get("stress", [])]
    return data, ipa


def _best_match(data, anchors, mode):
    best = None
    for anchor in anchors:
        relation = compare_pronunciations(anchor, data, mode)
        if relation and (best is None or relation["score"] > best["score"]):
            best = relation
    return best


def discover(store, anchors: list[dict], options: dict) -> list[dict]:
    """Return at most 600 useful phrase candidates from a bounded FTS search.

    Inputs accept either flattened parse_ipa anchors or ``{text, data}``.
    ``discovery_limit`` (default 480), ``discovery_sentence_limit`` (240), and
    ``discovery_seconds`` (4, at most 6) expose the work bounds. Returned source
    references document these bounds. A result is evidence from this explored
    neighborhood, not a claim that all matching corpus sentences were searched.
    """
    if not anchors or options.get("kind", "all") not in {"all", "phrase", "word"}:
        return []
    languages = options.get("languages", ["de", "en"])
    if languages and "de" not in languages:
        return []
    include_combinations = bool(options.get("include_combinations", False))
    origin = options.get("origin", "all")
    if origin == "constructed" and not include_combinations:
        return []
    mode = options.get("mode", "dirty")
    parsed = []
    for item in anchors:
        data = item.get("data", item)
        if data.get("nuclei") and data.get("syllable_count", len(data["nuclei"])):
            parsed.append({**data, "text": item.get("text", "")})
    if not parsed:
        return []
    excluded = {_compact(anchor["text"]) for anchor in parsed}
    low, high = max(1, options.get("min_syllables", 1)), min(64, options.get("max_syllables", 64))
    flex_bound = 0 if mode in {"strict", "balanced"} else min(2, max(0, options.get("syllable_flex", 2)))
    desired = set()
    for anchor in parsed:
        size = anchor.get("syllable_count", len(anchor["nuclei"]))
        flex = flex_bound if size >= 3 else 0
        desired.update(count for count in range(max(1, size - flex), size + flex + 1) if low <= count <= high)
    if not desired:
        return []
    limit = min(600, max(1, options.get("discovery_limit", 480)))
    sentence_limit = min(600, max(1, options.get("discovery_sentence_limit", 240)))
    seconds = min(6., max(.05, float(options.get("discovery_seconds", 4.))))
    deadline = monotonic() + seconds
    bounds = {"bounded": True, "sentence_limit": sentence_limit, "candidate_limit": limit,
              "seconds": seconds, "syllables": sorted(desired)}
    first_families = set().union(*(set(candidate_families(anchor["first_family"], mode)) for anchor in parsed))
    end_families = set().union(*(set(candidate_families(anchor["last_family"], mode)) for anchor in parsed))
    sentences, profiles = {}, {}
    try:
        with store.connect() as conn:
            # Even an unexpectedly common FTS token cannot run past the budget.
            conn.set_progress_handler(lambda: int(monotonic() >= deadline), 2000)
            vocabulary = _vocabulary(conn, store, end_families, deadline)
            terms, seen_terms = [], set()
            for anchor in parsed:
                words = list(_WORD.finditer(anchor["text"]))
                if words:
                    term = _norm(words[-1].group())
                    if term not in seen_terms:
                        terms.append(term); seen_terms.add(term)
            ranked = sorted(vocabulary, key=lambda row: max(_terminal_rank(anchor, row) for anchor in parsed), reverse=True)
            for row in ranked:
                term = row["norm"]
                if term not in seen_terms:
                    terms.append(term); seen_terms.add(term)
                if len(terms) >= 24:
                    break
            per_term = max(8, math.ceil(sentence_limit / max(1, len(terms))))
            for term in terms[:24]:
                if len(sentences) >= sentence_limit or monotonic() >= deadline:
                    break
                query = '"' + term.replace('"', '""') + '"'
                rows = conn.execute("""select c.* from corpus_fts join corpus_sentences c
                    on c.id=corpus_fts.rowid where corpus_fts match ?
                    and length(c.text) between ? and 6000 limit ?""",
                    (query, max(1, min(desired) * 2), min(per_term, sentence_limit - len(sentences)))).fetchall()
                for row in rows:
                    item = dict(row)
                    item["source_ref"] = json.loads(item["source_ref"])
                    sentences[item["id"]] = item
            tokens = {word.group() for sentence in sentences.values() for word in _WORD.finditer(sentence["text"])}
            profiles = _word_profiles(conn, store, tokens, deadline)
            conn.set_progress_handler(None, 0)
    except sqlite3.OperationalError as error:
        if "interrupted" not in str(error).lower():
            raise
        return []

    scored, left_parts, right_parts, bigrams = {}, defaultdict(list), defaultdict(list), {}
    fragment_count = 0
    max_size = max(desired)
    kind = options.get("kind", "all")
    for sentence in sentences.values():
        if monotonic() >= deadline:
            break
        words = list(_WORD.finditer(sentence["text"]))
        for index in range(len(words) - 1):
            key = (_norm(words[index].group()), _norm(words[index + 1].group()))
            if key not in bigrams:
                a, b = words[index].start(), words[index + 1].end()
                bigrams[key] = {"text": sentence["text"][a:b], "source_id": sentence["source_id"],
                    "source_ref": {**sentence["source_ref"], "context": sentence["text"], "char_start": a, "char_end": b}}
        for start in range(len(words)):
            total = 0
            for end in range(start + 1, len(words) + 1):
                if monotonic() >= deadline:
                    break
                profile = profiles.get(words[end - 1].group())
                if not profile or not profile["data"].get("nuclei"):
                    break
                total += profile["data"].get("syllable_count", len(profile["data"]["nuclei"]))
                if total > max_size:
                    break
                first = profiles[words[start].group()]["data"].get("first_family")
                last = profile["data"].get("last_family")
                useful_start, useful_end = first in first_families, last in end_families
                if not useful_start and not useful_end:
                    continue
                span = _span(sentence, words, start, end, profiles)
                span["syllable_count"] = total
                if include_combinations and origin != "attested" and total < max_size and fragment_count < 2400:
                    if useful_start and len(left_parts[span["last_word"]]) < 12:
                        left_parts[span["last_word"]].append(span); fragment_count += 1
                    if useful_end and len(right_parts[span["first_word"]]) < 12:
                        right_parts[span["first_word"]].append(span); fragment_count += 1
                if origin == "constructed" or total not in desired or not useful_start or not useful_end:
                    continue
                row_kind = "word" if end - start == 1 else "phrase"
                if kind != "all" and kind != row_kind:
                    continue
                norm = _compact(span["text"])
                if norm in excluded or norm in scored:
                    continue
                data, ipa = _pronunciation(span["profiles"])
                relation = _best_match(data, parsed, mode)
                if relation:
                    ref = {**span["source_ref"], "discovery": bounds,
                           "pronunciation": {"rule_words": [word.group() for word in words[start:end]
                               if profiles[word.group()]["evidence"] == "rule"]}}
                    scored[norm] = (relation["score"], {
                        "text": span["text"], "ipa": ipa, "data": data, "language": "de",
                        "source_id": span["source_id"], "origin": "attested_phrase", "kind": row_kind,
                        "source_ref": ref, "frequency": min(item["frequency"] for item in span["profiles"]),
                    })
        if len(scored) >= limit * 3:
            break

    if include_combinations and origin != "attested" and kind != "word" and monotonic() < deadline:
        joins = defaultdict(list)
        for left, right in bigrams:
            joins[left].append(right)
        contexts = [_norm(sentence["text"]) for sentence in sentences.values()]
        attempts, constructed = 0, 0
        constructed_limit = min(160, limit // 2 + 1)
        for last_word, parts in left_parts.items():
            if monotonic() >= deadline or constructed >= constructed_limit or attempts >= 4000:
                break
            for next_word in joins.get(last_word, []):
                for left in parts:
                    for right in right_parts.get(next_word, []):
                        if attempts >= 4000 or constructed >= constructed_limit or monotonic() >= deadline:
                            break
                        attempts += 1
                        if left["syllable_count"] + right["syllable_count"] not in desired:
                            continue
                        text = left["text"] + " " + right["text"]
                        norm = _compact(text)
                        if norm in excluded or norm in scored or any(_norm(text) in context for context in contexts):
                            continue
                        combined = left["profiles"] + right["profiles"]
                        data, ipa = _pronunciation(combined)
                        relation = _best_match(data, parsed, mode)
                        if relation:
                            scored[norm] = (relation["score"] - .005, {
                                "text": text, "ipa": ipa, "data": data, "language": "de", "kind": "phrase",
                                "source_id": "atlas-combinations", "origin": "constructed",
                                "frequency": min(item["frequency"] for item in combined),
                                "source_ref": {
                                    "parts": [{key: part[key] for key in ("text", "source_id", "source_ref")} for part in (left, right)],
                                    "join_evidence": bigrams[(last_word, next_word)],
                                    "construction": "Zwei belegte Textspannen kombiniert; nur ihr Wortübergang ist zusätzlich belegt.",
                                    "discovery": bounds,
                                },
                            })
                            constructed += 1
                    if attempts >= 4000 or constructed >= constructed_limit:
                        break
                if attempts >= 4000 or constructed >= constructed_limit:
                    break
    return [row for _, row in sorted(scored.values(), key=lambda item: (-item[0], -item[1]["frequency"], len(item[1]["text"])))[:limit]]
