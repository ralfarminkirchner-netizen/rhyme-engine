"""Song-level rap technique analysis built on the existing rhyme primitives."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Literal

from app.services.parser import parse_german_word
from app.services.phonological_distance import tail_similarity
from app.services.rhyme_window_extractor import (
    FUNCTION_WORDS,
    build_line_parse,
    extract_default_windows,
)

FeatureKind = Literal["terminal", "rhyme"]

SECTION_RE = re.compile(r"^(?:hook|part)\b", re.IGNORECASE)
BAR_COUNT_RE = re.compile(r"^\d+$")
TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+")


@dataclass
class RhymeChain:
    kind: str
    words: List[str]
    line_indices: List[int]
    similarity_floor: float


@dataclass
class RefrainGroup:
    key: str
    line_indices: List[int]
    texts: List[str]


@dataclass
class DeepStructure:
    key: str
    title: str
    line_indices: List[int]
    evidence_terms: List[str]


@dataclass
class RefrainStage:
    line_index: int
    text: str
    role: str


@dataclass
class RefrainEvolution:
    key: str
    stages: List[RefrainStage]


@dataclass
class QuestionMove:
    key: str
    line_index: int
    text: str


@dataclass
class RhetoricalDevice:
    kind: str
    line_indices: List[int]
    evidence: List[str]
    description: str


@dataclass
class EchoPattern:
    kind: str
    line_index: int
    words: List[str]
    stem: str


@dataclass
class LyricSection:
    name: str
    kind: str
    start_line: int
    end_line: int
    line_indices: List[int]
    texts: List[str]


@dataclass
class StructuralStage:
    key: str
    title: str
    line_indices: List[int]


@dataclass
class StructuralArc:
    key: str
    title: str
    stages: List[StructuralStage]
    complete: bool
    ordered: bool


@dataclass
class BypassingAudit:
    trauma_before_nondual: bool
    integration_before_nondual: bool
    first_trauma_line: int | None
    first_integration_line: int | None
    first_specific_nondual_line: int | None


@dataclass
class CoverageItem:
    key: str
    label: str
    covered: bool
    evidence: List[str]


@dataclass
class CompletionAudit:
    complete: bool
    covered_count: int
    total_count: int
    missing_keys: List[str]
    items: List[CoverageItem]


@dataclass
class TechniqueInventory:
    window_tag_counts: Dict[str, int]
    internal_chain_count: int
    terminal_chain_count: int
    refrain_group_count: int
    prefix_chain_count: int
    rhetorical_device_count: int
    echo_pattern_count: int


@dataclass
class RapLineAnalysis:
    line_index: int
    text: str
    window_tags: List[str]
    flow_shapes: List[str]
    parallel_shapes: List[str]
    anchor_nuclei: List[str]
    internal_rhyme_chains: List[RhymeChain] = field(default_factory=list)
    prefix_chains: List[List[str]] = field(default_factory=list)


@dataclass
class RapTextAnalysis:
    lines: List[RapLineAnalysis]
    terminal_rhyme_chains: List[RhymeChain]
    refrain_groups: List[RefrainGroup]
    motif_counts: Dict[str, int]
    deep_structures: List[DeepStructure]
    refrain_evolutions: List[RefrainEvolution]
    question_arc: List[QuestionMove]
    rhetorical_devices: List[RhetoricalDevice]
    echo_patterns: List[EchoPattern]
    sections: List[LyricSection]
    structural_arcs: List[StructuralArc]
    bypassing_audit: BypassingAudit
    completion_audit: CompletionAudit
    technique_inventory: TechniqueInventory


DEEP_STRUCTURE_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "embodiment_wound",
        "Verkörperung und Verletzung",
        (
            "leib", "seele", "wehwehchen", "schäden", "grenzen",
            "täterintrojekten", "traumata", "narben", "nervensysteme",
        ),
    ),
    (
        "shadow_integration",
        "Schattenintegration statt Flucht",
        (
            "integriere", "schatten*", "fragmente", "abgespaltene",
            "projektionen", "ängsten", "kämpfe", "wölfe", "hölle",
        ),
    ),
    (
        "conditioning_will_karma",
        "Wille, Karma und Bedingtheit",
        (
            "wille", "frei", "freiheit", "marionetten", "regeln",
            "fehlerketten", "karma", "pech", "bestimmt",
        ),
    ),
    (
        "stillness_insight",
        "Stille und Einsicht",
        (
            "stille", "innenraum", "denken*", "finden", "erkennen",
            "trennung", "illusion", "versenkung",
        ),
    ),
    (
        "witness_critic",
        "Innerer Zeuge löst inneren Kritiker",
        (
            "integrität", "zeugen", "kritiker", "stimme", "kindheit",
            "mittel", "sicher",
        ),
    ),
    (
        "nondual_simplicity",
        "Nicht-Trennung und radikale Einfachheit",
        (
            "leben", "erleben", "ungetrennt", "wunder", "jetzt",
            "hier", "unverändert", "spiegel", "welt", "existieren",
        ),
    ),
)


def extract_lyric_lines(text: str) -> List[str]:
    """Return lyric lines, skipping headings, bar counters, and prose analysis."""
    lyric = text.split("Ich schreibe das Folgende", 1)[0]
    lines: List[str] = []

    for raw in lyric.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "RAKi - DiCH":
            continue
        if BAR_COUNT_RE.match(line):
            continue
        if SECTION_RE.match(line):
            continue
        lines.append(line)

    return lines


def extract_lyric_sections(text: str) -> List[LyricSection]:
    """Return lyric sections with line indices matching ``extract_lyric_lines``."""
    lyric = text.split("Ich schreibe das Folgende", 1)[0]
    sections: List[LyricSection] = []
    current_name = "Intro"
    current_kind = "intro"
    current_rows: List[tuple[int, str]] = []
    lyric_line_index = 0

    def flush() -> None:
        nonlocal current_rows
        if not current_rows:
            return
        indices = [idx for idx, _ in current_rows]
        sections.append(
            LyricSection(
                name=current_name,
                kind=current_kind,
                start_line=indices[0],
                end_line=indices[-1],
                line_indices=indices,
                texts=[line for _, line in current_rows],
            )
        )
        current_rows = []

    for raw in lyric.splitlines():
        line = raw.strip()
        if not line or line == "RAKi - DiCH" or BAR_COUNT_RE.match(line):
            continue
        if SECTION_RE.match(line):
            flush()
            current_name = line
            current_kind = "hook" if line.lower().startswith("hook") else "part"
            continue
        lyric_line_index += 1
        current_rows.append((lyric_line_index, line))

    flush()
    return sections


def _tokens(text: str) -> List[str]:
    return TOKEN_RE.findall(text)


def _normalise_token(token: str) -> str:
    return token.lower().replace("ß", "ss")


def _content_tokens(text: str) -> List[str]:
    return [
        _normalise_token(t)
        for t in _tokens(text)
        if _normalise_token(t) not in FUNCTION_WORDS and len(t) >= 3
    ]


def _normalised_line(text: str) -> str:
    return " ".join(_normalise_token(t) for t in _tokens(text))


def _matches_term(token_set: set[str], line_text: str, term: str) -> bool:
    if term.endswith("*"):
        prefix = term[:-1]
        return any(token.startswith(prefix) for token in token_set)
    if " " in term:
        return term in line_text
    return term in token_set


def _phonetic_feature(word: str, feature: FeatureKind) -> List[str]:
    parsed = parse_german_word(word)
    if feature == "terminal":
        return parsed.terminal_span
    return parsed.rhyme_span


def _pairwise_floor(words: List[str], feature: FeatureKind) -> float:
    floor = 1.0
    for i, left in enumerate(words):
        for right in words[i + 1:]:
            floor = min(
                floor,
                tail_similarity(_phonetic_feature(left, feature), _phonetic_feature(right, feature)),
            )
    return floor


def _pairwise_groups(words: List[str], feature: FeatureKind, threshold: float) -> List[List[str]]:
    unique_words: List[str] = []
    seen_words: set[str] = set()
    for word in words:
        key = _normalise_token(word)
        if key in seen_words:
            continue
        seen_words.add(key)
        unique_words.append(word)

    groups: List[List[str]] = []
    seen_groups: set[tuple[str, ...]] = set()
    for i, left in enumerate(unique_words):
        for right in unique_words[i + 1:]:
            sim = tail_similarity(_phonetic_feature(left, feature), _phonetic_feature(right, feature))
            if sim < threshold:
                continue
            key = tuple(sorted((_normalise_token(left), _normalise_token(right))))
            if key in seen_groups:
                continue
            seen_groups.add(key)
            groups.append([left, right])

    for i, word in enumerate(unique_words):
        comp = [word]
        for candidate in unique_words[i + 1:]:
            if all(
                tail_similarity(_phonetic_feature(candidate, feature), _phonetic_feature(existing, feature)) >= threshold
                for existing in comp
            ):
                comp.append(candidate)
        if len(comp) < 2:
            continue
        key = tuple(sorted(_normalise_token(w) for w in comp))
        if key in seen_groups:
            continue
        seen_groups.add(key)
        groups.append(comp)
    return groups


def _internal_rhyme_chains(line: str, line_index: int) -> List[RhymeChain]:
    words = [w for w in _tokens(line) if _normalise_token(w) not in FUNCTION_WORDS and len(w) >= 4]
    chains: List[RhymeChain] = []
    seen: set[tuple[str, ...]] = set()
    for comp in _pairwise_groups(words, "rhyme", threshold=0.58):
        key = tuple(sorted(_normalise_token(w) for w in comp))
        seen.add(key)
        chains.append(
            RhymeChain(
                kind="internal_rhyme_chain",
                words=comp,
                line_indices=[line_index],
                similarity_floor=round(_pairwise_floor(comp, "rhyme"), 4),
            )
        )
    for comp in _pairwise_groups(words, "terminal", threshold=0.70):
        key = tuple(sorted(_normalise_token(w) for w in comp))
        if key in seen:
            continue
        chains.append(
            RhymeChain(
                kind="internal_terminal_chain",
                words=comp,
                line_indices=[line_index],
                similarity_floor=round(_pairwise_floor(comp, "terminal"), 4),
            )
        )
    return chains


def _prefix_chains(line: str) -> List[List[str]]:
    buckets: Dict[str, List[str]] = {}
    for word in _tokens(line):
        norm = _normalise_token(word)
        if len(norm) < 6:
            continue
        prefix = norm[:3]
        buckets.setdefault(prefix, []).append(word)
    return [words for words in buckets.values() if len(words) >= 2]


def _terminal_rhyme_chains(lines: List[str]) -> List[RhymeChain]:
    endings: List[tuple[int, str]] = []
    for idx, line in enumerate(lines, 1):
        tokens = _tokens(line)
        if not tokens:
            continue
        endings.append((idx, tokens[-1]))

    chains: List[RhymeChain] = []
    seen: set[tuple[int, ...]] = set()
    for start, (line_idx, word) in enumerate(endings):
        comp = [(line_idx, word)]
        for next_line_idx, next_word in endings[start + 1:start + 6]:
            if all(
                tail_similarity(_phonetic_feature(next_word, "terminal"), _phonetic_feature(existing, "terminal")) >= 0.70
                for _, existing in comp
            ):
                comp.append((next_line_idx, next_word))
        if len(comp) < 2:
            continue
        line_indices = [idx for idx, _ in comp]
        key = tuple(line_indices)
        if key in seen:
            continue
        seen.add(key)
        words = [w for _, w in comp]
        chains.append(
            RhymeChain(
                kind="terminal_rhyme_chain",
                words=words,
                line_indices=line_indices,
                similarity_floor=round(_pairwise_floor(words, "terminal"), 4),
            )
        )
    return chains


def _refrain_groups(lines: List[str]) -> List[RefrainGroup]:
    buckets: Dict[str, List[tuple[int, str]]] = {}
    for idx, line in enumerate(lines, 1):
        toks = [_normalise_token(t) for t in _tokens(line)]
        if len(toks) < 3:
            continue
        key = " ".join(toks[:3])
        buckets.setdefault(key, []).append((idx, line))

    return [
        RefrainGroup(
            key=key,
            line_indices=[idx for idx, _ in rows],
            texts=[text for _, text in rows],
        )
        for key, rows in buckets.items()
        if len(rows) >= 2
    ]


def _motif_counts(lines: Iterable[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for line in lines:
        for token in _content_tokens(line):
            counts[token] = counts.get(token, 0) + 1
    return {token: count for token, count in sorted(counts.items()) if count >= 3}


def _deep_structures(lines: List[str]) -> List[DeepStructure]:
    out: List[DeepStructure] = []
    for key, title, terms in DEEP_STRUCTURE_RULES:
        line_indices: List[int] = []
        evidence_terms: List[str] = []
        for idx, line in enumerate(lines, 1):
            normalised = _normalised_line(line)
            token_set = set(normalised.split())
            hits = [term for term in terms if _matches_term(token_set, normalised, term)]
            if not hits:
                continue
            line_indices.append(idx)
            for hit in hits:
                clean = hit.rstrip("*")
                if clean not in evidence_terms:
                    evidence_terms.append(clean)
        if line_indices:
            out.append(
                DeepStructure(
                    key=key,
                    title=title,
                    line_indices=line_indices,
                    evidence_terms=evidence_terms,
                )
            )
    return out


def _refrain_role(text: str) -> str:
    normalised = _normalised_line(text)
    if "leicht nehmen" in normalised or "probleme" in normalised and "nehmen" in normalised:
        return "problem_as_wound"
    if "begegnen" in normalised:
        return "life_confrontation"
    if "dich als leben erleben" in normalised:
        return "nondual_identity"
    if "wahrheit erkennst" in normalised:
        return "truth_recognition"
    if "wahrheit kannst" in normalised:
        return "truth_confrontation"
    if "wahrheit verbrennt" in normalised:
        return "truth_burns_lie"
    return "variant"


def _refrain_evolutions(groups: List[RefrainGroup]) -> List[RefrainEvolution]:
    evolutions: List[RefrainEvolution] = []
    for group in groups:
        stages = [
            RefrainStage(line_index=idx, text=text, role=_refrain_role(text))
            for idx, text in zip(group.line_indices, group.texts)
        ]
        roles = {stage.role for stage in stages}
        if len(roles) < 2:
            continue
        evolutions.append(RefrainEvolution(key=group.key, stages=stages))
    return evolutions


def _question_key(line: str) -> str | None:
    normalised = _normalised_line(line)
    if "wer entscheidet" in normalised:
        return "agency"
    if "wessen werten" in normalised:
        return "value_origin"
    if "marionetten" in normalised or "konzepte" in normalised:
        return "conditioned_self"
    if "körper mit seele" in normalised or "seele mit körper" in normalised:
        return "body_soul_polarity"
    if "trennung illusion" in normalised:
        return "separation_illusion"
    if "spiegel" in normalised and "welt" in normalised:
        return "nondual_mirror"
    return None


def _question_arc(lines: List[str]) -> List[QuestionMove]:
    arc: List[QuestionMove] = []
    seen: set[tuple[str, int]] = set()
    for idx, line in enumerate(lines, 1):
        if "?" not in line:
            continue
        key = _question_key(line)
        if key is None:
            continue
        marker = (key, idx)
        if marker in seen:
            continue
        seen.add(marker)
        arc.append(QuestionMove(key=key, line_index=idx, text=line))
    return arc


def _contains_ordered(tokens: List[str], pattern: List[str]) -> bool:
    pos = 0
    for token in tokens:
        if token == pattern[pos]:
            pos += 1
            if pos == len(pattern):
                return True
    return False


def _rhetorical_devices(lines: List[str], refrain_groups: List[RefrainGroup]) -> List[RhetoricalDevice]:
    devices: List[RhetoricalDevice] = []

    for group in refrain_groups:
        if len(group.line_indices) >= 3:
            devices.append(
                RhetoricalDevice(
                    kind="anaphoric_refrain",
                    line_indices=group.line_indices,
                    evidence=group.texts,
                    description=f"Wiederkehrender Zeilenanfang: {group.key}",
                )
            )

    for idx, line in enumerate(lines, 1):
        normalised = _normalised_line(line)
        tokens = normalised.split()

        if _contains_ordered(tokens, ["körper", "seele", "seele", "körper"]):
            devices.append(
                RhetoricalDevice(
                    kind="body_soul_chiasmus",
                    line_indices=[idx],
                    evidence=[line],
                    description="Kreuzstellung von Körper und Seele.",
                )
            )

        if _contains_ordered(tokens, ["seele", "körper", "körper", "seele"]):
            devices.append(
                RhetoricalDevice(
                    kind="body_soul_chiasmus",
                    line_indices=[idx],
                    evidence=[line],
                    description="Umgekehrte Kreuzstellung von Seele und Körper.",
                )
            )

        if "wahrheit" in tokens and any(t in tokens for t in ("lügen", "lüge", "betrügen")):
            devices.append(
                RhetoricalDevice(
                    kind="truth_lie_antithesis",
                    line_indices=[idx],
                    evidence=[line],
                    description="Wahrheit und Lüge werden als Gegenkräfte gekoppelt.",
                )
            )

        if "spiegel" in tokens and "welt" in tokens and "reflektieren" in tokens:
            devices.append(
                RhetoricalDevice(
                    kind="mirror_koan",
                    line_indices=[idx],
                    evidence=[line],
                    description="Koan-artige Spiegel-Frage gegen ein isoliertes Selbst.",
                )
            )

        if "muster" in tokens and ("entdecken" in tokens or "durchbrechen" in tokens):
            devices.append(
                RhetoricalDevice(
                    kind="process_parallelism",
                    line_indices=[idx],
                    evidence=[line],
                    description="Handlungskette über wiederholtes Leitwort.",
                )
            )

        if "geschehen" in tokens and tokens.count("geschehen") >= 2:
            devices.append(
                RhetoricalDevice(
                    kind="self_reflexive_repetition",
                    line_indices=[idx],
                    evidence=[line],
                    description="Dasselbe Verb reflektiert Subjekt und Prozess.",
                )
            )

        if "traumleben" in tokens and "traum" in tokens:
            devices.append(
                RhetoricalDevice(
                    kind="dream_frame_turn",
                    line_indices=[idx],
                    evidence=[line],
                    description="Traumleben kippt in den erlebten Traum.",
                )
            )

    return devices


def _echo_roots(token: str) -> set[str]:
    norm = _normalise_token(token)
    if len(norm) < 4 or norm in FUNCTION_WORDS:
        return set()
    roots = {norm}
    for suffix in ("ungen", "ende", "enden", "est", "ern", "en", "em", "er", "es", "e", "t"):
        if norm.endswith(suffix) and len(norm) - len(suffix) >= 5:
            roots.add(norm[: -len(suffix)])
            break
    for prefix in ("be", "ge", "ver", "zer", "er"):
        if norm.startswith(prefix) and len(norm) - len(prefix) >= 4:
            roots.add(norm[len(prefix):])
    if norm.startswith("selbst"):
        roots.add("selbst")
    if norm.startswith("traum"):
        roots.add("traum")
    return {root for root in roots if len(root) >= 4}


def _echo_stem(left: str, right: str) -> str | None:
    left_roots = _echo_roots(left)
    right_roots = _echo_roots(right)
    shared = sorted(left_roots & right_roots, key=len, reverse=True)
    if shared:
        return shared[0]
    for a in sorted(left_roots, key=len):
        for b in sorted(right_roots, key=len):
            if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
                return a if len(a) <= len(b) else b
    return None


def _echo_patterns(lines: List[str]) -> List[EchoPattern]:
    out: List[EchoPattern] = []
    for idx, line in enumerate(lines, 1):
        buckets: Dict[str, List[str]] = {}
        tokens = _tokens(line)
        for left_i, left in enumerate(tokens):
            for right in tokens[left_i + 1:]:
                stem = _echo_stem(left, right)
                if stem is None:
                    continue
                buckets.setdefault(stem, []).extend([left, right])
        for stem, words in buckets.items():
            unique_words: List[str] = []
            seen: set[str] = set()
            for word in words:
                key = _normalise_token(word)
                if key in seen:
                    continue
                seen.add(key)
                unique_words.append(word)
            if len(unique_words) < 2 and len(words) < 2:
                continue
            evidence_words = unique_words if len(unique_words) >= 2 else words[:2]
            out.append(
                EchoPattern(
                    kind="morphological_echo",
                    line_index=idx,
                    words=evidence_words,
                    stem=stem,
                )
            )
    return out


def _line_indices_matching(lines: List[str], terms: tuple[str, ...]) -> List[int]:
    out: List[int] = []
    for idx, line in enumerate(lines, 1):
        normalised = _normalised_line(line)
        token_set = set(normalised.split())
        if any(_matches_term(token_set, normalised, term) for term in terms):
            out.append(idx)
    return out


def _specific_nondual_lines(lines: List[str]) -> List[int]:
    out: List[int] = []
    for idx, line in enumerate(lines, 1):
        normalised = _normalised_line(line)
        token_set = set(normalised.split())
        direct = any(
            _matches_term(token_set, normalised, term)
            for term in ("dich als leben erleben", "ungetrennt", "wunder", "unverändert", "existieren")
        )
        mirror_koan = {"spiegel", "welt", "reflektieren"} <= token_set
        if direct or mirror_koan:
            out.append(idx)
    return out


def _structural_arcs(lines: List[str]) -> List[StructuralArc]:
    stage_specs: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        (
            "survival_and_wound",
            "Überleben, Körperwunde und Prägung",
            ("wehwehchen", "schäden", "täterintrojekten", "traumata", "narben"),
        ),
        (
            "conditioning_and_repetition",
            "Bedingtheit, Wiederholung und Karma",
            ("marionetten", "regeln", "fehlerketten", "karma", "pech"),
        ),
        (
            "integration_and_confrontation",
            "Schattenintegration und Konfrontation",
            ("integriere", "schatten*", "fragmente", "ängsten", "kämpfe", "hölle"),
        ),
        (
            "stillness_and_witness",
            "Stille, Einsicht und innerer Zeuge",
            ("stille", "trennung", "illusion", "integrität", "zeugen", "kritiker"),
        ),
        (
            "nondual_resolution",
            "Nicht-duale Auflösung",
            ("dich als leben erleben", "ungetrennt", "wunder", "unverändert", "existieren"),
        ),
    )

    stages = []
    for key, title, terms in stage_specs:
        line_indices = (
            _specific_nondual_lines(lines)
            if key == "nondual_resolution"
            else _line_indices_matching(lines, terms)
        )
        stages.append(StructuralStage(key=key, title=title, line_indices=line_indices))
    first_lines = [stage.line_indices[0] for stage in stages if stage.line_indices]
    return [
        StructuralArc(
            key="trauma_to_nonduality_spiral",
            title="Vom verkörperten Trauma zur Nicht-Trennung",
            stages=stages,
            complete=all(stage.line_indices for stage in stages),
            ordered=first_lines == sorted(first_lines),
        )
    ]


def _bypassing_audit(lines: List[str]) -> BypassingAudit:
    trauma_lines = _line_indices_matching(
        lines,
        ("wehwehchen", "schäden", "täterintrojekten", "traumata", "narben", "nervensysteme"),
    )
    integration_lines = _line_indices_matching(
        lines,
        ("integriere", "schatten*", "fragmente", "ängsten", "kämpfe", "hölle"),
    )
    nondual_lines = _specific_nondual_lines(lines)

    first_trauma = trauma_lines[0] if trauma_lines else None
    first_integration = integration_lines[0] if integration_lines else None
    first_nondual = nondual_lines[0] if nondual_lines else None

    return BypassingAudit(
        trauma_before_nondual=(
            first_trauma is not None and first_nondual is not None and first_trauma < first_nondual
        ),
        integration_before_nondual=(
            first_integration is not None and first_nondual is not None and first_integration < first_nondual
        ),
        first_trauma_line=first_trauma,
        first_integration_line=first_integration,
        first_specific_nondual_line=first_nondual,
    )


def _coverage_item(key: str, label: str, covered: bool, evidence: Iterable[str]) -> CoverageItem:
    return CoverageItem(
        key=key,
        label=label,
        covered=covered,
        evidence=list(evidence)[:8],
    )


def _completion_audit(
    line_analyses: List[RapLineAnalysis],
    terminal_chains: List[RhymeChain],
    refrain_groups: List[RefrainGroup],
    deep_structures: List[DeepStructure],
    refrain_evolutions: List[RefrainEvolution],
    question_arc: List[QuestionMove],
    rhetorical_devices: List[RhetoricalDevice],
    echo_patterns: List[EchoPattern],
    sections: List[LyricSection],
    structural_arcs: List[StructuralArc],
    bypassing_audit: BypassingAudit,
) -> CompletionAudit:
    deep_keys = {structure.key for structure in deep_structures}
    device_keys = {device.kind for device in rhetorical_devices}
    question_keys = {move.key for move in question_arc}
    tag_counts: Dict[str, int] = {}
    for line in line_analyses:
        for tag in line.window_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    echo_words = {
        word.lower()
        for echo in echo_patterns
        for word in echo.words
    }
    line_texts = [line.text for line in line_analyses]
    structural_arc = structural_arcs[0] if structural_arcs else None

    def bucket_evidence(label: str, terms: tuple[str, ...]) -> str:
        hits = _line_indices_matching(line_texts, terms)
        return f"{label}:{hits[0] if hits else '-'}"

    register_buckets = (
        ("clinical", ("täterintrojekten", "traumata", "bindungsmuster", "nervensysteme")),
        ("philosophical", ("wille", "freiheit", "trennung", "illusion", "spiegel")),
        ("spiritual", ("stille", "jetzt", "hier", "ungetrennt", "wunder")),
        ("biographical", ("vater", "kindheit", "selbstliebe", "narben")),
        ("social", ("generationen", "regeln", "gesetzen", "weltfrieden")),
    )
    embodied_buckets = (
        ("body", ("leib", "körper", "wehwehchen", "schäden", "nervensysteme")),
        ("psyche", ("täterintrojekten", "schatten*", "fragmente", "projektionen", "kritiker")),
        ("thinking", ("denken", "konzepte", "wille", "freiheit", "trennung")),
        ("relation", ("grenzen", "nähe", "werte", "vater", "kindheit")),
        ("nondual", ("ungetrennt", "wunder", "jetzt", "hier", "existieren")),
    )

    items = [
        _coverage_item(
            "lyric_sections",
            "Hook/Part-Architektur ist erhalten",
            len(sections) == 6 and sections[0].start_line == 1 and sections[-1].end_line == 72,
            [f"{section.name}:{section.start_line}-{section.end_line}" for section in sections],
        ),
        _coverage_item(
            "diphthong_anchor_chain",
            "Diphthong-Ankerketten werden erkannt",
            tag_counts.get("diphthong_anchor_chain", 0) >= 1,
            [line.text for line in line_analyses if "diphthong_anchor_chain" in line.window_tags],
        ),
        _coverage_item(
            "front_vowel_band",
            "Frontvokal-Bänder werden als Klangfarbe erkannt",
            tag_counts.get("front_vowel_band", 0) >= 40,
            [str(tag_counts.get("front_vowel_band", 0))],
        ),
        _coverage_item(
            "tight_consonant_grip",
            "Konsonantisches Gerüst wird erkannt",
            tag_counts.get("tight_consonant_grip", 0) >= 40,
            [str(tag_counts.get("tight_consonant_grip", 0))],
        ),
        _coverage_item(
            "internal_rhyme_density",
            "Binnenreime und Slant-Ketten werden songweit erkannt",
            sum(len(line.internal_rhyme_chains) for line in line_analyses) >= 100,
            [str(sum(len(line.internal_rhyme_chains) for line in line_analyses))],
        ),
        _coverage_item(
            "terminal_rhyme_density",
            "Endreim-Cluster werden songweit erkannt",
            len(terminal_chains) >= 40,
            [str(len(terminal_chains))],
        ),
        _coverage_item(
            "refrain_transformation",
            "Refrain wiederholt sich nicht nur, sondern transformiert Bedeutung",
            any(
                evolution.key == "leib seele probleme"
                and [stage.role for stage in evolution.stages][:3]
                == ["problem_as_wound", "life_confrontation", "nondual_identity"]
                for evolution in refrain_evolutions
            ),
            [
                f"{evolution.key}:{','.join(stage.role for stage in evolution.stages)}"
                for evolution in refrain_evolutions
            ],
        ),
        _coverage_item(
            "integrated_registers",
            "Klinische, philosophische, spirituelle, biografische und soziale Register greifen ineinander",
            all(_line_indices_matching(line_texts, terms) for _, terms in register_buckets),
            [bucket_evidence(label, terms) for label, terms in register_buckets],
        ),
        _coverage_item(
            "embodied_layer_fusion",
            "Körper, Psyche, Denken, Beziehung und Nicht-Dualität bleiben gekoppelt",
            all(_line_indices_matching(line_texts, terms) for _, terms in embodied_buckets),
            [bucket_evidence(label, terms) for label, terms in embodied_buckets],
        ),
        _coverage_item(
            "conditioned_action_without_blame",
            "Fremdbestimmung erscheint als Prägungskette statt simple Schuldlogik",
            bool(
                _line_indices_matching(line_texts, ("marionetten",))
                and _line_indices_matching(line_texts, ("regeln", "fehlerketten"))
                and _line_indices_matching(line_texts, ("vater", "affekt"))
                and _line_indices_matching(line_texts, ("karma", "pech"))
            ),
            [
                bucket_evidence("marionettes", ("marionetten",)),
                bucket_evidence("rules", ("regeln", "fehlerketten")),
                bucket_evidence("affect", ("vater", "affekt")),
                bucket_evidence("karma", ("karma", "pech")),
            ],
        ),
        _coverage_item(
            "embodiment_wound",
            "Leib-Seele-Achse als verkörperte Wunde",
            "embodiment_wound" in deep_keys,
            next((s.evidence_terms for s in deep_structures if s.key == "embodiment_wound"), []),
        ),
        _coverage_item(
            "shadow_integration",
            "Schattenintegration statt Flucht",
            "shadow_integration" in deep_keys,
            next((s.evidence_terms for s in deep_structures if s.key == "shadow_integration"), []),
        ),
        _coverage_item(
            "conditioning_will_karma",
            "Wille, Karma und Bedingtheit",
            "conditioning_will_karma" in deep_keys,
            next((s.evidence_terms for s in deep_structures if s.key == "conditioning_will_karma"), []),
        ),
        _coverage_item(
            "stillness_insight",
            "Stille und Einsicht als Wendepunkt",
            "stillness_insight" in deep_keys,
            next((s.evidence_terms for s in deep_structures if s.key == "stillness_insight"), []),
        ),
        _coverage_item(
            "witness_critic",
            "Innerer Zeuge relativiert inneren Kritiker",
            "witness_critic" in deep_keys,
            next((s.evidence_terms for s in deep_structures if s.key == "witness_critic"), []),
        ),
        _coverage_item(
            "nondual_simplicity",
            "Nicht-duale Einfachheit erscheint am Ende",
            "nondual_simplicity" in deep_keys,
            next((s.evidence_terms for s in deep_structures if s.key == "nondual_simplicity"), []),
        ),
        _coverage_item(
            "question_arc",
            "Fragebogen bewegt sich von Agency zu Spiegel-Koan",
            {"agency", "value_origin", "conditioned_self", "body_soul_polarity", "nondual_mirror"} <= question_keys,
            [move.key for move in question_arc],
        ),
        _coverage_item(
            "body_soul_chiasmus",
            "Körper/Seele-Kreuzstellung wird erkannt",
            "body_soul_chiasmus" in device_keys,
            [
                device.evidence[0]
                for device in rhetorical_devices
                if device.kind == "body_soul_chiasmus"
            ],
        ),
        _coverage_item(
            "mirror_koan",
            "Spiegel-Metapher wird als Koan erkannt",
            "mirror_koan" in device_keys,
            [
                device.evidence[0]
                for device in rhetorical_devices
                if device.kind == "mirror_koan"
            ],
        ),
        _coverage_item(
            "truth_lie_antithesis",
            "Wahrheit/Lüge-Antithese wird erkannt",
            "truth_lie_antithesis" in device_keys,
            [
                device.evidence[0]
                for device in rhetorical_devices
                if device.kind == "truth_lie_antithesis"
            ],
        ),
        _coverage_item(
            "morphological_echoes",
            "Morphologische Echos und Wortwurzelspiel werden erkannt",
            {"beenden", "enden", "traumleben", "traum"} <= echo_words,
            [f"{echo.stem}:{'/'.join(echo.words)}" for echo in echo_patterns],
        ),
        _coverage_item(
            "ordered_spiral",
            "Gesamtbewegung ist vollständig und geordnet",
            structural_arc is not None and structural_arc.complete and structural_arc.ordered,
            [
                f"{stage.key}:{stage.line_indices[0] if stage.line_indices else '-'}"
                for stage in (structural_arc.stages if structural_arc else [])
            ],
        ),
        _coverage_item(
            "anti_bypassing",
            "Körper/Trauma und Integration stehen vor Nicht-Dualität",
            bypassing_audit.trauma_before_nondual and bypassing_audit.integration_before_nondual,
            [
                f"trauma={bypassing_audit.first_trauma_line}",
                f"integration={bypassing_audit.first_integration_line}",
                f"nondual={bypassing_audit.first_specific_nondual_line}",
            ],
        ),
    ]

    covered_count = sum(1 for item in items if item.covered)
    missing = [item.key for item in items if not item.covered]
    return CompletionAudit(
        complete=not missing,
        covered_count=covered_count,
        total_count=len(items),
        missing_keys=missing,
        items=items,
    )


def _technique_inventory(
    line_analyses: List[RapLineAnalysis],
    terminal_chains: List[RhymeChain],
    refrain_groups: List[RefrainGroup],
    rhetorical_devices: List[RhetoricalDevice],
    echo_patterns: List[EchoPattern],
) -> TechniqueInventory:
    tag_counts: Dict[str, int] = {}
    internal_chain_count = 0
    prefix_chain_count = 0
    for line in line_analyses:
        for tag in line.window_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        internal_chain_count += len(line.internal_rhyme_chains)
        prefix_chain_count += len(line.prefix_chains)
    return TechniqueInventory(
        window_tag_counts=dict(sorted(tag_counts.items())),
        internal_chain_count=internal_chain_count,
        terminal_chain_count=len(terminal_chains),
        refrain_group_count=len(refrain_groups),
        prefix_chain_count=prefix_chain_count,
        rhetorical_device_count=len(rhetorical_devices),
        echo_pattern_count=len(echo_patterns),
    )


def analyze_rap_text(text: str) -> RapTextAnalysis:
    lines = extract_lyric_lines(text)
    sections = extract_lyric_sections(text)
    line_analyses: List[RapLineAnalysis] = []

    for idx, line in enumerate(lines, 1):
        windows = extract_default_windows(build_line_parse(line), idx)
        line_analyses.append(
            RapLineAnalysis(
                line_index=idx,
                text=line,
                window_tags=sorted({tag for w in windows for tag in w.technique_tags}),
                flow_shapes=sorted({w.flow_shape for w in windows}),
                parallel_shapes=sorted({w.parallel_shape for w in windows}),
                anchor_nuclei=[v for w in windows for v in w.anchor_nuclei],
                internal_rhyme_chains=_internal_rhyme_chains(line, idx),
                prefix_chains=_prefix_chains(line),
            )
        )

    terminal_chains = _terminal_rhyme_chains(lines)
    refrain_groups = _refrain_groups(lines)
    rhetorical_devices = _rhetorical_devices(lines, refrain_groups)
    echo_patterns = _echo_patterns(lines)
    structural_arcs = _structural_arcs(lines)
    bypassing_audit = _bypassing_audit(lines)
    deep_structures = _deep_structures(lines)
    refrain_evolutions = _refrain_evolutions(refrain_groups)
    question_arc = _question_arc(lines)
    completion_audit = _completion_audit(
        line_analyses,
        terminal_chains,
        refrain_groups,
        deep_structures,
        refrain_evolutions,
        question_arc,
        rhetorical_devices,
        echo_patterns,
        sections,
        structural_arcs,
        bypassing_audit,
    )

    return RapTextAnalysis(
        lines=line_analyses,
        terminal_rhyme_chains=terminal_chains,
        refrain_groups=refrain_groups,
        motif_counts=_motif_counts(lines),
        deep_structures=deep_structures,
        refrain_evolutions=refrain_evolutions,
        question_arc=question_arc,
        rhetorical_devices=rhetorical_devices,
        echo_patterns=echo_patterns,
        sections=sections,
        structural_arcs=structural_arcs,
        bypassing_audit=bypassing_audit,
        completion_audit=completion_audit,
        technique_inventory=_technique_inventory(
            line_analyses,
            terminal_chains,
            refrain_groups,
            rhetorical_devices,
            echo_patterns,
        ),
    )
