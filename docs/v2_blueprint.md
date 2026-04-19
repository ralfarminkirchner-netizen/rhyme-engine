# Reim-Engine 2.0 — Architekturstand und Blueprint

**Datum:** 2026-04-19
**Repo-Pfad:** `~/Downloads/rhyme-engine`
**Dokument-Zweck:** Technischer Ist-Zustand + Ziel-Architektur + Phasenplan.
Kein Marketingtext.

Konventionen in diesem Dokument:
- **Ist:** durch Dateien, Testläufe oder Kommandoausgaben belegt.
- **Vorschlag:** geplante Struktur, noch nicht umgesetzt.

---

## 1. Executive Summary

Die bestehende Reim-Engine läuft als FastAPI-Service mit sieben Legacy-Modi
(STRICT … END_RHYME). Ein Phrase-Layer (`rhyme_window_extractor.py`) und ein
isoliertes Scoring-Harness (`rhyme_window_scoring.py`) sind als Bibliothek mit
Gold-Tests vorhanden, werden jedoch im produktiven Such-Pfad (Route
`/api/rhymes/search`) **nicht aufgerufen**. Das Frontend ist sauberer Consumer
ohne Reim-Logik. Alle 92 Tests sind grün (Stand 2026-04-19). Der Ordner
`~/Downloads/rhyme-engine` ist aktuell **kein Git-Repository** — das ist für
den Workflow relevant und unten explizit dokumentiert. Reim-Engine 2.0 wird
additiv gebaut: Legacy bleibt byte-identisch unter `/api/rhymes/*`, V2
entsteht parallel unter `/api/v2/*`. Die größte reale Lücke ist, dass das
existierende Scoring-Harness bislang keinen User erreicht — die erste V2-Aufgabe
ist, diesen Kern produktiv über eine additive API sichtbar zu machen.

---

## 2. Ist-Zustand des Repos

### 2.1 Repo- und Git-Situation (**Ist**)
- Arbeitsverzeichnis: `/Users/ralfkirchner/Downloads/rhyme-engine`.
- `git status` meldet: `fatal: not a git repository (or any of the parent directories): .git`.
- Es existiert kein `.git/`-Verzeichnis im Repo-Root.
- **Relevanz:** Ohne Git gibt es keinen Diff-Verlauf, kein Branching,
  kein `git blame`, keine Rollback-Sicherheit, kein Commit-Message-Kontext.
  Jede Änderung ab jetzt ist irreversibel, solange kein Git initialisiert wird.
- **Vorschlag:** Vor Phase 0 `git init` + Initial-Commit. Das ist eine
  Entscheidung, die die Nutzerin explizit absegnen soll.

### 2.2 Was real funktioniert (**Ist**)

Belegt durch 92 grüne Tests (`pytest -q` → `92 passed in 0.32s`) und
Endpunkte im `TestClient`.

- `app/services/parser.py` — G2P, Silbentrennung, Stress-Heuristik.
  Abgedeckt durch `tests/test_parser_invariants.py` und indirekt durch alle
  downstream-Tests.
- `app/services/phonological_distance.py` — feature-basiertes Edit-Distance,
  `tail_similarity`. Live im Legacy-Validator genutzt.
- `app/services/rhyme_window_extractor.py` — `build_line_parse`,
  `extract_default_windows`, Features (anchor_nuclei, support_vowels,
  vowel_run, consonant_grip, flow_shape, parallel_shape, technique_tags).
  40 grün (`tests/test_rhyme_window_extractor.py -v`).
- `app/services/rhyme_window_scoring.py` — 4 Sub-Scores
  (anchor/vowel_run/rhythm/grip), Self-Match-Invariante `== 1.0`,
  Ordering-Tests POS > BORD > NEG. 21 grün (`tests/test_rhyme_window_scoring.py`).
- `app/services/rhyme_engine.py` (`RhymeEngine.search`) — Validate-then-Score
  über die Wortliste, 7 Presets, `FeatureTarget.RHYME/TERMINAL`.
- `app/api/routes/rhymes.py` — `/health`, `/modes`, `/analyze`, `/search`.
  Durchgetestet mit `fastapi.testclient.TestClient`.
- `app/services/word_loader.py` + `WordCache` — Wortlisten-Lader + gepickelter
  Parse-Cache. Cache materialisiert in `cache/` (4 `.pkl` Dateien).
