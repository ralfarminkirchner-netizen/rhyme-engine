"""Check a private local graph corpus without putting its text in this repo.

Usage: .venv/bin/python scripts/check_graph_cases.py /path/to/private-cases.json
The JSON contains {"cases": [{"name": "...", "request": {...},
"expected": {"syllable_counts": [...], "min_edges": 1,
"all_lines_linked": true, "single_component": true,
"no_unknown_phones": true, "no_manual_overrides": true}}]}.
Only case names, counts and a text fingerprint are printed, never the text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.rhyme_graph import GraphBuildRequest
from app.services.rhyme_graph import build_rhyme_graph


def check_case(case: dict) -> dict:
    request = GraphBuildRequest.model_validate(case["request"])
    expected = case.get("expected", {})
    if expected.get("no_manual_overrides") and request.overrides:
        raise AssertionError("The case must work without manual pronunciation overrides.")
    graph = build_rhyme_graph(request)
    counts = [len(line.phonetic_syllables) for line in graph.lines]
    if "syllable_counts" in expected and counts != expected["syllable_counts"]:
        raise AssertionError(f"Unexpected syllable counts: {counts}")
    if len(graph.edges) < expected.get("min_edges", 0):
        raise AssertionError(f"Too few relationships: {len(graph.edges)}")
    nodes = {node.id: node for node in graph.nodes}
    degree = {line.line_index: 0 for line in graph.lines if line.words}
    neighbors = {line: set() for line in degree}
    for edge in graph.edges:
        left, right = nodes[edge.source].line_index, nodes[edge.target].line_index
        if left == right:
            continue
        degree[left] += 1
        degree[right] += 1
        neighbors[left].add(right)
        neighbors[right].add(left)
    if expected.get("all_lines_linked") and any(value == 0 for value in degree.values()):
        raise AssertionError(f"An input line remains isolated: {degree}")
    if expected.get("single_component") and neighbors:
        reached, queue = set(), [next(iter(neighbors))]
        while queue:
            line = queue.pop()
            if line in reached:
                continue
            reached.add(line)
            queue.extend(neighbors[line] - reached)
        if len(reached) != len(neighbors):
            raise AssertionError("Input lines do not participate in one connected network of direct matches.")
    if expected.get("no_unknown_phones") and any("unbekannte Laut" in warning for warning in graph.warnings):
        raise AssertionError("The analysis still contains unknown phone symbols.")
    return {
        "name": case.get("name", "unnamed"), "status": "passed",
        "text_sha256": hashlib.sha256(request.text.encode("utf-8")).hexdigest(),
        "syllable_counts": counts, "nodes": len(graph.nodes), "edges": len(graph.edges),
        "line_degrees": degree, "analysis_version": graph.version,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args()
    cases = json.loads(args.corpus.read_text(encoding="utf-8"))["cases"]
    failed = False
    for index, case in enumerate(cases):
        try:
            print(json.dumps(check_case(case), ensure_ascii=False))
        except (AssertionError, ValueError, KeyError) as error:
            failed = True
            # Pydantic's full ValidationError can include the private input.
            reason = str(error) if isinstance(error, AssertionError) else "Invalid local case input; inspect the private corpus locally."
            print(json.dumps({"name": case.get("name", f"case-{index}"), "status": "failed", "reason": reason}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
