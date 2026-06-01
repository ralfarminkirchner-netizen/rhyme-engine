# Rheinwerker Agent Playbook

Dieses Repo ist Rheinwerker, eine persoenliche Rap-Reim-Bibliothek und
Reim-Engine. Es ist nicht Rainbow Light, nicht Godot und nicht Antigravity.

## Kanonischer Kontext

- Arbeitsordner: `/Users/ralfkirchner/Documents/Rheinwerker`
- Remote: `https://github.com/ralfarminkirchner-netizen/rhyme-engine.git`
- Kein `git push`, ausser der User fordert es ausdruecklich.
- Keine destruktiven Git-Befehle.

## Produktprinzip

Rheinwerker ist keine allgemeine Wortsuche. Jede Aenderung soll die persoenliche
Rap-Reim-Bibliothek staerker machen:

1. 3-8-silbige Phrase-Level-Endreimketten priorisieren.
2. Starke Terminal-Endreime und Anchor-Matches bevorzugen.
3. Rhythmischen Grip, Kadenz und Flow-Dichte beruecksichtigen.
4. Vokal-Spine nur sekundaer nutzen.
5. Rechtschreibung, Praefixe und optisch aehnliche Wortkoerper ignorieren.

## Private Daten

Niemals committen:

- private Pages-/Text-Inhalte
- extrahierte User-Texte
- SQLite-Datenbanken
- JSONL-Trainingsdaten
- lokale Modell-Dateien
- Bilder oder generierte Kataloge

Diese Artefakte bleiben unter `app/data/user_texts/` und sind git-ignoriert.
Vor Abschluss immer kurz pruefen:

```bash
find app/data/user_texts -maxdepth 3 -type f -print | sort
git status --short
```

Erwartet sind nur `.gitkeep` Dateien im Datenordner.

## Lokale Pipeline

Der komplette private Workflow ist:

```bash
python3 scripts/run_personal_rhyme_pipeline.py "schattenkabinett"
```

Er importiert die Inbox, baut Reim-, Text- und Quote-Bibliotheken, exportiert
private Trainingsdaten, trainiert das lokale Reimmodell und fuehrt eine
trainiert gerankte Suchprobe aus.

## Pruefkommandos

Vor Abschluss technischer Aenderungen:

```bash
python3 -m pytest -q
npm run build --prefix frontend
python3 -m py_compile scripts/run_personal_rhyme_pipeline.py app/services/personal_rhyme_pipeline.py app/services/local_rhyme_model.py
```

## Architektur-Hinweise

- Backend-API: `app/api/routes/rhymes.py`
- User-Bibliotheken: `app/services/user_text_importer.py`
- Lokales Reimmodell: `app/services/local_rhyme_model.py`
- Pipeline: `app/services/personal_rhyme_pipeline.py`
- Frontend: `frontend/src/components/RhymeSearch.tsx`
- Betriebsdoku: `docs/personal_rhyme_pipeline.md`

Additive Aenderungen bevorzugen. Bestehende Legacy-Wortsuche nicht umbauen,
wenn die Aufgabe die persoenliche Phrase-/Reimbibliothek betrifft.
