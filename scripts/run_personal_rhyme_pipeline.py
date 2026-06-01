#!/usr/bin/env python3
"""Run the local personal rhyme pipeline without exposing private full texts."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.personal_rhyme_pipeline import run_personal_rhyme_pipeline


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import user texts, build private training data, train the local model, and run a reranked search.",
    )
    parser.add_argument("query", nargs="?", default="schattenkabinett")
    parser.add_argument("--inbox", type=Path, default=Path("app/data/user_texts/inbox"))
    parser.add_argument("--data-root", type=Path, default=Path("app/data/user_texts"))
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--min-score", type=float, default=0.40)
    parser.add_argument("--min-pair-score", type=float, default=0.58)
    parser.add_argument("--max-examples", type=int, default=2000)
    parser.add_argument("--no-pages-export", action="store_true")
    parser.add_argument("--show-phrases", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = run_personal_rhyme_pipeline(
        query=args.query,
        inbox_dir=args.inbox,
        data_root=args.data_root,
        prefer_pages_export=not args.no_pages_export,
        max_examples=args.max_examples,
        min_pair_score=args.min_pair_score,
        limit=args.limit,
        min_score=args.min_score,
    )

    import_summary = result["import"]
    training = result["training"]
    model = result["model"]
    search = result["search"]

    print(f"Status:              {result['status']}")
    print(f"Query:               {result['query']}")
    print(f"Quellen importiert:  {import_summary['imported_count']}/{import_summary['source_count']}")
    print(f"Textzeilen:          {import_summary['line_count']}")
    print(f"Reim-Units:          {import_summary['rhyme_unit_count']}")
    print(f"Reim-Paare:          {import_summary['rhyme_pair_count']}")
    print(f"Quotes:              {import_summary['quote_count']}")
    print(f"Trainingsbeispiele:  {training['example_count']}")
    print(f"Trainingsdatei:      {training['output_path']}")
    print(f"Modellpaare:         {model['pair_count']}")
    print(f"Modelldatei:         {model['model_path']}")
    print(f"Reranker:            {search['rerank'].get('provider')} ({search['rerank'].get('enabled')})")

    if model.get("warning"):
        print(f"Modell-Warnung:      {model['warning']}")
    if training.get("warning"):
        print(f"Training-Warnung:    {training['warning']}")

    results = search.get("results", [])
    if results:
        print("Top-Phrasen:")
        for index, row in enumerate(results[: args.limit], 1):
            score = row.get("learned_score", row.get("score", 0.0))
            phrase = row["phrase"] if args.show_phrases else "<verborgen>"
            print(f"  {index:>2}. {phrase}  {score:.3f}  {row.get('source_title', '')}:{row.get('line_no', '')}")
    else:
        print("Top-Phrasen:          keine")

    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