- Frontend: `frontend/src/api/client.ts`, `components/RhymeSearch.tsx`,
  `types/index.ts` — reiner Consumer. Keine Parser-, Ranker- oder
  Preset-Logik clientseitig.

### 2.3 Was nur vorbereitet ist (**Ist**)

- **Das Scoring-Harness ist nicht im Request-Pfad.** Beleg: `rhyme_engine.py`
  importiert aus dem Phrase-Layer nur `build_line_parse` und
  `extract_default_windows`, nicht aus `rhyme_window_scoring`. Die vier
  V2-Subscores (anchor/vowel_run/rhythm/grip) sind berechnet und getestet,
  werden aber von keinem User erreicht.
- Die Tail-Window (zweites Fenster aus `extract_default_windows` für Zeilen
  ab 4 Silben) wird im produktiven Matching nicht gezielt verwendet.
- Phrase-Queries: `build_line_parse` nimmt Strings mit mehreren Worten, die
  API (`AnalyzeRequest`/`SearchRequest`) bindet jedoch auf `word: str` mit
  `min_length=1`. Kein eigener Phrase-Pfad.

### 2.4 Was experimentell oder provisorisch ist (**Ist**)

- `V_WORDS`/`V_PREFIXES` in `parser.py`: manuelle Liste zur Entscheidung
  `v → /v/` vs `/f/`.
- `EXCEPTIONS` in `parser.py`: 10 Einträge.
- `STRESS_SUFFIX_RULES` in `parser.py`: 6 Heuristik-Regeln, kein echter
  Morpho-Parser.
- `_vowel_distance` in `rhyme_engine.py`: positions-gewichtet (Position 0
  wichtigster) — klassische Tail-Denke, kein Reimfenster-Ansatz.
- Retrieval: O(N) über die gesamte Wortliste (138k Einträge in
  `app/data/de_merged.txt`). Kein Index, kein Bucket, kein Pre-Filter.
- CORS in `app/main.py`: `allow_origins=["*"]`.
- `app/services/_parked/rhyme_engine_anchor_patch.py` ist byte-identisch zur
  aktuellen `app/services/rhyme_engine.py` (geprüft via `diff -q`). Es ist
  **kein separater experimenteller Stand** mehr, sondern ein Duplikat.
- `frontend/src/{types,api,components}/` — ein Verzeichnis mit
  bash-Klammer-Literal im Namen, vermutlich versehentlich durch
  nicht-expandiertes Glob entstanden. Steht parallel zu den echten
  `types/`, `api/`, `components/`.

---

## 3. Audit-Befunde

### 3.1 Phrase-/Fenster-Layer (**Ist**)
- Datenstrukturen in `app/schemas/rhyme_window.py`: `WordInLine`, `LineParse`,
  `RhymeWindow`. Dokumentation in Docstrings.
- Tokenisierung via Regex `[A-Za-zÄÖÜäöüß]+`, Bindestriche zerlegen
  Komposita in Einzelkomponenten (`"Leib-Seele-Probleme"` → 3 Wörter).
- Fenster-Strategie: 1× Full-Line-Window immer, 1× Tail-Window ab 4 Silben,
  ausgehend von `last_main_stress - 1` bis Zeilenende, Funktionswörter
  werden bei der Suche nach Last-Stress übersprungen.
- Features deckend getestet: Gold A (Diphthong-Anchor-Chain),
  Gold B (parallel_question), Gold C (front_vowel_band), Negativfälle
  (`interaktiven/literarischen/Suffixen` triggern **keine** `aɪ`-Anker).

### 3.2 Aktueller Such-Pfad (**Ist**)
- Route `POST /api/rhymes/search` → `parse_german_word(query)` →
  `RhymeEngine.search(...)`.
- `RhymeEngine` cacht pro Wort die Anker-Vokale
  (`_anchors: dict[str, List[str]]`) über den Phrase-Layer — das ist der
  einzige Berührungspunkt zwischen Legacy-Engine und V2-Core-Bibliothek.
- Validator prüft: `syllableDelta`, `stressDistance`, `vowelDistance`,
  `tailSimilarity`. Scorer summiert gewichtet `stress`, `vowelCore`, `tail`,
  `syllableFlex`.
