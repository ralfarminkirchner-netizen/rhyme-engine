#!/usr/bin/env python3
"""Direct access to the private song repository and reviewed passage memory."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.song_archive import (sync_configured_archive, record_feedback,
                                      search_passages, export_reviewed_training)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inbox", type=Path, default=Path("app/data/user_texts/inbox"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sync")
    commands.add_parser("export-training")
    search = commands.add_parser("search")
    search.add_argument("query")
    feedback = commands.add_parser("feedback")
    feedback.add_argument("document_id")
    feedback.add_argument("version")
    feedback.add_argument("start", type=int)
    feedback.add_argument("end", type=int)
    feedback.add_argument("axis", choices=["meaning", "rhyme", "rhythm"])
    feedback.add_argument("rating", type=float)
    feedback.add_argument("--comment", default="")
    args = parser.parse_args()
    if args.command == "sync":
        result = sync_configured_archive(args.inbox)
    elif args.command == "search":
        result = search_passages(args.inbox, args.query)
    elif args.command == "export-training":
        result = export_reviewed_training(args.inbox)
    else:
        result = record_feedback(args.inbox, args.document_id, args.version, args.start,
                                 args.end, args.axis, args.rating, args.comment)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result.get("status") == "not_configured" else 0


if __name__ == "__main__":
    raise SystemExit(main())
