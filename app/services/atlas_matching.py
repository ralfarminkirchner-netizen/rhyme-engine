"""Compare complete, ordered pronunciations in the atlas' sound space.

Scores express this transparent comparison rule, not a probability that a
performed rhyme works. Initial consonants are never a gate; ordered vowel
anchors, the extent of the match, cadence, and stress contribute separately.
"""
from __future__ import annotations

from math import ceil


_NEAR_FAMILIES = {
    frozenset(pair): value for pair, value in [
        (("e", "ei"), .86), (("o", "ou"), .86),
        (("a", "ai"), .73), (("a", "au"), .72),
        (("i", "ei"), .68), (("i", "ai"), .51),
        (("u", "ou"), .68), (("u", "au"), .54),
        (("oe", "e"), .76), (("ue", "i"), .74),
        (("ue", "u"), .74), (("oe", "o"), .67),
        (("oe", "ue"), .52), (("i", "e"), .48),
        (("u", "o"), .48), (("a", "o"), .35),
        (("ai", "ei"), .69), (("ai", "oi"), .64),
        (("au", "ou"), .66), (("oi", "ei"), .58),
    ]
}
_CONSONANT_GROUPS = [
    (frozenset("pb"), .87), (frozenset("td"), .87),
    (frozenset("kgɡ"), .87), (frozenset("fv"), .87),
    (frozenset({"s", "z", "ʃ", "ʒ", "t͡s", "t͡ʃ", "d͡ʒ"}), .68),
    (frozenset("mnŋɱɲɴ"), .82), (frozenset("lrʁɹɾɽʀ"), .69),
    (frozenset("mnŋɱɲɴlrʁɹɾɽʀ"), .55),
    (frozenset("xçhχħɦ"), .66), (frozenset("pbtdkgɡ"), .39),
]


def candidate_families(family: str, mode: str = "dirty") -> list[str]:
    """Index prefilter containing every family the terminal gate can accept."""
    if mode == "strict":
        return [family]
    threshold = .62 if mode == "balanced" else .50
    nearby = {other for pair, similarity in _NEAR_FAMILIES.items() if family in pair and similarity >= threshold for other in pair}
    return [family, *sorted(nearby - {family})]


def _nucleus_similarity(left: str, right: str, lf: str, rf: str) -> float:
    if not left or not right or not lf or not rf:
        return 0.0
    if left == right:
        return 1.0
    bare_left = left.replace("ː", "").replace("ˑ", "")
    bare_right = right.replace("ː", "").replace("ˑ", "")
    if bare_left == bare_right:
        return .97
    if lf == rf:
        return .88
    if "schwa" in (lf, rf):
        return .48
    return _NEAR_FAMILIES.get(frozenset((lf, rf)), .12)


def _phone_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    return max((score for phones, score in _CONSONANT_GROUPS if left in phones and right in phones), default=.10)


def _sequence_similarity(left: list[str], right: list[str]) -> float:
    """Small weighted edit distance for consonants; unlike nuclei, no gate."""
    if not left and not right:
        return 1.0
    if not left or not right:
        return .15
    previous = list(map(float, range(len(right) + 1)))
    for i, lp in enumerate(left, 1):
        current = [float(i)]
        for j, rp in enumerate(right, 1):
            current.append(min(
                previous[j] + 1, current[-1] + 1,
                previous[j - 1] + 1 - _phone_similarity(lp, rp),
            ))
        previous = current
    return max(0.0, 1 - previous[-1] / max(len(left), len(right)))


def _nucleus_index(syllable: list[str], nucleus: str) -> int:
    try:
        return syllable.index(nucleus)
    except ValueError:
        return -1


def _rhyme_core(syllables: list[list[str]], nuclei: list[str]) -> list[str]:
    start = _nucleus_index(syllables[0], nuclei[0])
    if start < 0:
        return []
    return list(syllables[0][start:]) + [phone for syllable in syllables[1:] for phone in syllable]


def _consonants(syllables: list[list[str]], nuclei: list[str]) -> list[str]:
    result = []
    for index, (syllable, nucleus) in enumerate(zip(syllables, nuclei)):
        position = _nucleus_index(syllable, nucleus)
        if index == 0:
            result.extend(syllable[position + 1:])
        else:
            result.extend(phone for at, phone in enumerate(syllable) if at != position)
    return result


def _coda(syllables: list[list[str]], nuclei: list[str]) -> list[str]:
    position = _nucleus_index(syllables[-1], nuclei[-1])
    return syllables[-1][position + 1:] if position >= 0 else []


def _stress_similarity(left: dict, right: dict, pairs: list[tuple[int, int]]) -> float:
    ls, rs = left.get("stress", []), right.get("stress", [])
    values = []
    for i, j in pairs:
        a, b = ls[i] if i < len(ls) else 0, rs[j] if j < len(rs) else 0
        if a and b:
            values.append(1.0 if a == b else .35)
        elif a or b:
            values.append(.65)
    # Unmarked sources supply no positive or negative stress evidence.
    return sum(values) / len(values) if values else .75