- Modi: `STRICT`, `BALANCED`, `DIRTY`, `MULTISYLLABIC`, `KOMPOSITA`,
  `HARDCORE`, `END_RHYME`. `END_RHYME` setzt `FeatureTarget.TERMINAL`.

### 3.3 Legacy-Core (**Ist**)
- `app/services/rhyme_engine.py` + `app/services/presets.py` +
  `FeatureTarget`/`Mode` in `app/schemas/rhyme.py` + API-Shape
  `RankedCandidate`/`RejectedCandidate` bilden zusammen den Legacy-Kern.
- Tests hängen an diesem Kern: `tests/test_all.py` nutzt die Engine direkt
  und über `TestClient`.

### 3.4 Frontend-Zustand (**Ist**)
- `frontend/package.json`: Vite 8, React 19, TypeScript 6, Port 5174.
- `frontend/src/api/client.ts`: drei Calls — `health`, `modes`, `analyze`,
  `search` — jeweils reine fetch-Wrapper.
- `frontend/src/components/RhymeSearch.tsx`: UI für Wort-Query,
  Modus-Auswahl, Gewichts-Slider, Ergebnis-Tabelle. Keine Reim-Logik.
- `frontend/src/types/index.ts`: 1:1-Spiegel von `app/schemas/rhyme.py`
  in camelCase.

### 3.5 Datenbasis (**Ist**)
- `app/data/de_50k.txt` — 50.000 Zeilen.
- `app/data/de_merged.txt` — 138.475 Zeilen.
- `app/data/deu_news_2021_100K.txt` — 120.374 Zeilen.
- Fallback: Eingebaute Minimal-Wortliste in `app/main.py`.
- Lader priorisiert `de_merged.txt` > `deu_news_2021_100K.txt` > `de_50k.txt`.

### 3.6 Teststand (**Ist, Stand 2026-04-19**)
- `pytest tests/test_rhyme_window_extractor.py -v` → **40 passed in 0.08s**.
- `pytest -q` → **92 passed in 0.32s**.
- Tests pro Datei:
  - `tests/test_all.py` (Engine, API, Modi) — 31 Tests.
  - `tests/test_parser_invariants.py` — ~10 Tests.
  - `tests/test_rhyme_window_extractor.py` — 40 Tests.
  - `tests/test_rhyme_window_scoring.py` — 21 Tests.
- Hinweis: Eine frühere Zählung `76 passed` ist überholt (Scoring-Tests
  sind seitdem hinzugekommen).

---

## 4. V2-Zielarchitektur (**Vorschlag**)

### 4.1 Layer
- **UI:** reiner Consumer. Kein Ranker, kein Parser, kein Preset-Engine.
  Zwei Ansichten: Legacy (frozen) und V2.
- **API:** zwei Routergruppen nebeneinander:
  - `/api/rhymes/*` (Legacy, byte-identisch zu heute).
  - `/api/v2/*` (neu, additiv).
- **Orchestration:** V2-Engine als dünner Orchestrator — nimmt Query,
  bestimmt Pool, läuft Retrieval + Scoring + Explain, liefert Ranking.
- **V2-Core:** existierender Phrase-Layer + Scoring-Harness, ergänzt um
  Retrieval, Pools und Explainability.
- **Legacy-Core:** heutige Engine + Presets, physisch nach
  `app/services/legacy/` verschoben, Schnittstelle unverändert.
- **Shared Primitives:** `parser.py`, `phonological_distance.py`,
  `word_loader.py`, `rhyme_window_extractor.py`. Werden von beiden Kernen
  benutzt, sind aber selbst engine-frei.
- **Daten:** WordPool heute. PhrasePool und FragmentPool später.

### 4.2 Abhängigkeitsregel (**Vorschlag**)
- V2 darf Shared-Primitives importieren.
- Legacy darf Shared-Primitives importieren.
- V2 darf **nicht** aus Legacy importieren. Legacy darf **nicht** aus V2
  importieren. Der einzige Berührungspunkt ist die gemeinsame Basis.

### 4.3 Analyzer (**Vorschlag**)
- `POST /api/v2/analyze` nimmt eine Zeile (Phrase zulässig), gibt das
  `LineParse` + alle extrahierten `RhymeWindow`s + berechnete Features
  zurück. Kein Matching.

