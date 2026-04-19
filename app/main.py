from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.services.rhyme_engine import RhymeEngine
from app.services.word_loader import WordLoader, WordCache
from app.api.routes import rhymes as rhymes_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Eingebaute Minimal-Wortliste (Fallback wenn keine externe Datei vorhanden) ─

BUILTIN_WORDS = """
sein schein allein bewusstsein erschein gemeinschein widerschein
lieb tief Brief grief rief Chief Riff Stift Gift
lieb blieb trieb rieb schrieb hieb nieb
Licht dicht richt Gesicht Gericht Gewicht Pflicht Bericht sicht
Bach Fach Dach Mach nach wach
Buch Tuch Fluch Brauch Schlauch Rauch Bauch Hauch Strauch
ich mich dich sich wich brich stich sprich
Tag Weg leg Steg
Haus aus Maus Laus Klaus graus Schmaus Straus
gut Hut Mut Blut Flut Wut Glut
Zeit weit breit Leid Heid Scheid Neid Meid Eid
sein mein kein dein rein Lein Wein Schein nein fein Zein pein Hein Bein Stein Rein
Geist Geist Greis Reis Eis Kreis Preis Beweis
Kraft Shaft haft saft taft raft
gut blut hut Mut Flut Glut Wut
Tag sag Mag frag Lag wag Klag
Herz Schmerz Kerz Merz
warm arm Farm Harm Lärm Karm
wohl voll toll Soll Roll Kohl
hell Fell Fell Bell Well Quell sell
klar bar war Tar Spar Jahr
neu treu freu blau grau rau
Traum Raum Schaum Saum Baum Gaum
stark dark park Mark Quark Lark hark
lang sang rang Drang Klang Bang Gang
groß bloß los stoß Floß toß
alt kalt wald bald Halt Salt
Zeit Leid Streit Neid weit breit
Welt Feld Geld Held
Hand Sand Band Land Wand Rand
Berg Werk Stärk Merk
Licht dicht richt nicht Pflicht
Herz Schmerz Scherz
Mut gut Blut Flut Hut
Brot rot tot Not
Ruh Kuh Schuh Kuh
Frost Rost Kost Most Bost
"""

def _builtin_wordlist():
    return [w.strip().lower() for w in BUILTIN_WORDS.split() if w.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starte Engine …")

    # Externe Wortliste laden falls vorhanden, sonst Fallback
    # Priorität: Merged > Leipzig 100k > OpenSubtitles 50k > generische Fallbacks
    sources = [
        Path("app/data/de_merged.txt"),
        Path("app/data/deu_news_2021_100K.txt"),
        Path("app/data/de_50k.txt"),
        Path("app/data/german.txt"),
        Path("app/data/wordlist.txt"),
    ]
    raw_words = WordLoader.load_multiple(sources)

    if not raw_words:
        logger.warning("Keine externe Wortliste gefunden – nutze eingebaute Liste")
        raw_words = _builtin_wordlist()
    else:
        logger.info(f"{len(raw_words)} Wörter aus Dateien geladen")

    parsed = WordCache.load_or_process(raw_words)
    engine = RhymeEngine(parsed)
    rhymes_router.set_engine(engine)
    logger.info(f"Engine bereit: {len(parsed)} Wörter")

    yield

    logger.info("Engine gestoppt")


app = FastAPI(
    title="Deutsche Reim-Engine",
    description="Phonetische Reimsuche für die deutsche Sprache",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rhymes_router.router)


@app.get("/")
async def root():
    return {"message": "Deutsche Reim-Engine", "docs": "/docs"}
