"""End-to-end local workflow for the personal rhyme library."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from app.services.local_rhyme_model import rerank_with_local_model, train_local_rhyme_model
from app.services.user_text_importer import (
    DATA_ROOT,
    DB_PATH,
    INBOX_DIR,
    TRAINING_DIR,
    build_training_dataset,
    refresh_user_text_database,
    search_user_rhymes,
)


def run_personal_rhyme_pipeline(
    query: str,
    inbox_dir: Path = INBOX_DIR,
    data_root: Path = DATA_ROOT,
    prefer_pages_export: bool = True,
    context_radius: int = 12,
    max_examples: int = 2000,
    min_pair_score: float = 0.58,
    limit: int = 25,
    min_score: float = 0.40,
) -> Dict[str, Any]:
    db_path = data_root / DB_PATH.name
    training_dir = data_root / TRAINING_DIR.name
    training_jsonl = training_dir / "rhyme_training.jsonl"
    model_path = training_dir / "local_rhyme_model.json"

    import_summary = refresh_user_text_database(
        inbox_dir=inbox_dir,
        data_root=data_root,
        prefer_pages_export=prefer_pages_export,
        context_radius=context_radius,
    )
    training_summary = build_training_dataset(
        db_path=db_path,
        output_path=training_jsonl,
        max_examples=max_examples,
        include_text_lines=True,
    )
    model_summary = train_local_rhyme_model(
        db_path=db_path,
        model_path=model_path,
        min_pair_score=min_pair_score,
    )

    search_summary = search_user_rhymes(
        query=query,
        db_path=db_path,
        limit=max(limit, 1),
        min_score=min_score,
        rerank=False,
    )
    rerank_summary = rerank_with_local_model(
        query=query,
        candidates=search_summary.get("results", []),
        model_path=model_path,
    )

    return {
        "status": "ok" if model_summary.get("status") == "ok" else model_summary.get("status", "incomplete"),
        "query": query,
        "import": asdict(import_summary),
        "training": training_summary,
        "model": model_summary,
        "search": {
            "total_candidates": search_summary.get("total_candidates", 0),
            "retrieved_candidates": search_summary.get("retrieved_candidates", 0),
            "rerank": {
                key: value
                for key, value in rerank_summary.items()
                if key != "results"
            },
            "results": rerank_summary.get("results", [])[:limit],
        },
    }
