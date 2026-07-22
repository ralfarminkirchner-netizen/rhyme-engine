#!/usr/bin/env python3
"""
fetch_dictionaries.py — Echte Fach-Wörterbücher aus der deutschen Wikipedia ziehen.

Durchläuft pro Fachgebiet Kategorie-Bäume (inkl. Unterkategorien, tiefenbegrenzt),
sammelt Artikeltitel = Fachbegriffe, bereinigt sie und schreibt eine Wortliste
pro Domäne nach app/data/user_texts/dictionaries/<domain>.txt.

Rein lesend, öffentliche Wikipedia-API, keine Keys. Danach:
    python3 -c "from app.services.dictionary_loader import import_dictionaries as i; print(i())"

Aufruf:
    python3 scripts/fetch_dictionaries.py [domain ...]
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://de.wikipedia.org/w/api.php"
OUT_DIR = Path("app/data/user_texts/dictionaries")

# Domäne -> Wurzel-Kategorien (werden inkl. Unterkategorien traversiert)
DOMAINS = {
    "philosophie": [
        "Philosophie", "Erkenntnistheorie", "Metaphysik", "Ethik", "Logik",
        "Ästhetik", "Sprachphilosophie", "Philosophie des Geistes",
        "Naturphilosophie", "Philosophische Anthropologie", "Philosophischer Begriff",
        "Wissenschaftstheorie", "Politische Philosophie", "Rechtsphilosophie",
        "Geschichtsphilosophie", "Bewusstsein", "Willensfreiheit",
    ],
    "ontologie": [
        "Ontologie", "Metaphysik", "Modallogik", "Seinsphilosophie",
        "Naturphilosophie", "Universalienproblem", "Kausalität",
    ],
    "spiritualitaet": [
        "Spiritualität", "Mystik", "Esoterik", "Meditation",
        "Religiöse Praxis", "Religionsphilosophie", "Kontemplation",
        "Religiöse Erfahrung", "Yoga", "Gebet",
    ],
    "psychologie": [
        "Psychologie", "Emotion", "Wahrnehmung", "Kognition",
        "Persönlichkeitspsychologie", "Tiefenpsychologie", "Psychoanalyse",
        "Psychologisches Konzept", "Motivation",
    ],
    "mythologie": [
        "Mythologie", "Griechische Mythologie", "Germanische Mythologie",
        "Römische Mythologie", "Mythologisches Konzept", "Schöpfungsmythos",
    ],
    "naturwissenschaft": [
        "Naturwissenschaft", "Physik", "Kosmologie", "Astronomie",
        "Chemie", "Biologie", "Physikalische Größe", "Naturphänomen",
    ],
    "gesellschaft": [
        "Soziologie", "Gesellschaft", "Politik", "Soziologischer Begriff",
        "Sozialphilosophie", "Macht", "Kultur",
    ],
    "kunst": [
        "Kunst", "Literatur", "Musik", "Poetik", "Kunsttheorie",
        "Literarischer Begriff", "Rhetorik",
    ],
}

GENERAL_URL = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/de/de_50k.txt"

MAX_DEPTH = 2
MAX_PER_DOMAIN = 8000
_BAD_PREFIX = ("liste ", "kategorie", "portal", "wikipedia", "datei", "vorlage")


def _get(params: dict) -> dict:
    params = {**params, "format": "json", "formatversion": "2", "maxlag": "5"}
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "RheinwerkerRhyme/1.0 (local; rhyme dictionary)"})
    delay = 1.0
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 5:
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            raise
    return {}


def _members(cat: str, cmtype: str):
    cont = None
    while True:
        params = {"action": "query", "list": "categorymembers",
                  "cmtitle": f"Kategorie:{cat}", "cmlimit": "500", "cmtype": cmtype}
        if cont:
            params["cmcontinue"] = cont
        data = _get(params)
        for m in data.get("query", {}).get("categorymembers", []):
            yield m["title"]
        cont = data.get("continue", {}).get("cmcontinue")
        if not cont:
            break
        time.sleep(0.6)


def _clean(title: str) -> str | None:
    t = re.sub(r"\s*\(.*?\)\s*$", "", title).strip()      # "(Philosophie)" weg
    if not t or ":" in t:
        return None
    low = t.lower()
    if low.startswith(_BAD_PREFIX):
        return None
    if re.search(r"\d", t):
        return None
    if not re.fullmatch(r"[A-Za-zÄÖÜäöüßéèêàç\- ]+", t):
        return None
    if len(t) < 3 or len(t.split()) > 4:
        return None
    return t


def fetch_domain(domain: str, roots: list[str]) -> list[str]:
    seen_cats: set[str] = set()
    terms: set[str] = set()
    frontier = [(c, 0) for c in roots]
    while frontier and len(terms) < MAX_PER_DOMAIN:
        cat, depth = frontier.pop(0)
        if cat in seen_cats:
            continue
        seen_cats.add(cat)
        try:
            for title in _members(cat, "page"):
                c = _clean(title)
                if c:
                    terms.add(c)
                    if len(terms) >= MAX_PER_DOMAIN:
                        break
            if depth < MAX_DEPTH:
                for sub in _members(cat, "subcat"):
                    name = sub.split(":", 1)[-1]
                    if name not in seen_cats:
                        frontier.append((name, depth + 1))
        except Exception as exc:
            print(f"   ! {cat}: {exc}")
        print(f"   {domain}: {len(terms)} Begriffe (cat '{cat}', tiefe {depth})", flush=True)
        time.sleep(0.6)
    return sorted(terms)


def fetch_general() -> int:
    """Lädt eine allgemeine deutsche Frequenz-Wortliste (~50k) als 'allgemein.txt'."""
    req = urllib.request.Request(GENERAL_URL, headers={"User-Agent": "RheinwerkerRhyme/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8", "ignore")
    terms = []
    seen = set()
    for line in raw.splitlines():
        w = line.split()[0] if line.split() else ""
        if len(w) < 3 or not re.fullmatch(r"[A-Za-zÄÖÜäöüß\-]+", w):
            continue
        k = w.lower()
        if k in seen:
            continue
        seen.add(k)
        terms.append(w)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "allgemein.txt"
    out.write_text(f"# allgemein — de Frequenzliste 50k ({len(terms)} Wörter)\n" + "\n".join(terms) + "\n", "utf-8")
    print(f"-> {out}: {len(terms)} Wörter")
    return 0


def main(argv: list[str]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    args = argv[1:]
    if "general" in args:
        fetch_general()
        args = [a for a in args if a != "general"]
        if not args:
            return 0
    wanted = args or list(DOMAINS)
    for domain in wanted:
        roots = DOMAINS.get(domain)
        if not roots:
            print(f"unbekannte Domäne: {domain}")
            continue
        print(f"== {domain} ==")
        terms = fetch_domain(domain, roots)
        out = OUT_DIR / f"{domain}.txt"
        header = f"# {domain} — aus de.wikipedia Kategorie-Baum ({len(terms)} Begriffe)\n"
        out.write_text(header + "\n".join(terms) + "\n", "utf-8")
        print(f"-> {out}: {len(terms)} Begriffe\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