def _alignment(similarities: list[list[float]], n: int, m: int) -> list[tuple[int, int]]:
    """Match both endpoints and all shorter-side nuclei, in source order.

    Only the longer sequence can have internal insertions. This prevents a
    high-scoring suffix or a few cherry-picked vowels from becoming a claimed
    full-sequence match. There are at most two insertions at the call site.
    """
    if n == m:
        return [(index, index) for index in range(n)]
    # States hold the best score and path for the small interior band.
    states = {(1, 1): (similarities[0][0], [(0, 0)])}
    for i in range(1, n):
        for j in range(1, m):
            state = states.get((i, j))
            if state is None:
                continue
            score, path = state

            def update(ni: int, nj: int, value: float, pairs: list[tuple[int, int]]) -> None:
                if value > states.get((ni, nj), (-float("inf"), []))[0]:
                    states[(ni, nj)] = (value, pairs)

            if i < n - 1 and j < m - 1:
                update(i + 1, j + 1, score + similarities[i][j], path + [(i, j)])
            if n > m and i < n - 1 and i - j < n - m:
                update(i + 1, j, score, path)
            if m > n and j < m - 1 and j - i < m - n:
                update(i, j + 1, score, path)
    state = states.get((n - 1, m - 1))
    return state[1] + [(n - 1, m - 1)] if state else []


def compare_pronunciations(left: dict, right: dict, mode: str = "dirty") -> dict | None:
    """Compare full ordered ``parse_ipa`` results, without looking up a source.

    ``strict`` requires equal syllable counts and the identical phone sequence
    from the first nucleus. ``balanced`` allows nearby vowels at equal length.
    ``dirty`` also permits one or two internal extra syllables, while requiring
    distributed anchors. Stress and terminal consonants remain weighted signals.
    """
    if mode not in {"strict", "balanced", "dirty"}:
        raise ValueError("mode must be strict, balanced, or dirty")
    ls, rs = left.get("syllables", []), right.get("syllables", [])
    ln, rn = left.get("nuclei", []), right.get("nuclei", [])
    lf, rf = left.get("families", []), right.get("families", [])
    n, m = len(ls), len(rs)
    if not n or not m or len(ln) != n or len(rn) != m or len(lf) != n or len(rf) != m:
        return None
    if not all(ln) or not all(rn) or not all(lf) or not all(rf):
        return None
    if any(_nucleus_index(syllable, nucleus) < 0 for syllable, nucleus in zip(ls, ln)) or any(
        _nucleus_index(syllable, nucleus) < 0 for syllable, nucleus in zip(rs, rn)
    ):
        return None

    exact = n == m and _rhyme_core(ls, ln) == _rhyme_core(rs, rn)
    if exact:
        stress = _stress_similarity(left, right, [(i, i) for i in range(n)])
        return {
            "score": round(.96 + .04 * stress, 4), "kind": "exact", "matched_syllables": n,
            "reason": f"Gleiche Lautfolge ab dem ersten Silbenkern über {n} Silben.",
            "details": {
                "left_syllables": n, "right_syllables": m, "gap_count": 0,
                "nucleus_score": 1.0, "cadence_score": 1.0, "consonant_score": 1.0,
                "stress_score": round(stress, 4), "anchor_count": n,
                "alignment": [{"left": i, "right": i, "nucleus_similarity": 1.0} for i in range(n)],
            },
        }
    if mode == "strict":
        return None
    gaps = abs(n - m)
    if (mode == "balanced" and gaps) or gaps > 2:
        return None
    if gaps and (min(n, m) < 3 or min(n, m) / max(n, m) < .6):
        return None

    similarities = [[_nucleus_similarity(a, b, lf[i], rf[j]) for j, b in enumerate(rn)] for i, a in enumerate(ln)]
    pairs = _alignment(similarities, n, m)
    if not pairs:
        return None
    values = [similarities[i][j] for i, j in pairs]
    minimum_anchor = .62 if mode == "balanced" else .50
    if values[0] < minimum_anchor or values[-1] < minimum_anchor:
        return None
    count = len(pairs)
    anchors = sum(value >= .68 for value in values)
    required = 1 if count == 1 else max(2, ceil(count * (.75 if mode == "balanced" else .5)))
    if anchors < required:
        return None

    if count == 1:
        vowel_score = values[0]
    elif count == 2:
        vowel_score = .4 * values[0] + .6 * values[-1]
    else:
        vowel_score = .25 * values[0] + .35 * values[-1] + .4 * sum(values[1:-1]) / (count - 2)
    cadence = _sequence_similarity(_coda(ls, ln), _coda(rs, rn))
    consonants = _sequence_similarity(_consonants(ls, ln), _consonants(rs, rn))
    stress = _stress_similarity(left, right, pairs)
    # A single shared vowel cannot assert a monosyllabic rhyme across wholly
    # unrelated codas. Multisyllabic matches carry evidence elsewhere as well.
    if count == 1 and cadence < .38:
        return None
    if mode == "balanced":
        score = .67 * vowel_score + .15 * cadence + .12 * consonants + .06 * stress
        threshold = .76
    else:
        score = .74 * vowel_score + .11 * cadence + .10 * consonants + .05 * stress - .035 * gaps
        threshold = .66
    if score < threshold:
        return None
    return {
        "score": round(min(1.0, max(0.0, score)), 4), "matched_syllables": count,
        "kind": "flex" if gaps else "near",
        "reason": (
            f"Ähnliche geordnete Klangfolge über {count} Silben; "
            + (f"{gaps} zusätzliche Binnensilbe{'n' if gaps != 1 else ''} berücksichtigt."
               if gaps else "Anfang und Ende tragen gemeinsam die Verbindung.")
        ),
        "details": {
            "left_syllables": n, "right_syllables": m, "gap_count": gaps,
            "nucleus_score": round(vowel_score, 4), "cadence_score": round(cadence, 4),
            "consonant_score": round(consonants, 4), "stress_score": round(stress, 4),
            "anchor_count": anchors,
            "alignment": [
                {"left": i, "right": j, "nucleus_similarity": round(similarities[i][j], 4)}
                for i, j in pairs
            ],
        },
    }
