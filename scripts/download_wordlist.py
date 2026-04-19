#!/usr/bin/env python3
"""Lädt die deutsche FrequencyWords-Liste (50k) nach app/data/."""
from __future__ import annotations
import shutil, urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "app" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = [
    (
        "de_50k.txt",
        "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/de/de_50k.txt",
    ),
]

def main() -> None:
    for filename, url in SOURCES:
        target = DATA_DIR / filename
        tmp    = DATA_DIR / (filename + ".tmp")
        print(f"↓ {url}")
        try:
            urllib.request.urlretrieve(url, tmp)
            shutil.move(tmp, target)
            lines = target.read_text("utf-8", errors="ignore").count("\n")
            print(f"✓ {target} ({lines} Zeilen)")
        except Exception as e:
            print(f"✗ Fehler: {e}")
            tmp.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