### 4.4 Retrieval (**Vorschlag**)
- Anker-Bucket-Index: `tuple(anchor_nuclei)` → Kandidatenmenge.
- Flow-Shape-Bucket als Sekundärfilter.
- Fallback-Bucket `all`, damit ein zu enger Pre-Filter niemals ein leeres
  Ergebnis produziert.

### 4.5 V2-API (**Vorschlag**)
- `POST /api/v2/analyze`
- `POST /api/v2/search` — Eingabe: `query`, `pool`, optional `limit`,
  optional `explain`. Ausgabe: Ranked Matches mit Subscore-Breakdown +
  strukturierter Explanation.

### 4.6 V2-UI (**Vorschlag**)
- Analyzer-Panel (Zeile rein, Windows raus, Tags, Flow, Grip).
- Phrase-Search-Panel.
- Explain-Panel (welche Subscores, welche Tags, welche Überlappung).
- Engine-Switcher (Legacy / V2). Legacy bleibt erreichbar.

---

## 5. Dateistruktur-Vorschlag (**Vorschlag**)

```
app/
├── main.py
├── schemas/
│   ├── rhyme.py                        (legacy, bleibt)
│   ├── rhyme_window.py                 (shared, bleibt)
│   └── v2/
│       ├── __init__.py
│       ├── query.py                    (V2 Request-Schemas)
│       ├── result.py                   (V2 Ranked-Match-Schemas)
│       └── explain.py                  (Explanation-Schema)
│
├── services/
│   ├── parser.py                       (shared, bleibt)
│   ├── phonological_distance.py        (shared, bleibt)
│   ├── word_loader.py                  (shared, bleibt)
│   ├── presets.py                      (legacy, bleibt)
│   ├── rhyme_window_extractor.py       (shared, bleibt)
│   ├── rhyme_window_scoring.py         (shared, bleibt)
│   │
│   ├── legacy/
│   │   ├── __init__.py
│   │   └── rhyme_engine.py             (verschoben aus services/)
│   │
│   └── v2/
│       ├── __init__.py
│       ├── engine.py                   (Orchestrator)
│       ├── retrieval.py                (Pre-Filter / Buckets)
│       ├── explain.py                  (baut Explanation)
│       └── pools/
│           ├── base.py                 (CandidatePool-Protokoll)
│           ├── word_pool.py            (Phase 3)
│           ├── phrase_pool.py          (Phase 4)
│           └── fragment_pool.py        (Phase 5)
│
├── api/
│   └── routes/
│       ├── rhymes.py                   (legacy, bleibt)
│       └── v2/
│           ├── __init__.py
│           ├── analyze.py
│           └── search.py
│
├── data/        (bleibt)
└── cache/       (bleibt)

tests/
├── test_all.py                         (bleibt)
├── test_parser_invariants.py           (bleibt)
├── test_rhyme_window_extractor.py      (bleibt)
├── test_rhyme_window_scoring.py        (bleibt)
├── legacy/
│   └── test_legacy_parity.py           (Phase 0)
└── v2/
    ├── test_pools_word_pool.py         (Phase 3)
    ├── test_retrieval_prefilter.py     (Phase 3)
    ├── test_engine_ordering.py         (Phase 3)
    ├── test_explain.py                 (Phase 2)
    └── test_api_v2.py                  (Phase 6)

frontend/src/
├── api/
│   ├── client.ts                       (bleibt)
│   └── v2Client.ts                     (Phase 7)
├── types/
│   ├── index.ts                        (bleibt)
│   └── v2.ts                           (Phase 7)
└── components/
    ├── RhymeSearch.tsx                 (bleibt)
    └── v2/
        ├── EngineSwitcher.tsx
        ├── PhraseSearch.tsx
        ├── Analyzer.tsx
        └── ExplainPanel.tsx
```

---

## 6. Phasen 0 – 8 (**Vorschlag**)

### Phase 0 — Stabilisieren / Einfrieren
- **Ziel:** Baseline fixieren, Legacy-Verhalten messbar einfrieren.
- **Betroffene Dateien:**
  - `tests/legacy/test_legacy_parity.py` (neu, Snapshot von `/modes`,
    `/analyze`, `/search` gegen Mini-Wortliste).
  - Optional: `app/services/_parked/rhyme_engine_anchor_patch.py` löschen
    (Duplikat).
  - Optional: `frontend/src/{types,api,components}` Literal-Directory löschen.
  - Optional: `git init` + Initial-Commit.
