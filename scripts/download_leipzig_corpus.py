#!/usr/bin/env python3
"""Lädt das Leipzig Wortschatz Corpus (deu_news_2021_100K) nach app/data/."""
from __future__ import annotations
import shutil
import tarfile
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "app" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

URL      = "https://downloads.wortschatz-leipzig.de/corpora/deu_news_2021_100K.tar.gz"
TGZ_PATH = DATA_DIR / "deu_news_2021_100K.tar.gz"
TARGET   = DATA_DIR / "deu_news_2021_100K.txt"
TMP_DIR  = DATA_DIR / "_leipzig_tmp"


def _safe_extract(tf: tarfile.TarFile, dest: Path) -> None:
    """Entpackt nur reguläre Dateien – verhindert Path-Traversal."""
    for member in tf.getmembers():
        if not member.isfile():
            continue
        # Keine absoluten Pfade, keine ".." in Namen
        member_path = Path(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            print(f"  ⚠  übersprungen (unsicher): {member.name}")
            continue
        tf.extract(member, dest)


def main() -> None:
    print(f"↓ {URL}")
    try:
        urllib.request.urlretrieve(URL, TGZ_PATH)
        print(f"  Archiv: {TGZ_PATH.stat().st_size // 1024 // 1024} MB")
    except Exception as e:
        print(f"✗ Download fehlgeschlagen: {e}")
        TGZ_PATH.unlink(missing_ok=True)
        return

    print("  Entpacke …")
    TMP_DIR.mkdir(exist_ok=True)
    try:
        with tarfile.open(TGZ_PATH, "r:gz") as tf:
            _safe_extract(tf, TMP_DIR)
    except Exception as e:
        print(f"✗ Entpacken fehlgeschlagen: {e}")
        shutil.rmtree(TMP_DIR, ignore_errors=True)
        TGZ_PATH.unlink(missing_ok=True)
        return

    # Leipzig-Format: deu_news_2021_100K-words.txt oder deu_news_2021_100K-1.txt etc.
    # Suche nach dem Korpus-Namensmuster statt hartem Dateinamen.
    word_files = sorted(TMP_DIR.rglob("deu_news_2021_100K-*.txt"))
    if not word_files:
        word_files = sorted(TMP_DIR.rglob("*words*.txt"))
    if not word_files:
        word_files = sorted(TMP_DIR.rglob("*.txt"))

    if not word_files:
        print("✗ Keine Wortliste im Archiv gefunden.")
        shutil.rmtree(TMP_DIR, ignore_errors=True)
        TGZ_PATH.unlink(missing_ok=True)
        return

    words: set[str] = set()
    for txt in word_files:
        for line in txt.read_text("utf-8", errors="ignore").splitlines():
            parts = line.strip().split("\t")
            # Typisch: parts[0]=Index, parts[1]=Wort, parts[2]=Frequenz
            word = (parts[1] if len(parts) >= 2 else parts[0]).strip().lower()
            if word and word.isalpha():
                words.add(word)
        print(f"  {txt.name}: {len(words)} Wörter kumuliert")

    sorted_words = sorted(words)
    TARGET.write_text("\n".join(sorted_words) + "\n", encoding="utf-8")
    print(f"✓ {TARGET}  ({len(sorted_words)} Wörter)")

    shutil.rmtree(TMP_DIR, ignore_errors=True)
    TGZ_PATH.unlink(missing_ok=True)
    print("  Temporäre Dateien gelöscht.")


if __name__ == "__main__":
    main()
