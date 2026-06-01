# Personal Rhyme Pipeline

Rheinwerker verarbeitet eigene Texte lokal. Private Importtexte, Extrakte,
SQLite-Datenbanken, JSONL-Trainingsdaten und lokale Modell-Dateien bleiben unter
`app/data/user_texts/` und sind git-ignoriert.

## Ordner

- `app/data/user_texts/inbox/`: eigene `.txt`, `.md` oder `.pages` Dateien ablegen
- `app/data/user_texts/extracted/`: bereinigte lokale Extrakte
- `app/data/user_texts/rhyme_database.sqlite`: lokale Reim-, Text- und Quote-Bibliothek
- `app/data/user_texts/training/rhyme_training.jsonl`: private Trainingsbeispiele
- `app/data/user_texts/training/local_rhyme_model.json`: lokal kalibriertes Reimmodell

## Ein-Schritt-Lauf

```bash
python3 scripts/run_personal_rhyme_pipeline.py "schattenkabinett"
```

Der Lauf importiert die Inbox, baut die Bibliotheken, exportiert Trainingsdaten,
kalibriert das lokale Modell und führt eine trainiert gerankte Suchprobe aus.
Standardmäßig druckt das Skript keine vollständigen privaten Phrasen. Wer lokal
bewusst Phrasen sehen will, kann `--show-phrases` setzen.

## UI

Im Bereich `Deine Reimdatenbank`:

- `Inbox importieren`: baut Reim-, Text- und Quote-Bibliothek
- `Training bauen`: schreibt private JSONL-Trainingsbeispiele
- `Modell trainieren`: kalibriert das lokale Modell
- `Pipeline laufen`: führt den kompletten Ablauf in einem Schritt aus
- `trainiert`: nutzt das lokale Modell beim Suchen als Reranker

## API

- `POST /api/rhymes/user-texts/import`
- `POST /api/rhymes/user-texts/build-training`
- `POST /api/rhymes/user-texts/train-local-model`
- `POST /api/rhymes/user-texts/pipeline`
- `POST /api/rhymes/user-texts/search` mit `{"rerank": true}`

## Tests

```bash
python3 -m pytest -q
npm run build --prefix frontend
```