- **Risiken:** Snapshot über zu große Wortliste wird brüchig.
  Fix: feste, kleine Test-Wortliste in der Fixture.
- **Exit-Kriterium:** 92 grün + Parity-Snapshot committed.

### Phase 1 — Phrase-Layer / Gold verifizieren
- **Ziel:** Phrase-Layer als "Wahrheit" formal fixieren; echte Rap-Gold-Patterns
  aus den genannten Gold A/B/C ergänzen.
- **Betroffene Dateien:**
  - `tests/test_rhyme_window_extractor.py` (ergänzen, nicht umschreiben).
- **Risiken:** Neue Gold-Tests könnten aktuelle Extraktor-Heuristiken
  sprengen. Dann erst diskutieren, nie blind tunen.
- **Exit-Kriterium:** Alle Gold- und Negativ-Tests grün.

### Phase 2 — Isoliertes Scoring-Harness
- **Ziel:** Scoring engine-frei, Explanation-Payload dokumentiert.
- **Betroffene Dateien:**
  - `app/services/v2/explain.py` (neu).
  - `app/schemas/v2/explain.py` (neu).
  - `tests/v2/test_explain.py` (neu).
- **Risiken:** Gewichte tunen ohne Ranking-Gold.
  Regel: keine Gewichts-Änderung ohne neues Ranking-Gold-Set.
- **Exit-Kriterium:** `total_score` und `build_explanation` testbar isoliert,
  Self-Match bleibt 1.0.

### Phase 3 — Word-Pool Retrieval
- **Ziel:** V2 matcht Query gegen die bestehende Wortliste.
- **Betroffene Dateien:**
  - `app/services/v2/pools/base.py`, `pools/word_pool.py`.
  - `app/services/v2/retrieval.py`.
  - `app/services/v2/engine.py`.
  - `tests/v2/test_pools_word_pool.py`, `test_retrieval_prefilter.py`,
    `test_engine_ordering.py`.
- **Risiken:** Pre-Filter filtert zu aggressiv. Fallback-Bucket `all`
  ist Pflicht. Cache: `RhymeWindow` pro Wort cachen, nicht nur `ParsedWord`.
- **Exit-Kriterium:** Ranking-Gold-Set liefert erwartete Reihenfolge,
  p95 < klar definiertes Budget (wird in Phase 3 festgelegt).

### Phase 4 — Phrase-Pool Retrieval
- **Ziel:** Pool aus echten Zeilen.
- **Betroffene Dateien:**
  - `app/services/v2/pools/phrase_pool.py`.
  - `scripts/ingest_phrases.py`.
  - `app/data/phrases/` (Seed).
  - `tests/v2/` (Phrase-Ordering-Gold).
- **Risiken:** Copyright-Material. Nur Eigen- oder Public-Domain-Zeilen
  committen.
- **Exit-Kriterium:** `pool=word|phrase` umschaltbar in V2-API.

### Phase 5 — Fragment-/Hybrid-System
- **Ziel:** K-Silben-Slices und Tail-Windows als eigener Kandidatenraum.
- **Betroffene Dateien:**
  - `app/services/v2/pools/fragment_pool.py`.
  - Tests analog.
- **Risiken:** Kombinatorische Explosion. K ≤ 4, De-Dup über
  `(stress_slots, vowel_run)`.
- **Exit-Kriterium:** Fragment-Pool lädt deterministisch < 500 ms auf Seed.

### Phase 6 — V2-API
- **Ziel:** `/api/v2/analyze` + `/api/v2/search` online.
- **Betroffene Dateien:**
  - `app/api/routes/v2/analyze.py`, `search.py`.
  - `app/schemas/v2/query.py`, `result.py`.
  - `app/main.py` (Router + Lifespan-Registry).
  - `tests/v2/test_api_v2.py`.
- **Risiken:** Lifespan-Race zwischen Legacy und V2-Engine. Sequenziell
  bauen, beide Engines vor `yield` bereit.
- **Exit-Kriterium:** Beide Routen nebeneinander, Legacy-Parity-Snapshot
  weiterhin grün.

