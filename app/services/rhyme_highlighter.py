"""Syllable-level rhyme highlighting for rap text."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from app.services.phrase_scorer import score_rhyme
from app.services.parser import (
    UNSTRESSED_PREFIXES,
    detect_stress,
    graphemes_to_phonemes,
    is_vowel,
    syllabify,
)
from app.services.phonological_distance import FEATURES, tail_similarity
from app.services.rap_text_analyzer import BAR_COUNT_RE, SECTION_RE
from app.services.rhyme_window_extractor import FUNCTION_WORDS


TOKEN_OR_GAP_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+|\s+|[^A-Za-zÄÖÜäöüß\s]+")
VOWEL_GROUP_RE = re.compile(r"[aeiouäöüyAEIOUÄÖÜY]+")
WORD_EDGE_CHARS = ".,!?;:()[]{}\"'„“”‚‘`"
CLAUSE_BREAK_RE = re.compile(r"[,.;:!?]+")
MIN_WINDOW_SYLLABLES = 3
MAX_WINDOW_SYLLABLES = 8
MIN_PHRASE_SCORE = 0.56
MIN_SYLLABLE_SCORE = 0.62
LONG_OR_DIPHTHONGS = {
    "aː", "eː", "iː", "oː", "uː", "øː", "yː",
    "aɪ", "aʊ", "ɔʏ",
}

LOW_VALUE_WORDS = FUNCTION_WORDS | {
    "den", "dem", "des", "wen", "wem", "wessen",
    "mich", "dich", "uns", "euch", "mein", "meine", "meinen", "meinem",
    "dein", "deine", "deinen", "deinem", "sein", "seine", "seinen", "seinem",
    "ihr", "ihre", "ihren", "ihrem", "euer", "eure", "euren", "eurem",
    "im", "am", "ans", "ins", "vom", "zur", "zum", "beim",
    "nur", "mal", "so",
}

PALETTE = [
    "#ff5c8a", "#58c7ff", "#ffd166", "#75e06f", "#c98cff", "#ff8f4f",
    "#4dd6c8", "#f071ff", "#a3e635", "#60a5fa", "#f472b6", "#facc15",
    "#34d399", "#fb7185", "#38bdf8", "#d8b4fe", "#f97316", "#22c55e",
]


@dataclass
class HighlightSegment:
    text: str
    kind: str
    word: str | None = None
    syllable_index: int | None = None
    accented: bool = False
    terminal: bool = False
    rhyme_group: str | None = None
    color: str | None = None
    phonetic: List[str] = field(default_factory=list)


@dataclass
class HighlightLine:
    raw_index: int
    lyric_index: int | None
    raw: str
    is_lyric: bool
    segments: List[HighlightSegment]


@dataclass
class RhymeGroup:
    key: str
    color: str
    count: int
    line_indices: List[int]
    examples: List[str]


@dataclass
class RhymeHighlightAnalysis:
    lines: List[HighlightLine]
    rhyme_groups: List[RhymeGroup]
    colored_syllable_count: int
    accented_syllable_count: int


@dataclass
class _Node:
    line_pos: int
    segment_pos: int
    lyric_index: int
    line_syllable_index: int
    word: str
    text: str
    syllable_index: int
    accented: bool
    terminal: bool
    anchor: List[str]
    vowel: str | None
    coda: List[str]


@dataclass
class _WordSpan:
    text: str
    start_syllable: int
    end_syllable: int


@dataclass
class _PhraseWindow:
    raw_text: str
    line_pos: int
    lyric_index: int
    start_syllable: int
    end_syllable: int
    syllable_count: int


class _UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _is_title_or_section(line: str) -> bool:
    stripped = line.strip()
    return stripped == "RAKi - DiCH" or SECTION_RE.match(stripped) is not None or BAR_COUNT_RE.match(stripped) is not None


def _visual_syllables(word: str) -> List[str]:
    groups = list(VOWEL_GROUP_RE.finditer(word))
    if len(groups) <= 1:
        return [word]

    boundaries: List[int] = []
    for left, right in zip(groups, groups[1:]):
        cluster_len = max(0, right.start() - left.end())
        boundary = right.start() - 1 if cluster_len else right.start()
        boundary = max(left.end(), min(boundary, len(word) - 1))
        if 0 < boundary < len(word):
            boundaries.append(boundary)

    out: List[str] = []
    start = 0
    for boundary in boundaries:
        if boundary <= start:
            continue
        out.append(word[start:boundary])
        start = boundary
    out.append(word[start:])
    return [chunk for chunk in out if chunk] or [word]


def _first_vowel_idx(phones: List[str]) -> int | None:
    for idx, phoneme in enumerate(phones):
        if is_vowel(phoneme):
            return idx
    return None


def _accent_indices(word: str, visual_count: int, stress: List[int]) -> set[int]:
    if visual_count <= 1:
        return {0}
    norm = word.lower()
    if any(norm.startswith(prefix) for prefix in UNSTRESSED_PREFIXES):
        return {min(1, visual_count - 1)}
    indices = [idx for idx, value in enumerate(stress) if value == 1]
    if not indices:
        return {0}
    return {min(idx, visual_count - 1) for idx in indices}


def _is_voiceless_obstruent(phoneme: str) -> bool:
    feature = FEATURES.get(phoneme)
    return bool(feature and feature.typ in {"plosive", "fricative", "affricate"} and not feature.voiced)


def _vowel_family(phoneme: str) -> str:
    families = {
        "a": "a", "aː": "a",
        "ɛ": "e", "eː": "e", "œ": "oe", "øː": "oe",
        "ɪ": "i", "iː": "i",
        "ɔ": "o", "oː": "o",
        "ʊ": "u", "uː": "u",
        "ʏ": "ue", "yː": "ue",
        "aɪ": "ai", "aʊ": "au", "ɔʏ": "eu",
    }
    return families.get(phoneme, phoneme)


def _rhyme_similarity(left: _Node, right: _Node) -> float:
    if not left.vowel or not right.vowel:
        return 0.0
    if _vowel_family(left.vowel) != _vowel_family(right.vowel):
        return 0.0

    base = tail_similarity(left.anchor, right.anchor)
    hard_slant = (
        left.coda
        and right.coda
        and all(_is_voiceless_obstruent(p) for p in left.coda + right.coda)
    )
    if hard_slant:
        base = max(base, 0.62)
    return base


def _syllable_anchor(syllable: List[str]) -> tuple[List[str], str | None, List[str]]:
    vowel_idx = _first_vowel_idx(syllable)
    if vowel_idx is None:
        return [], None, []
    anchor = syllable[vowel_idx:]
    return anchor, syllable[vowel_idx], syllable[vowel_idx + 1:]


def _map_visual_to_phonetic_syllable(visual_idx: int, visual_count: int, phonetic_count: int) -> int:
    if phonetic_count <= 1 or visual_count <= 1:
        return 0
    mapped = round(visual_idx * (phonetic_count - 1) / (visual_count - 1))
    return max(0, min(mapped, phonetic_count - 1))


def _word_segments(word: str, syllable_base: int = 0) -> tuple[List[HighlightSegment], List[_Node], int]:
    clean_word = word.strip(WORD_EDGE_CHARS) or word
    phones = graphemes_to_phonemes(clean_word)
    phon_syllables = syllabify(phones)
    stress = detect_stress(clean_word, len(phon_syllables))
    visual = _visual_syllables(word)
    accents = _accent_indices(clean_word, len(visual), stress)

    segments: List[HighlightSegment] = []
    nodes: List[_Node] = []
    for idx, chunk in enumerate(visual):
        phon_idx = _map_visual_to_phonetic_syllable(idx, len(visual), len(phon_syllables))
        syllable_phones = phon_syllables[phon_idx] if phon_syllables else []
        anchor, vowel, coda = _syllable_anchor(syllable_phones)
        accented = idx in accents
        terminal = idx == len(visual) - 1
        segment = HighlightSegment(
            text=chunk,
            kind="syllable",
            word=clean_word,
            syllable_index=idx,
            accented=accented,
            terminal=terminal,
            phonetic=syllable_phones,
        )
        segment_pos = len(segments)
        segments.append(segment)
        weak_terminal = vowel in {"ə", "ɐ"} and not accented
        low_value_word = clean_word.lower() in LOW_VALUE_WORDS
        strong_internal = (
            accented
            and not terminal
            and len(chunk) >= 3
            and (bool(coda) or vowel in LONG_OR_DIPHTHONGS)
        )
        color_candidate = terminal or strong_internal
        if vowel is not None and color_candidate and not weak_terminal and not low_value_word:
            nodes.append(
                _Node(
                    line_pos=-1,
                    segment_pos=segment_pos,
                    lyric_index=-1,
                    line_syllable_index=syllable_base + phon_idx,
                    word=clean_word,
                    text=chunk,
                    syllable_index=idx,
                    accented=accented,
                    terminal=terminal,
                    anchor=anchor,
                    vowel=vowel,
                    coda=coda,
                )
            )
    return segments, nodes, len(phon_syllables)


def _phrase_windows_for_clause(
    words: List[_WordSpan],
    start_word: int,
    end_word: int,
    line_pos: int,
    lyric_index: int,
) -> List[_PhraseWindow]:
    windows: List[_PhraseWindow] = []
    running = 0
    for idx in range(end_word - 1, start_word - 1, -1):
        word = words[idx]
        running += word.end_syllable - word.start_syllable
        if running > MAX_WINDOW_SYLLABLES:
            break
        if running < MIN_WINDOW_SYLLABLES:
            continue
        window_words = words[idx:end_word]
        windows.append(
            _PhraseWindow(
                raw_text=" ".join(w.text for w in window_words),
                line_pos=line_pos,
                lyric_index=lyric_index,
                start_syllable=word.start_syllable,
                end_syllable=words[end_word - 1].end_syllable,
                syllable_count=running,
            )
        )
    return windows


def _phrase_windows_for_line(
    words: List[_WordSpan],
    clause_ranges: List[tuple[int, int]],
    line_pos: int,
    lyric_index: int,
) -> List[_PhraseWindow]:
    windows: List[_PhraseWindow] = []
    seen: set[tuple[int, int, str]] = set()
    for start_word, end_word in clause_ranges:
        if end_word <= start_word:
            continue
        for window in _phrase_windows_for_clause(words, start_word, end_word, line_pos, lyric_index):
            key = (window.start_syllable, window.end_syllable, window.raw_text.lower())
            if key not in seen:
                seen.add(key)
                windows.append(window)
    return windows


def _window_nodes(nodes: List[_Node], window: _PhraseWindow) -> List[int]:
    return [
        idx
        for idx, node in enumerate(nodes)
        if (
            node.line_pos == window.line_pos
            and window.start_syllable <= node.line_syllable_index < window.end_syllable
        )
    ]


def _phrase_windows_match(left: _PhraseWindow, right: _PhraseWindow) -> bool:
    if abs(left.syllable_count - right.syllable_count) > 1:
        return False
    try:
        score = score_rhyme(left.raw_text, right.raw_text)
    except Exception:
        return False
    return not score.anchor_gated and score.total >= MIN_PHRASE_SCORE


def highlight_rhyme_syllables(text: str, context_radius: int = 6) -> RhymeHighlightAnalysis:
    lines: List[HighlightLine] = []
    nodes: List[_Node] = []
    phrase_windows: List[_PhraseWindow] = []
    lyric_index = 0

    for raw_index, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        is_lyric = bool(stripped) and not _is_title_or_section(stripped)
        if is_lyric:
            lyric_index += 1

        segments: List[HighlightSegment] = []
        if not is_lyric:
            segments.append(HighlightSegment(text=raw, kind="text"))
        else:
            word_spans: List[_WordSpan] = []
            clause_ranges: List[tuple[int, int]] = []
            clause_start_word = 0
            syllable_cursor = 0
            for token in TOKEN_OR_GAP_RE.findall(raw):
                if token.isspace():
                    segments.append(HighlightSegment(text=token, kind="space"))
                    continue
                if re.fullmatch(r"[A-Za-zÄÖÜäöüß]+", token):
                    word_start = syllable_cursor
                    token_segments, token_nodes, syllable_count = _word_segments(token, syllable_cursor)
                    base = len(segments)
                    segments.extend(token_segments)
                    for node in token_nodes:
                        node.line_pos = len(lines)
                        node.segment_pos = base + node.segment_pos
                        node.lyric_index = lyric_index
                        nodes.append(node)
                    syllable_cursor += syllable_count
                    word_spans.append(
                        _WordSpan(
                            text=token,
                            start_syllable=word_start,
                            end_syllable=syllable_cursor,
                        )
                    )
                    continue
                segments.append(HighlightSegment(text=token, kind="punct"))
                if CLAUSE_BREAK_RE.fullmatch(token):
                    if len(word_spans) > clause_start_word:
                        clause_ranges.append((clause_start_word, len(word_spans)))
                    clause_start_word = len(word_spans)

            if len(word_spans) > clause_start_word:
                clause_ranges.append((clause_start_word, len(word_spans)))
            phrase_windows.extend(
                _phrase_windows_for_line(word_spans, clause_ranges, len(lines), lyric_index)
            )

        lines.append(
            HighlightLine(
                raw_index=raw_index,
                lyric_index=lyric_index if is_lyric else None,
                raw=raw,
                is_lyric=is_lyric,
                segments=segments,
            )
        )

    uf = _UnionFind(len(nodes))
    for i, left in enumerate(phrase_windows):
        for right in phrase_windows[i + 1:]:
            if left.lyric_index == right.lyric_index:
                continue
            if abs(left.lyric_index - right.lyric_index) > context_radius:
                continue
            if not _phrase_windows_match(left, right):
                continue
            left_nodes = _window_nodes(nodes, left)
            right_nodes = _window_nodes(nodes, right)
            for left_node_idx in left_nodes:
                for right_node_idx in right_nodes:
                    if _rhyme_similarity(nodes[left_node_idx], nodes[right_node_idx]) >= MIN_SYLLABLE_SCORE:
                        uf.union(left_node_idx, right_node_idx)

    component_members: Dict[int, List[int]] = {}
    for idx in range(len(nodes)):
        component_members.setdefault(uf.find(idx), []).append(idx)

    rhyme_groups: List[RhymeGroup] = []
    colored_syllables = 0
    color_index = 0
    for members in sorted(component_members.values(), key=lambda group: (-len(group), nodes[group[0]].lyric_index)):
        if len(members) < 2:
            continue
        line_indices = sorted({nodes[idx].lyric_index for idx in members})
        examples: List[str] = []
        seen_examples: set[str] = set()
        for idx in members:
            label = f"{nodes[idx].text} ({nodes[idx].word}, Z{nodes[idx].lyric_index})"
            if label not in seen_examples:
                seen_examples.add(label)
                examples.append(label)
            if len(examples) >= 8:
                break

        color = PALETTE[color_index % len(PALETTE)]
        group_key = f"r{color_index + 1}"
        color_index += 1

        for idx in members:
            node = nodes[idx]
            segment = lines[node.line_pos].segments[node.segment_pos]
            segment.rhyme_group = group_key
            segment.color = color
            colored_syllables += 1

        rhyme_groups.append(
            RhymeGroup(
                key=group_key,
                color=color,
                count=len(members),
                line_indices=line_indices,
                examples=examples,
            )
        )

    accented_count = sum(
        1
        for line in lines
        for segment in line.segments
        if segment.kind == "syllable" and segment.accented
    )
    return RhymeHighlightAnalysis(
        lines=lines,
        rhyme_groups=rhyme_groups,
        colored_syllable_count=colored_syllables,
        accented_syllable_count=accented_count,
    )
