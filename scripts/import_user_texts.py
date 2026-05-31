#!/usr/bin/env python3
"""Importiert app/data/user_texts/inbox in die lokale Reimdatenbank."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.user_text_importer import refresh_user_text_database


def main() -> None:
    summary = refresh_user_text_database()
    print(f"Quellen:      {summary.source_count}")
    print(f"Importiert:   {summary.imported_count}")
    print(f"Übersprungen: {summary.skipped_count}")
    print(f"Textzeilen:   {summary.line_count}")
    print(f"Reim-Units:   {summary.rhyme_unit_count}")
    print(f"Reim-Paare:   {summary.rhyme_pair_count}")
    print(f"Datenbank:    {summary.database_path}")
    print(f"Extrakte:     {summary.extracted_dir}")
    if summary.warnings:
        print("Warnungen:")
        for warning in summary.warnings[:8]:
            print(f"  - {warning}")


if __name__ == "__main__":
    main()
