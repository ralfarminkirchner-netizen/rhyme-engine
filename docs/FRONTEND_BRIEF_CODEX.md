# Frontend-Brief für Codex — Reim-Trainer (2 Achsen: Reime + Bedeutung)

> Handoff vom Backend. **Backend ist fertig & eingefroren** — bitte nur `frontend/`
> bauen, keine `app/`-Dateien ändern. Der API-Vertrag unten ist verbindlich und
> bereits live unter `http://localhost:8003` (FastAPI, CORS offen).

## Ziel

Eine persönliche deutsche Rap-Reim-Bibliothek mit **zwei strikt getrennten Achsen**:

1. **🎤 Reime** — klangliche Reimsuche im eigenen Korpus, mit **0–10-Bewertung**,
   die das Ranking langfristig lernt (Feedback-Loop).
2. **💡 Bedeutung** — thematisch verwandte Zeilen (lokal, TF-IDF). **Getrennt**
   vom Reim-Ranking, kein Vermischen ("kein semantic drift"). Nur Browsen.

Es existiert bereits ein funktionierendes Vanilla-HTML-Tool unter
`GET http://localhost:8003/trainer` als Referenz-UX (Backend liefert es aus
`app/data/user_texts/reim_trainer.html`). Ziel: dieselbe Funktionalität als
saubere React/Vite-Komponente ins bestehende Frontend integrieren (oder die
vorhandene `RhymeSearch.tsx` erweitern).

## Hard Constraints

- Nur `frontend/` ändern. **Niemals** `app/`, Tests oder Backend-Logik anfassen.
- Den API-Vertrag unten **nicht** umbenennen/umbauen — er ist fix.
- Kommentar-/Feedback-Texte sind privat: **nie** an externe APIs senden (das
  Backend tut das auch nicht).
- Alles läuft lokal gegen `http://localhost:8003`.

---

## API-Vertrag (verbindlich)

Base URL: `http://localhost:8003`  ·  Prefix: `/api/rhymes`  ·  alle POST = JSON.

### 1) Reim-Suche
`POST /api/rhymes/user-texts/search`

Request:
```json
{ "query": "einfach machen", "limit": 25, "min_score": 0.4, "rerank": false }
```
(`limit` 1–100 default 30 · `min_score` 0–1 default 0 · `rerank` optional bool)

Response:
```json
{
  "query": "einfach machen",
  "total_candidates": 5775,
  "retrieved_candidates": 120,
  "rerank": { "enabled": false, "provider": "none" },
  "results": [
    {
      "phrase": "kein kopf machen",
      "score": 0.978,            // Engine-Reimscore 0..1
      "raw_score": 0.995,
      "anchor": 1.0,             // End-/Stress-Anker-Match
      "tail": 1.0,
      "vowel": 1.0,
      "cadence": 1.0,
      "syllable_count": 4,
      "source_title": "3? einfach machen",
      "line_no": 91,
      "line_text": "kein kopf machen",
      "reason": "Starker Anker-Match",
      "occurrence_count": 1,     // wie oft die Phrase im Korpus vorkam
      "feedback_rating": null,   // deine letzte Note 0..10 für diese (Query,Treffer) oder null
      "feedback_comment": "",
      "feedback_score": 0.978,   // SORTIERFELD: Score nach Feedback-Einfluss
      "feedback_count": 0,
      "feedback_average": null,
      "feedback_pattern": "ə|ə|short",     // Muster-Schlüssel (Query-Endfamilie|Treffer-Endfamilie|Silbenband)
      "feedback_pattern_count": 0,         // wie viele Bewertungen dieses Muster stützen
      "feedback_pattern_average": null     // Ø-Note des Musters
    }
  ]
}
```
Sortierung: das Backend liefert bereits nach `feedback_score` (bzw. `score`)
absteigend. Frontend zeigt in dieser Reihenfolge.

### 2) Feedback speichern (Lern-Loop)
`POST /api/rhymes/user-texts/feedback`

Request (alle vier Identifikator-Felder exakt aus dem Result-Row durchreichen):
```json
{ "query": "einfach machen", "source_title": "3? einfach machen",
  "line_no": 91, "phrase": "kein kopf machen", "rating": 2, "comment": "" }
```
(`rating` 0–10 · `line_no` >= 1 · `comment` optional, <= 2000 Zeichen)

