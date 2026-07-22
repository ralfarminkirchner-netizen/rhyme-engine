#!/usr/bin/env python3
"""
Spielt den Export aus dem HTML-Bewertungsbogen (reim_bewertung_export.json)
ins lokale Feedback-Training ein. Schliesst den Lern-Kreis:

    HTML-Bogen  ->  Export-JSON  ->  save_rhyme_feedback()  ->  Pattern-Prior

Privatsphaere: alles lokal. Kommentare werden gespeichert, aber NIE an externe
APIs geschickt (siehe ai_reranker-Payload).

Aufruf:
    python3 scripts/ingest_rating_feedback.py <pfad/zur/reim_bewertung_export.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.services.user_text_importer import DB_PATH, save_rhyme_feedback


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Aufruf: python3 scripts/ingest_rating_feedback.py <export.json>")
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"Datei nicht gefunden: {path}")
        return 2
    rows = json.loads(path.read_text("utf-8"))
    if not isinstance(rows, list):
        print("Unerwartetes Format: erwarte JSON-Liste.")
        return 2

    ok = skipped = 0
    for row in rows:
        try:
            res = save_rhyme_feedback(
                query=row["query"],
                source_title=row["source_title"],
                line_no=int(row["line_no"]),
                phrase=row["phrase"],
                rating=int(row["rating"]),
                comment=str(row.get("comment", "")),
                db_path=DB_PATH,
            )
        except (KeyError, ValueError, TypeError) as exc:
            skipped += 1
            print(f"  uebersprungen ({exc}): {row!r:.80}")
            continue
        if res.get("status") == "ok":
            ok += 1
        else:
            skipped += 1
            print(f"  Fehler: {res.get('warning')}")

    print(f"\nFertig: {ok} Bewertungen gespeichert, {skipped} uebersprungen.")
    print("Pattern-Prior + exakte Feedbacks wirken ab dem naechsten Such-Aufruf.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
