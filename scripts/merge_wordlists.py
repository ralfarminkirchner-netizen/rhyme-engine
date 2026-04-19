#!/usr/bin/env python3
"""Kombiniert mehrere Wortlisten zu einer deduplizierten Gesamtliste."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.word_loader import WordLoader

DATA_DIR = Path(__file__).parent.parent / "app" / "data"

SOURCES = [
    DATA_DIR / "de_50k.txt",
    DATA_DIR / "deu_news_2021_100K.txt",
]
OUTPUT  = DATA_DIR / "de_merged.txt"


def main() -> None:
    existing = [s for s in SOURCES if s.exists()]
    missing  = [s for s in SOURCES if not s.exists()]

    if missing:
        for m in missing:
            print(f"  ⚠  nicht gefunden, wird übersprungen: {m.name}")

    if not existing:
        print("✗ Keine Quellen vorhanden. Abbruch.")
        return

    print("  Lade Wortlisten …")
    words = WordLoader.load_multiple(existing)
    print(f"  Eindeutige Wörter gesamt: {len(words)}")

    OUTPUT.write_text("\n".join(sorted(words)) + "\n", encoding="utf-8")
    print(f"✓ Zusammengeführt → {OUTPUT}  ({len(words)} Wörter)")


if __name__ == "__main__":
    main()