Response: `{ "status": "ok", "warning": "", "feedback": { ... } }`

Lern-Wirkung (Backend, nur zur Info fürs UI-Wording):
- Exakte Bewertung zieht genau diesen Treffer hoch/runter.
- **Muster-Prior**: ab 2 Bewertungen desselben Musters werden auch ähnliche,
  *nicht* bewertete Treffer mitgezogen. Darum: nach dem Bewerten erneut suchen
  → Bewegung wird sichtbar.

### 3) Bedeutungs-Suche (getrennte Achse)
`POST /api/rhymes/user-texts/search-meaning`

Request: `{ "query": "schmerz", "limit": 25, "min_score": 0.0 }`

Response:
```json
{
  "query": "schmerz", "axis": "meaning", "total_candidates": 5876,
  "results": [
    { "text": "...gibt es kein Schmerz", "score": 0.517,
      "source_title": "...", "line_no": 42, "matched_terms": ["schmerz"] }
  ]
}
```
Kein Reim, keine Bewertung — reine Themen-Relevanz. (Aktuell lexikalisch/TF-IDF;
Synonyme/Metaphern folgen evtl. später per Embedding — UI muss dafür nichts ändern.)

### 4) Status / Hilfsendpunkte (optional fürs UI)
- `GET  /api/rhymes/user-texts/summary` → Korpus-Status (Quellen, Zeilen, Units).
- `POST /api/rhymes/user-texts/search-lines` `{query,limit,min_score}` → Textzeilen-Suche.
- `POST /api/rhymes/user-texts/search-quotes` `{query,limit,min_score}` → zitierbare Zeilen.
- `POST /api/rhymes/user-texts/library` `{limit}` → komplette Listen.

---

## UX-Spezifikation

**Kopf:** Achsen-Umschalter (🎤 Reime / 💡 Bedeutung) + Sucheingabe (Enter sucht)
+ Optionen (min_score, Anzahl).

**Reime-Modus — Treffer-Karte:**
- Groß: `phrase`.
- Badges: `Engine score` · `nach Feedback feedback_score` · `Anker/Tail/Vokal/Kadenz`
  · `syllable_count Silben` · `source_title` (+ `occurrence_count×` wenn >1)
  · falls `feedback_pattern_count>0`: „Muster N× (Ø …)" · falls `feedback_rating!=null`: „deine Note N".
- **0–10-Buttons** (0–3 rot, 4–7 gelb, 8–10 grün) → bei Klick `feedback` POSTen,
  Karte als „bewertet" markieren, kleine Bestätigung („gelernt ✓").
- Optionales Kommentarfeld pro Karte.
- Button **„Erneut ranken ↻"**: gleiche Query nochmal suchen, damit der Lerneffekt
  sichtbar wird.

**Bedeutung-Modus — Treffer-Karte (read-only):**
- Groß: `text` (ganze Zeile).
- Badges: `Relevanz score` · `source_title` · `matched_terms`.
- **Keine** Bewertung, keine Reim-Sub-Scores (bewusst getrennte Achse).

**Wording/Erklärung im UI:**
- 0–3 = schlecht/kein Reim · 4–7 = ok · 8–10 = stark.
- Hinweis, dass Bewerten ähnliche Muster mitlernt.
- Kommentare bleiben lokal.

**Robustheit:** Backend kann offline sein → klare Fehlermeldung statt Crash
(„Backend nicht erreichbar auf <url> — läuft uvicorn auf 8003?").

## Akzeptanzkriterien
- [ ] Beide Achsen umschaltbar, je eigener Endpunkt & Kartendarstellung.
- [ ] Reim-Bewertung 0–10 wird gespeichert; „Erneut ranken" zeigt veränderte Reihenfolge.
- [ ] Unbekannte/zusätzliche JSON-Felder brechen das UI nicht (defensiv lesen).
- [ ] Keine Backend-Dateien geändert; build läuft (`npm run build`, `tsc --noEmit`).
- [ ] Funktioniert gegen das laufende Backend auf `http://localhost:8003`.

## Referenz
Live-Vorbild (gleiche Funktionalität, Vanilla): `http://localhost:8003/trainer`.