### Phase 7 — V2-UI
- **Ziel:** Analyzer-, Phrase-Search- und Explain-UI.
- **Betroffene Dateien:**
  - `frontend/src/api/v2Client.ts`, `types/v2.ts`.
  - `frontend/src/components/v2/*.tsx`.
  - Top-Level-Shell mit `EngineSwitcher`.
- **Risiken:** Frontend-Drift. Code-Review-Regel: keine Ranking-Heuristik
  im TS.
- **Exit-Kriterium:** Beide UIs nebeneinander, Screenshot-Review durch
  Nutzerin.

### Phase 8 — Legacy/V2-Integration
- **Ziel:** V2 als Default. Legacy bleibt unter Feature-Flag erreichbar.
- **Betroffene Dateien:**
  - `frontend/src/App.tsx`.
  - Feature-Flag z. B. `VITE_DEFAULT_ENGINE`.
- **Risiken:** Nutzergewohnheit. Switcher muss sichtbar und dokumentiert
  sein.
- **Exit-Kriterium:** Beide Engines stabil, V2 Default, keine Reim-Logik
  im Frontend.

---

## 7. Kritische Risiken

1. **Kein Git:** Ohne Versionierung geht jede Änderung ohne Rollback live.
   → `git init` vor Phase 0 oder explizite Entscheidung dagegen.
2. **Scoring-Harness ohne User:** Bis V2-API steht, bleibt die gebaute
   Arbeit unsichtbar. Risiko, parallel am Legacy weiterzutunen und die
   Arbeit doppelt zu machen. → Phase 6 priorisieren, sobald Phase 2–3
   stehen.
3. **Retrieval-Kosten:** Scoring pro Kandidat setzt `RhymeWindow`-Build
   voraus. Ohne Cache und Pre-Filter wird p95 unbrauchbar.
4. **Phrase-vs-Wort Längen-Mismatch:** `rhythm_score` bestraft
   Längendifferenz. Phase 3 bleibt deshalb auf word↔word, Phrase kommt
   erst Phase 4.
5. **Stress-Heuristik:** Falsche Stress-Pattern erzeugen falsche Anker.
   Regressionsset nötig, bevor Scoring-Gewichte geändert werden.
6. **Gewichts-Drift:** Leitbild 0.60 Vokalführung vs aktuell 0.40 + 0.25
   = 0.65. Nicht ohne Ranking-Gold-Set ändern.
7. **Legacy-Parity-Bruch:** Versehentliche Shape-Änderungen in
   `/api/rhymes/*`. → Snapshot-Test aus Phase 0 als Schutz.

---

## 8. Nächster konkreter Schritt

Nach Freigabe dieses Blueprints: **Phase 0 ausführen**, in dieser Reihenfolge
und nur wenn jeder Teilschritt einzeln bestätigt wird:

1. Entscheidung zur Git-Situation.
2. `_parked/rhyme_engine_anchor_patch.py` löschen (Duplikat, bytegleich).
3. `frontend/src/{types,api,components}/` Literal-Directory löschen.
4. `tests/legacy/test_legacy_parity.py` als Snapshot-Test anlegen.
5. `pytest -q` erneut ausführen, Output zeigen.

Kein Code in `rhyme_engine.py`, keine API-Änderung, keine Frontend-Änderung
in Phase 0.

---

## 9. Offene Fragen

1. Soll `~/Downloads/rhyme-engine` zu einem Git-Repo initialisiert werden?
2. Sollen die Scoring-Gewichte in `rhyme_window_scoring.py`
   (aktuell 0.40/0.25/0.20/0.15) auf das Leitbild 0.60-Vokalführung
   (z. B. 0.35/0.25/0.25/0.15) gezogen werden, und falls ja, erst nach
   einem Ranking-Gold-Set (empfohlen) oder sofort?
3. Welche Zeilen dürfen in den Phrase-Pool (Eigenmaterial / Lizenzfrage)?
4. Soll der Legacy-Code physisch nach `app/services/legacy/rhyme_engine.py`
   wandern, oder bleibt die Datei am Ort und nur der Import-Pfad wird
   namentlich klargezogen?
5. Wird der `EXCEPTIONS`-Mechanismus in `parser.py` Teil von V2 oder
   ersetzt V2 ihn durch ein Data-File?
6. Soll die V2-API in der gleichen FastAPI-App laufen oder ist ein
   separater Service gewünscht?
