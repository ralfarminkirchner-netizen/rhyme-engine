"""Bounded phrase-rhyme proposals over exact source occurrences.

This service deliberately does not infer rhythm, semantic fitness, or accepted
pronunciations. Similarities are rule-based ranking aids, not probabilities.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import re
from math import ceil, sqrt
from typing import Any, Iterator

from app.schemas.rhyme_graph import (
    GraphBuildRequest, GraphEdge, GraphLine, GraphNode, GraphProfile,
    GraphResponse, GraphWord, SYLLABIC_CONSONANTS, SyllableAlignment,
)
from app.services.parser import graphemes_to_phonemes, is_vowel, syllabify
from app.services.graph_pronunciation import pronounce_graph_word
from app.services.phonological_distance import (
    FEATURES, phoneme_similarity, phonological_edit_distance,
)


WORD_PATTERN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
MAX_COMPARISONS = 2400
BASE_WARNINGS = [
    "Aussprache, Silbengrenzen und Betonung stammen aus einer deutschen Regelheuristik; "
    "r-Nachschläge werden konservativ zugeordnet; geschriebenes finales -er bleibt als möglicher Silbenkern erhalten. "
    "Dialekt, Fremdwörter und Komposita können falsch analysiert sein. Wortweise Korrekturen sind möglich.",
    "Zeichenbereiche sind globale, 0-basierte Python-Zeichenindizes (Ende exklusiv). "
    "Bei Teilwortsegmenten umschließen sie das ganze betroffene Wort; die Silbenindizes grenzen den Klang ein.",
    "Betonungsähnlichkeit ist kein beobachteter Flow. Zeit, Tempo, Melodie, Aussage und Sprechbarkeit "
    "sind ohne Aufnahme nicht geprüft. Alle Beziehungen sind Vorschläge.",
    "Lücken bezeichnen ungepaarte Silben. Pausen und Dehnung liefern keine fehlenden Laute; "
    "Vortragsanpassungen bleiben ungehörte Vorschläge. Scores sind Sortierhilfen, keine Wahrscheinlichkeiten.",
    "Bei ausdrücklich ausgewiesenen unbetonten Endüberhängen kann die Sortierung das ausgerichtete tragende Ende "
    "berücksichtigen; das Terminalprofil zeigt weiterhin den tatsächlichen Schluss.",
]


def _nucleus(phone: str) -> bool:
    return is_vowel(phone) or phone in SYLLABIC_CONSONANTS


def _parts(syllable: list[str] | tuple[str, ...]) -> tuple[list[str], list[str], list[str]]:
    for index, phone in enumerate(syllable):
        if _nucleus(phone):
            return list(syllable[:index]), [phone], list(syllable[index + 1:])
    return list(syllable), [], []


def _similarity(left: list[str], right: list[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return 1.0 - phonological_edit_distance(left, right)


def _rhyme_span(syllables: list[list[str]], start: int = 0) -> list[str]:
    """Ignore only the first onset; later onsets remain rhyme-bearing sounds."""
    first = syllables[start] if start < len(syllables) else []
    _, vowel, coda = _parts(first)
    if not vowel:
        return []
    return vowel + coda + [phone for syllable in syllables[start + 1:] for phone in syllable]


def _graph_syllables(word: str, phones: list[str], stress: list[int]) -> tuple[list[list[str]], list[int]]:
    """Group parser-generated r offglides without swallowing a genuine -er.

    The legacy G2P emits /ɐ/ both for vocalised /r/ and for a final written
    -er. Its syllabifier treats both as independent vowels. Final -er is
    protected only when parsing the preceding written stem plus /ɐ/ reproduces
    the original phones: Feuer/Leier retain two syllables, Bier/hier do not.
    The actual phone sequence is preserved; this is a syllable grouping fix.
    """
    original = syllabify(phones)
    pattern = (list(stress) + [0] * len(original))[:len(original)]
    written = word.lower()
    protect_final = (
        written.endswith("er") and phones and phones[-1] == "ɐ"
        and graphemes_to_phonemes(written[:-2]) + ["ɐ"] == phones
    )
    syllables: list[list[str]] = []
    remapped: list[int] = []
    offset = 0
    for syllable, accent in zip(original, pattern):
        source_length = len(syllable)
        # A non-syllabic i in the repaired loanword cluster /t͡s j ɛ/ belongs
        # to that following onset, not to the coda of the preceding vowel.
        # The legacy syllabifier does not know this onset class.
        if syllables and syllable and syllable[0] == "j" and syllables[-1][-1:] == ["t͡s"]:
            syllables[-1].pop()
            syllable = ["t͡s", *syllable]
        is_offglide = (
            syllables and syllable and syllable[0] == "ɐ"
            and syllables[-1] and is_vowel(syllables[-1][-1])
            and syllables[-1][-1] != "ɐ"
            and not (protect_final and offset == len(phones) - 1)
        )
        if is_offglide:
            syllables[-1].extend(syllable)
            remapped[-1] = max(remapped[-1], accent)
        else:
            syllables.append(list(syllable))
            remapped.append(accent)
        offset += source_length
    return syllables, remapped


def _parse_lines(request: GraphBuildRequest) -> list[GraphLine]:
    overrides = {(o.line_index, o.word_index): o for o in request.overrides}
    used: set[tuple[int, int]] = set()
    lines: list[GraphLine] = []
    offset = 0
    # Splitting on LF preserves empty line indices and global CRLF offsets.
    for line_index, raw in enumerate(request.text.split("\n")):
        text = raw[:-1] if raw.endswith("\r") else raw
        words: list[GraphWord] = []
        flat: list[list[str]] = []
        stress: list[int] = []
        for word_index, match in enumerate(WORD_PATTERN.finditer(text)):
            word = match.group()
            correction = overrides.get((line_index, word_index))
            analysis_notes: list[str] = []
            if correction:
                if correction.word_text is not None and correction.word_text != word:
                    raise ValueError(
                        f"Aussprachekorrektur Zeile {line_index}, Wort {word_index}: "
                        f"word_text stimmt nicht mit der aktuellen Wortstelle '{word}' überein."
                    )
                syllables = [list(s) for s in correction.syllables]
                pattern = list(correction.stress)
                used.add((line_index, word_index))
            else:
                phones, guessed_stress, analysis_notes = pronounce_graph_word(word)
                syllables, pattern = _graph_syllables(word, phones, guessed_stress)
            start = len(flat)
            flat.extend(syllables)
            stress.extend(pattern)
            words.append(GraphWord(
                word_index=word_index, text=word,
                char_start=offset + match.start(), char_end=offset + match.end(),
                start_syllable=start, end_syllable=len(flat),
                phonetic_syllables=syllables, stress=pattern,
                origin="manual" if correction else "rule_based",
                analysis_notes=analysis_notes,
            ))
        lines.append(GraphLine(
            line_index=line_index, text=text, char_start=offset, char_end=offset + len(text),
            words=words, phonetic_syllables=flat, stress=stress,
        ))
        offset += len(raw) + 1
    unused = set(overrides) - used
    if unused:
        line_index, word_index = min(unused)
        raise ValueError(f"Aussprachekorrektur verweist auf fehlende Stelle: Zeile {line_index}, Wort {word_index}.")
    return lines


def _terminal_specs(lines: list[GraphLine], request: GraphBuildRequest) -> Iterator[tuple[int, int, int]]:
    # Round-robin: each line gets its longest terminal before a second variant.
    for rank in range(request.max_syllables - request.min_syllables + 1):
        for line in lines:
            count = len(line.phonetic_syllables)
            length = min(request.max_syllables, count) - rank
            if length >= request.min_syllables:
                yield line.line_index, count - length, count


def _internal_specs(lines: list[GraphLine], request: GraphBuildRequest) -> Iterator[tuple[int, int, int]]:
    longest = max((len(line.phonetic_syllables) for line in lines), default=0)
    for start in range(max(0, longest - request.min_syllables)):
        for line in lines:
            count = len(line.phonetic_syllables)
            for length in range(min(request.max_syllables, count - start - 1), request.min_syllables - 1, -1):
                yield line.line_index, start, start + length


def _select_nodes(
    lines: list[GraphLine], request: GraphBuildRequest, sources: dict[int, dict[str, Any]],
) -> tuple[list[GraphNode], int]:
    terminal = _terminal_specs(lines, request)
    internal = _internal_specs(lines, request) if request.include_internal else iter(())
    total_terminal = sum(max(0, min(request.max_syllables, len(line.phonetic_syllables)) - request.min_syllables + 1) for line in lines)
    total_internal = sum(
        max(0, len(line.phonetic_syllables) - length)
        for line in lines
        for length in range(request.min_syllables, request.max_syllables + 1)
    ) if request.include_internal else 0
    # Preserve room for internal relationships while prioritising terminal ones.
    terminal_budget = request.max_nodes if not total_internal else max(1, (request.max_nodes * 7) // 10)
    selected: list[tuple[int, int, int]] = []
    for _ in range(min(terminal_budget, total_terminal)):
        selected.append(next(terminal))
    for _ in range(min(total_internal, request.max_nodes - len(selected))):
        selected.append(next(internal))
    while len(selected) < min(request.max_nodes, total_terminal + total_internal):
        item = next(terminal, None)
        if item is None:
            break
        selected.append(item)
    nodes: list[GraphNode] = []
    for line_index, start, end in selected:
        line = lines[line_index]
        words = [word for word in line.words if word.start_syllable < end and word.end_syllable > start]
        first, last = words[0], words[-1]
        nodes.append(GraphNode(
            id=f"l{line_index}-s{start}-{end}", line_index=line_index,
            char_start=first.char_start, char_end=last.char_end,
            start_word=first.word_index, end_word=last.word_index + 1,
            start_syllable=start, end_syllable=end,
            text=request.text[first.char_start:last.char_end],
            phonetic_syllables=line.phonetic_syllables[start:end], stress=line.stress[start:end],
            kind="terminal" if end == len(line.phonetic_syllables) else "internal",
            origin="manual" if any(word.origin == "manual" for word in words) else "rule_based",
            source=sources.get(line_index),
        ))
    return nodes, total_terminal + total_internal


@lru_cache(maxsize=8192)
def _syllable_metrics(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[float, float, float]:
    lo, lv, lc = _parts(left)
    ro, rv, rc = _parts(right)
    return (_similarity(lv, rv) if lv and rv else 0.0, _similarity(lc, rc), _similarity(lo, ro))


def _align(left: GraphNode, right: GraphNode, max_gaps: int, mode: str = "balanced") -> list[SyllableAlignment] | None:
    """Bounded global alignment; only explicitly unstressed end overhangs may gap."""
    a, b = left.phonetic_syllables, right.phonetic_syllables
    if abs(len(a) - len(b)) > max_gaps:
        return None
    metrics = {
        (i, j): _syllable_metrics(tuple(sa), tuple(sb))
        for i, sa in enumerate(a) for j, sb in enumerate(b)
    }

    @lru_cache(maxsize=None)
    def solve(i: int, j: int, remaining: int) -> tuple[float, tuple[tuple[int | None, int | None], ...]]:
        if i == 0 and j == 0:
            return 0.0, ()
        choices = []
        if i and j:
            vowel, coda, onset = metrics[i - 1, j - 1]
            consonants = coda if i == 1 and j == 1 else (coda + onset) / 2
            similarity = 0.55 * vowel + 0.30 * consonants + 0.15 * (left.stress[i - 1] == right.stress[j - 1])
            cost, path = solve(i - 1, j - 1, remaining)
            choices.append((cost + 1 - similarity, path + ((i - 1, j - 1),)))
        if i and remaining:
            cost, path = solve(i - 1, j, remaining - 1)
            choices.append((cost + 0.65 + 0.30 * left.stress[i - 1], path + ((i - 1, None),)))
        if j and remaining:
            cost, path = solve(i, j - 1, remaining - 1)
            choices.append((cost + 0.65 + 0.30 * right.stress[j - 1], path + ((None, j - 1),)))
        return min(choices, key=lambda item: item[0]) if choices else (float("inf"), ())

    endings = []
    for left_tail, left_terminal, left_anchor in _ending_options(left, max_gaps):
        for right_tail, right_terminal, right_anchor in _ending_options(right, max_gaps - left_tail):
            if left_tail and right_tail:
                continue
            if left_tail or right_tail:
                terminal_gate, anchor_gate = (0.75, 0.65) if mode == "dirty" else (0.85, 0.75)
                if _similarity(left_terminal, right_terminal) < terminal_gate or _similarity(left_anchor, right_anchor) < anchor_gate:
                    continue
            # All remaining endings are paired; the omitted tail is visible.
            i, j = len(a) - left_tail - 1, len(b) - right_tail - 1
            cost, path = solve(i, j, max_gaps - left_tail - right_tail)
            vowel, coda, onset = metrics[i, j]
            consonants = coda if i == 0 and j == 0 else (coda + onset) / 2
            last_similarity = 0.55 * vowel + 0.30 * consonants + 0.15 * (left.stress[i] == right.stress[j])
            path += ((i, j),)
            path += tuple((index, None) for index in range(i + 1, len(a)))
            path += tuple((None, index) for index in range(j + 1, len(b)))
            endings.append((cost + 1 - last_similarity + 0.65 * (left_tail + right_tail), path))
    cost, path = min(endings, key=lambda item: item[0]) if endings else (float("inf"), ())
    if cost == float("inf"):
        return None
    alignment = []
    for i, j in path:
        vowel, coda, _ = metrics[i, j] if i is not None and j is not None else (0.0, 0.0, 0.0)
        alignment.append(SyllableAlignment(
            left_index=i, right_index=j, vowel_similarity=round(vowel, 4), coda_similarity=round(coda, 4),
            stress_match=i is not None and j is not None and left.stress[i] == right.stress[j],
        ))
    return alignment


def _terminal_span(node: GraphNode) -> list[str]:
    return _rhyme_span(node.phonetic_syllables, len(node.phonetic_syllables) - 1)


def _anchor_span(node: GraphNode) -> list[str]:
    stressed = [i for i, value in enumerate(node.stress) if value]
    return _rhyme_span(node.phonetic_syllables, stressed[-1] if stressed else len(node.stress) - 1)


def _ending_options(node: GraphNode, budget: int) -> list[tuple[int, list[str], list[str]]]:
    """(Skipped tail, carried terminal, carried anchor), retaining >=2 syllables.

    Tail syllables are never removed from the node or the actual profiles.
    The optional truncation exists only for a proposed alignment and requires
    explicitly unstressed syllables following a stressed retained anchor.
    """
    result = [(0, _terminal_span(node), _anchor_span(node))]
    for tail in range(1, min(budget, len(node.stress) - 2) + 1):
        if any(node.stress[-tail:]):
            break
        retained_stress = node.stress[:-tail]
        if not any(retained_stress):
            continue
        syllables = node.phonetic_syllables[:-tail]
        last_stress = max(i for i, value in enumerate(retained_stress) if value)
        result.append((tail, _rhyme_span(syllables, len(syllables) - 1), _rhyme_span(syllables, last_stress)))
    return result


def _rap_pattern(
    left: GraphNode, right: GraphNode, alignment: list[SyllableAlignment], mode: str,
) -> dict[str, Any] | None:
    """Distributed rime support, independent of changing syllable onsets.

    A phrase can carry several corresponding nuclei without repeating the
    consonants that START its syllables. This route needs separated strong
    nucleus anchors, support across the whole ordered sequence, and observed
    coda grip. An isolated common ending or four vowels alone is insufficient.
    Word-stress guesses describe differences; they cannot veto the evidence.
    """
    paired = [row for row in alignment if row.left_index is not None and row.right_index is not None]
    span = max(len(left.stress), len(right.stress))
    if len(paired) < 3 or len(paired) / span < 0.75:
        return None
    reduced = {"ə", "ɐ", *SYLLABIC_CONSONANTS}
    full = []
    coda_scores = []
    for position, row in enumerate(paired):
        _, lv, lc = _parts(left.phonetic_syllables[row.left_index])
        _, rv, rc = _parts(right.phonetic_syllables[row.right_index])
        if lv and rv and lv[0] not in reduced and rv[0] not in reduced:
            full.append((position, row))
        # Two absent codas are not positive consonant evidence.
        if lc and rc:
            coda_scores.append(_similarity(lc, rc))
    if len(full) < 2:
        return None
    first_position, first = full[0]
    last_position, last = full[-1]
    if first_position > 1 or last_position < len(paired) - 2 or last_position - first_position < 2:
        return None
    anchors = sqrt(first.vowel_similarity * last.vowel_similarity)
    grip = max(coda_scores, default=0.0)
    average = sum(row.vowel_similarity for row in paired) / len(paired)
    support_floor = 0.60 if mode == "dirty" else 0.75
    support = sum(row.vowel_similarity >= support_floor for row in paired)
    coverage = support / span
    interior = [row.vowel_similarity for row in paired[first_position + 1:last_position]]
    anchor_floor, mean_floor, grip_floor, interior_floor = (
        (0.90, 0.76, 0.34, 0.40) if mode == "dirty" else (0.94, 0.86, 0.55, 0.60)
    )
    if (
        first.vowel_similarity < anchor_floor or last.vowel_similarity < anchor_floor
        or average < mean_floor or grip < grip_floor
        or support < ceil(span * 0.75)
        or (interior and min(interior) < interior_floor)
    ):
        return None
    terminal = _similarity(_terminal_span(left), _terminal_span(right))
    stress = sum(row.stress_match for row in alignment) / len(alignment)
    score = (
        0.36 * anchors + 0.20 * terminal + 0.16 * average
        + 0.12 * coverage + 0.10 * grip + 0.06 * stress
    ) * len(paired) / span
    return {
        "score": score, "anchors": anchors, "grip": grip, "coverage": coverage,
        "evidence": [
            f"{span}-silbige Klangstrecke mit {support} gestützten Reimkernen in der ausgerichteten Folge.",
            f"Getrennte Klanganker: links Silben {first.left_index + 1} und {last.left_index + 1}, "
            f"rechts Silben {first.right_index + 1} und {last.right_index + 1}.",
            "Wechselnde Silbenanfänge sind zulässig; tatsächlich ähnliche Silbenauslaute stützen die Verbindung.",
        ],
    }


def _compare(left: GraphNode, right: GraphNode, request: GraphBuildRequest) -> GraphEdge | None:
    max_gaps = 0 if request.mode == "strict" else request.max_syllable_delta
    alignment = _align(left, right, max_gaps, request.mode)
    if alignment is None:
        return None
    gap_count = sum(row.left_index is None or row.right_index is None for row in alignment)
    paired = [row for row in alignment if row.left_index is not None and row.right_index is not None]
    last_pair = paired[-1]
    left_tail = len(left.stress) - last_pair.left_index - 1
    right_tail = len(right.stress) - last_pair.right_index - 1
    trailing = left_tail + right_tail
    count = len(alignment)
    vowels = sum(row.vowel_similarity for row in alignment) / count
    stress = sum(row.stress_match for row in alignment) / count
    consonant_total, covered = 0.0, 0
    for row in alignment:
        i, j = row.left_index, row.right_index
        if i is None or j is None:
            continue
        vowel, coda, onset = _syllable_metrics(tuple(left.phonetic_syllables[i]), tuple(right.phonetic_syllables[j]))
        consonants = coda if i == 0 and j == 0 else (coda + onset) / 2
        consonant_total += consonants
        covered += int(vowel >= 0.78 and consonants >= 0.55)
    profile = GraphProfile(
        anchor=_similarity(_anchor_span(left), _anchor_span(right)),
        terminal=_similarity(_terminal_span(left), _terminal_span(right)),
        vowels=vowels, consonants=consonant_total / count, stress=stress,
        coverage=covered / max(len(left.stress), len(right.stress)),
    )
    valid_nuclei = all(any(_nucleus(p) for p in syllable) for syllable in left.phonetic_syllables + right.phonetic_syllables)
    clean = (
        not gap_count and valid_nuclei
        and _rhyme_span(left.phonetic_syllables) == _rhyme_span(right.phonetic_syllables)
        and left.stress == right.stress
    )
    if request.mode == "strict" and not clean:
        return None
    support_terminal, support_anchor = profile.terminal, profile.anchor
    if trailing:
        # Gate on the carried end, without replacing the actual terminal score.
        left_end = next((option for option in _ending_options(left, max_gaps) if option[0] == left_tail), None)
        right_end = next((option for option in _ending_options(right, max_gaps) if option[0] == right_tail), None)
        if left_end is None or right_end is None or len(paired) < 2:
            return None
        support_terminal = _similarity(left_end[1], right_end[1])
        support_anchor = _similarity(left_end[2], right_end[2])
        support_gates = (0.75, 0.65) if request.mode == "dirty" else (0.85, 0.75)
        if support_terminal < support_gates[0] or support_anchor < support_gates[1]:
            return None
    # A matching last word cannot alone legitimise an arbitrary long phrase.
    gates = (0.40, 0.35, 0.45, 0.40) if request.mode == "dirty" else (0.65, 0.55, 0.62, 0.55)
    gate_vowels = profile.vowels * count / len(paired) if trailing else profile.vowels
    segment_supported = clean or not (
        support_terminal < gates[0] or support_anchor < gates[1]
        or gate_vowels < gates[2] or profile.coverage < gates[3]
    )
    score = (
        0.35 * support_anchor + 0.25 * support_terminal + 0.12 * profile.vowels
        + 0.13 * profile.consonants + 0.08 * profile.stress + 0.07 * profile.coverage
    ) - 0.06 * trailing
    basis = "exact" if clean else "segment"
    evidence: list[str] = []
    if not segment_supported or score < request.min_similarity:
        rap = _rap_pattern(left, right, alignment, request.mode) if not trailing and request.mode != "strict" else None
        if rap is None or rap["score"] < request.min_similarity:
            return None
        basis, score, evidence = "rap_pattern", rap["score"], rap["evidence"]
        profile.rap_anchors = rap["anchors"]
        profile.consonant_grip = rap["grip"]
        profile.coverage = rap["coverage"]
    deviations, operations = [], []
    if profile.vowels < 0.9999:
        deviations.append("Vokalkerne weichen ab; keine lautidentische Reimstrecke.")
    if profile.consonants < 0.9999:
        deviations.append("Konsonanten im Reimsegment weichen ab (einschließlich innerer Silbenanfänge).")
    if profile.stress < 0.9999:
        deviations.append("Die angegebenen Betonungsmuster stimmen nicht vollständig überein.")
        operations.append("Akzentsetzung im eigenen Vortrag prüfen; keine Betonungsänderung ist bereits bestätigt.")
    if gap_count:
        deviations.append(f"{gap_count} Silbe(n) bleiben in der Ausrichtung ungepaart.")
        operations.append("Ungepaarte Silben gegebenenfalls kürzer oder in feinerer Unterteilung sprechen; am Zieltempo erproben.")
    if trailing:
        deviations.append(
            f"Unbetonter Endüberhang: links {left_tail}, rechts {right_tail} ungepaarte Endsilbe(n). "
            f"Tatsächlicher Terminalvergleich {profile.terminal:.2f}; getragenes ausgerichtetes Ende "
            f"{support_terminal:.2f}, ausgerichteter Anker {support_anchor:.2f}. Keine saubere Entsprechung."
        )
        operations.append("Den unbetonten Überhang nach dem getragenen Ende sprechen und dessen Platz im Takt selbst erproben; Flow und Dehnung sind nicht bestätigt.")
    if not valid_nuclei:
        deviations.append("Mindestens ein automatisch erkanntes Segment besitzt keinen sicher erkannten Silbenkern.")
    if not clean and not operations:
        operations.append("Unreine Klangentsprechung laut im Zusammenhang prüfen; keine Anpassung ist vorausgesetzt.")
    return GraphEdge(
        id=f"{left.id}__{right.id}", source=left.id, target=right.id,
        kind="clean" if clean else ("flex" if gap_count else "slant"),
        score=round(score, 4), profile=profile, alignment=alignment,
        deviations=deviations, required_operations=operations,
        basis=basis, evidence=evidence,
    )


def _candidate_pairs(nodes: list[GraphNode], request: GraphBuildRequest) -> list[tuple[float, int, int]]:
    """Terminal-vowel index first; fine comparisons remain hard-bounded."""
    budget = 0 if request.mode == "strict" else request.max_syllable_delta
    endings = [_ending_options(node, budget) for node in nodes]
    buckets: dict[str, list[tuple[int, int, list[str], list[str]]]] = defaultdict(list)
    for index, node in enumerate(nodes):
        for tail, terminal, anchor in endings[index]:
            if terminal:
                buckets[terminal[0]].append((index, tail, terminal, anchor))
    priorities: dict[tuple[int, int], float] = {}
    vowel_gate = 1.0 if request.mode == "strict" else (0.50 if request.mode == "dirty" else 0.70)
    for right_index, right in enumerate(nodes):
        for right_tail, right_terminal, right_anchor in endings[right_index]:
            if not right_terminal:
                continue
            for vowel, items in buckets.items():
                if phoneme_similarity(vowel, right_terminal[0]) < vowel_gate:
                    continue
                for left_index, left_tail, left_terminal, left_anchor in items:
                    if left_index >= right_index or left_tail + right_tail > budget or (left_tail and right_tail):
                        continue
                    left = nodes[left_index]
                    if abs(len(left.stress) - len(right.stress)) > budget:
                        continue
                    if left.line_index == right.line_index and left.start_syllable < right.end_syllable and right.start_syllable < left.end_syllable:
                        continue
                    terminal = _similarity(left_terminal, right_terminal)
                    trailing = left_tail + right_tail
                    minimum = 1.0 if request.mode == "strict" else (0.40 if request.mode == "dirty" else 0.65)
                    if trailing:
                        minimum = 0.75 if request.mode == "dirty" else 0.85
                    if terminal < minimum:
                        continue
                    anchor = _similarity(left_anchor, right_anchor)
                    if trailing and anchor < (0.65 if request.mode == "dirty" else 0.75):
                        continue
                    # Prefer actual matching terminals over proposed overhangs.
                    priority = 0.55 * terminal + 0.40 * anchor + 0.05 * (left.kind == right.kind == "terminal") - 0.04 * trailing
                    key = (left_index, right_index)
                    priorities[key] = max(priority, priorities.get(key, -1.0))
    pairs = [(priority, left, right) for (left, right), priority in priorities.items()]
    pairs.sort(key=lambda item: (-item[0], item[1], item[2]))
    return pairs


def build_rhyme_graph(request: GraphBuildRequest, sources: dict[int, dict[str, Any]] | None = None) -> GraphResponse:
    lines = _parse_lines(request)
    nodes, possible_nodes = _select_nodes(lines, request, sources or {})
    warnings = list(BASE_WARNINGS)
    truncated = possible_nodes > len(nodes)
    if truncated:
        warnings.append(f"Segmentlimit: {len(nodes)} von {possible_nodes} möglichen Segmenten ausgewählt; Endsegmente priorisiert, Innenreime begrenzt berücksichtigt.")
    if any(not any(_nucleus(phone) for phone in syllable) for line in lines for syllable in line.phonetic_syllables):
        warnings.append("Mindestens eine Wortanalyse enthält keinen erkannten Silbenkern; Aussprache bitte korrigieren.")
    unknown = {phone for line in lines for syllable in line.phonetic_syllables for phone in syllable if phone not in FEATURES and phone not in SYLLABIC_CONSONANTS}
    if unknown:
        warnings.append("Die Regelanalyse enthält unbekannte Lautsymbole; Fremdwörter oder Aussprache bitte korrigieren.")
    if not nodes:
        warnings.append("Keine Segmente in der gewählten Silbenlänge; Text ergänzen oder Mindestlänge verkleinern.")
    pairs = _candidate_pairs(nodes, request)
    if len(pairs) > MAX_COMPARISONS:
        truncated = True
        warnings.append(f"Vergleichslimit: {MAX_COMPARISONS} von {len(pairs)} vorgefilterten Paaren werden genau verglichen; mögliche Beziehungen bleiben ungeprüft.")
    edges = []
    for _, left, right in pairs[:MAX_COMPARISONS]:
        edge = _compare(nodes[left], nodes[right], request)
        if edge:
            edges.append(edge)
    edges.sort(key=lambda edge: (-edge.score, edge.id))
    if len(edges) > request.max_edges:
        truncated = True
        warnings.append(f"Kantenlimit: {request.max_edges} von {len(edges)} gefundenen Beziehungen ausgegeben.")
    return GraphResponse(
        text=request.text, mode=request.mode, lines=lines, nodes=nodes,
        edges=edges[:request.max_edges], warnings=warnings,
        analysis_notes=list(BASE_WARNINGS), truncated=truncated,
    )
