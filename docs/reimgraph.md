# REiMWERK: lokaler Reimgraph

Stand: 27. Oktober 2026. Additive Weiterentwicklung von `rhyme-engine`,
Ausgangsstand `41d4307`, Arbeitsbranch `codex/reimgraph`.
`Rhyme-Engine-Anti-Gravity` wurde als zweite vorhandene Variante gesichtet und
nicht verändert. Es wurden keine Änderungen gepusht.

## Korrektur der Rap-Erkennung: reimgraph/2

Ein echter Nutzerfall mit sechs viersilbigen Phrasen ergab in Version 1 trotz
`dirty`, 4–5 Silben und ±1 Flex keine Beziehung. Die bestehenden technischen
Tests hatten diesen Qualitätsfehler nicht erfasst. Die Abdeckung verlangte
an jeder Silbe zusätzlich ähnliche Konsonanten, einschließlich wechselnder
Silbenanfänge. Dadurch konnten selbst stark zusammenpassende Kerne mit
identischem Endanker vollständig herausfallen.

Version 2 ergänzt einen eigenen Vergleich für verteilte Rap-Reimkerne:
getrennte starke Anfangs-/Endkerne, geordnete Stützung über die gesamte
Silbenstrecke und tatsächlich vorhandener Konsonantgriff. Die Einzelprofile
bleiben sichtbar; die Erklärung benennt tragende Positionen. Ein gemeinsamer
Schluss allein oder ähnliche Vokale ohne weitere Lautstützung genügen nicht.
`strict` prüft weiterhin die exakte reimtragende Lautfolge.

Ein graphlokaler Ausspracheadapter verbessert außerdem C-Kontexte, bestimmte
Lehnwortfolgen mit unsilbischem i, Konsonantverdopplung, Flexions-Schwa und
offene betonte Silben. Die angewandten Regeln stehen an den Wortanalysen;
die Legacy-Wortsuche wird dadurch nicht verändert. Es bleibt eine
korrigierbare Aussprachehypothese, kein Aufnahmeabgleich.

Der private Nutzerfall ist außerhalb des getrackten Implementierungsrepos
aufbewahrt. Er wird mit den ursprünglichen Einstellungen und ohne manuelle
Aussprachekorrekturen geprüft: sechs Vier-Silben-Segmente, zehn direkte
Beziehungen, keine isolierte Zeile. Beide Satzzeichenvarianten wurden auch
über die laufende API geprüft; die geöffnete Browseransicht wurde mit der
erhaltenen Nutzereingabe neu berechnet. Das ist ein Nachweis für diesen Fall,
keine allgemeine künstlerische Abnahme.

Für lokale private Korpora steht ein inhaltsneutraler Prüfläufer bereit:

```sh
.venv/bin/python scripts/check_graph_cases.py /pfad/zum/privaten-korpus.json
```

Er prüft Silbenzahl, direkte Beteiligung jeder Zeile, zusammenhängendes Netz
und unbekannte Laute, ohne den Text auszugeben. Neue synthetische Tests
prüfen unabhängig davon wechselnde Onsets, Auslautvarianten und Gegenfälle.

## Benutzung

Im Projektordner:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8003
```

`http://127.0.0.1:8003` öffnet den neuen Arbeitsbereich. Die bestehende
Bibliothek ist über den Schalter daneben erreichbar. Beim Wechsel bleiben
die Eingaben beider Arbeitsbereiche erhalten.

1. Mehrere eigene Zeilen einfügen oder ausdrücklich **Beispiel laden** wählen.
2. Silbenlänge, Reimspielraum und Binnenreime wählen, Graph berechnen.
3. Beziehung im Graphen oder in der vollständigen Beziehungsliste auswählen.
4. Lautsilben, Ausrichtung, Lücken und getrennte Vergleichswerte prüfen.
5. Bei Bedarf ein Wort samt Aussprache und Betonung korrigieren, neu berechnen.
6. Die Analyse als lokale Session speichern. Ein neuer Stand erzeugt eine
   eigene Session; er überschreibt keine frühere Analyse.
7. Persönliche Entscheidung, Hörstatus, Kommentar, Vortragsidee und
   Bedeutungsbrücke separat speichern. Frühere Entscheidungen bleiben erhalten.
8. Nach Neuladen dieselbe Session öffnen und die Entscheidung zurücklesen.

Die Werte von 0 bis 1 sind technische Vergleichswerte. Ein angenommener Reim
ist nur durch eine ausdrückliche Nutzerentscheidung angenommen. Der Hörstatus
ist eine Selbstauskunft; die Software hat dadurch keine Aufnahme analysiert.

## Was der Graph verbindet

- **Quellvorkommen:** unveränderter Text und konkrete Wort-/Zeilenposition.
- **Aussprache:** regelbasierter Vorschlag oder manuell eingegebene Lautsilben
  und Betonung, jeweils an dieser Wortstelle.
- **Segmente:** zusammenhängende Klangabschnitte, auch über Wortgrenzen und
  innerhalb von Wörtern. Standardmäßig 3–8 Silben, einstellbar bis 12.
- **Beziehungen:** tatsächlich paarweise berechnete Ausrichtungen mit Anker,
  Schluss, Vokal-/Konsonantenentsprechung, Betonung und Abdeckung. Keine
  transitive Reimbehauptung aus benachbarten Knoten.
- **Entscheidungen:** eigene Annahme, Versuch oder Ablehnung dieser Beziehung
  in genau diesem gespeicherten Zusammenhang.

Nur der erste Silbenanlaut eines Vergleichssegments wird aus dem
reimtragenden Lautbereich ausgenommen. Spätere Silbenanfänge werden
mitverglichen. So wird reine Vokalähnlichkeit nicht als lautidentischer
mehrsilbiger Reim etikettiert. Endanker und Schluss tragen im Ranking mehr
Gewicht als die globale Vokalfolge.

Zeichenbereiche sind 0-basierte Python-Codepoints, Ende exklusiv. JavaScript
stellt sie mit `Array.from(text)` dar. Bei einem Teilwortsegment umschließt der
Schriftbereich das gesamte betroffene Wort; die Silbenindizes zeigen den
genauen verglichenen Klangabschnitt. Das ist keine behauptete exakte
Graphem-Phonem-Ausrichtung innerhalb des Wortes.

Silbenflex verwendet eine begrenzte Sequenzausrichtung. Lücken bleiben
sichtbar. Eine Pause füllt musikalische Zeit, kein fehlendes Phonem. Dehnung
und kürzere Artikulation werden als zu erprobende Vortragsideen behandelt.

## Persönliches Archiv und Provenienz

**Persönliche Bibliothek einbeziehen** liest die bereits importierte lokale
`rhyme_database.sqlite`. Die erste Eingabezeile dient als Suchphrase, wenn
keine eigene angegeben wird. Ein Pool von höchstens 240 Archivstellen wird
mit dem bestehenden Phrasen-Scorer vorgeprüft; Endankerfamilien haben Vorrang.
Die Beschränkung wird bei größerem Archiv angezeigt. Dies ist keine
vollständige Vollarchivsuche nach allen denkbaren unreinen Reimen.

Ausgewählte Originalzeilen werden als zusätzliche Quellen in den Graphen
aufgenommen. Knoten behalten `source_id`, Quelltitel, Originalzeilennummer,
Originalzeile, Unit-ID und Zeilenhash. Der Quellenknopf liest die betreffende
Bibliothekszeile samt Nachbarzeilen zurück. Ein nachträglicher Reimport kann
dieselbe Quelle verändert haben; der Hashvergleich meldet das und erhält den
alten Ausschnitt im Snapshot.
Die Quellzeilennummer bezieht sich auf die importierte beziehungsweise
extrahierte Bibliotheksfassung. Die ursprüngliche Pages-/TXT-Datei wird beim
Quellenrücksprung nicht erneut geöffnet oder geparst.

Fehlt die Bibliothek in einer neuen Arbeitskopie, zeigt die Anwendung das an.
Es werden keine Archivtexte erfunden oder aus einem anderen Projekt kopiert.
Der vorhandene Inbox-Import bleibt der Einstieg für private Texte.

## Speicherung und API

Standardpfad: `app/data/user_texts/reimgraph.sqlite`.
`REIMGRAPH_DATA_DIR` kann für Tests oder einen anderen lokalen Datenordner
gesetzt werden. Die Datenbank ist wie die persönliche Bibliothek ignoriert.
`REIMGRAPH_ARCHIVE_PATH` kann auf eine andere bereits importierte lokale
Reimbibliothek zeigen; diese wird ausschließlich lesend verwendet.

Sessions speichern Request, vollständige Analyse und Analyseversion. Ein
SHA-256-Fingerprint bindet das Speichern an die betrachtete Analyse. Hat sich
etwa die Archivgrundlage verändert, liefert die API 409 und verlangt einen
erneuten Aufbau. Feedback wird als Ereignis angehängt; jüngste Entscheidung
und vollständiger Verlauf können zurückgelesen werden.

| Route | Zweck |
|---|---|
| `POST /api/rhymes/graph/build` | Graph berechnen, ohne Session zu schreiben |
| `POST /api/rhymes/graph/sessions` | Unveränderlichen Analysestand speichern |
| `GET /api/rhymes/graph/sessions` | Neueste 100 gespeicherte Sessions auflisten |
| `GET /api/rhymes/graph/sessions/{id}` | Analyse, aktuelle Entscheidungen und Verlauf lesen |
| `POST /api/rhymes/graph/sessions/{id}/feedback` | Explizite Entscheidung an vorhandene Beziehung anhängen |
| `GET /api/rhymes/graph/sources/{source_id}?line_no=N&expected_line_hash=HASH` | Originalkontext und Abgleich zum gespeicherten Ausschnitt |

Grenzen: 16000 Zeichen, 64 LF-Zeilen, 160 Zeichen je Wort, höchstens 160
Segmente, 300 ausgegebene Beziehungen und 2400 genaue Paarvergleiche. Die
Standardoberfläche verwendet 120 Segmente und 180 Beziehungen. Begrenzungen
werden sichtbar gemeldet; für weitere Beziehungen kürzere Ausschnitte prüfen.

## Alle Gedanken des Ausgangsauftrags und ihr Stand

| Gedanke | In dieser Fassung |
|---|---|
| 1. Qualitätsabstand zum gemeinsamen Schreiben | Konkrete Analysen statt behaupteter Textqualität; künstlerischer Vergleich offen. |
| 2. Modellwahl | Keine neue KI-Anbindung in diesem ausdrücklich gewählten Arbeitsschritt. |
| 3. Lokale/kleine Modelle | Deterministischer Graph; vorhandene Modellwahl unverändert. Das bestehende lokale Reimmodell ist ein kalibrierter Reranker. |
| 4. Persönliche Maßstäbe | Explizites, kontextgebundenes Feedback samt Verlauf; automatische Geschmacksübertragung offen. |
| 5. Archiv und Rhyme Engine | Echte lokale Bibliotheksstellen werden dem Graphen zugeführt und rückgelesen. |
| 6. Reimgraph | Berechnete Segmente und bedingte paarweise Beziehungen in Graph und Liste. |
| 7. SiLBENMASCHiNE | Wort-/Laut-/Silbendaten erreichbar; eine separate App oder Pad-Oberfläche wurde nicht verbunden. |
| 8. Gesprochene Silben und Laute | Regelanalyse mit korrigierbaren Lautsilben und Betonung; keine perfekte Ausspracheinstanz. |
| 9. Reimtragende Lautfolgen über Wortgrenzen | Zusammenhängende Silbensegmente und Ausrichtungen. |
| 10. Schriftlich verschiedene, klanglich passende Wörter | Lautvergleich, keine Bewertung nach Buchstabenähnlichkeit. |
| 11. Schrift, Lautschrift, tatsächliche Aussprache | Schrift-/Wortstelle und Lautanalyse verbunden; Aufnahmeabgleich offen. |
| 12. Semantisches Reaching | Bedeutungsbrücke ausdrücklich als eigene Notiz; keine automatische Semantikprüfung. |
| 13. Klanglicher/rhythmischer Spielraum | Sichtbare Lautabweichungen, Silbenlücken und unbestätigte Vortragsvorschläge. |
| 14. Dreckige Reime | Eigenständiger Spielraum und Kennzeichnung unreiner Beziehungen. |
| 15. Saubere mehrsilbige Reime | Lautbereich und Betonungsmuster auf Identität geprüft; Vokalfolge allein genügt nicht. |
| 16. Veränderte Betonung | Pro Wort/Silbe korrigierbar und vergleichbar; Natürlichkeit bleibt Hörurteil. |
| 17. Zusätzliche/fehlende Silbe | Begrenzte Ausrichtung und explizite Lücken, kein stiller Gleichlauf. |
| 18. Dehnung, Verdichtung und Pause | Vortragsnotizen und Vorschläge; keine automatische Audio-/Zeitanpassung. |
| 19. Binnenreime im größeren Muster | Zusätzliche interne Segmente und mehrere Beziehungen je Segment; kein erzwungener Einheitscluster. |
| 20. Abwechslung bei erhaltenem Flow/Melodie | Gegenüberstellung und persönliches Urteil; tatsächlicher Gesamtflow/Melodie noch nicht automatisch analysiert. |

Das nächste Qualitätsurteil braucht echte Passagen und eigenes Sprechen.
Für die Ursachenprüfung sollten Modell und Integration getrennt variiert
werden: bisheriges/stärkeres Modell × bisheriger/erweiterter Arbeitskontext.
Die neue Graphansicht allein belegt keine verbesserte Lyrikgenerierung.

## Prüfen

```sh
.venv/bin/python -m pytest -q
npm run build --prefix frontend
.venv/bin/python -m py_compile scripts/run_personal_rhyme_pipeline.py app/services/personal_rhyme_pipeline.py app/services/local_rhyme_model.py app/services/rhyme_graph.py app/services/rhyme_graph_workspace.py
```

Neue Prüfungen betreffen Lautidentität statt Vokalähnlichkeit, Mehrwort-/
Binnenreime, Silbenlücken, Quellpositionen einschließlich CRLF und Emoji,
ungültige/stale Aussprachekorrekturen, Begrenzungen, echte Archivzuführung,
Quellenänderungen, Fingerprintkonflikte und das Rücklesen von Sessions samt
Feedbackverlauf. Testtexte sind synthetisch, Datenbanken liegen in temporären
Verzeichnissen. Browserprüfungen ergänzen dies um Bedienung und Darstellung;
eine künstlerische Annahme durch den Nutzer ist davon unabhängig.

Fachliche Ausgangspunkte: [Hirjee/Brown: Automatic Detection of Internal and
Imperfect Rhymes in Rap Lyrics](https://archives.ismir.net/ismir2009/paper/000029.pdf)
und [Adams: On the Metrical Techniques of Flow in Rap
Music](https://www.mtosmt.org/issues/mto.09.15.5/mto.09.15.5.adams.html).
Die hier verwendeten deutschen Regeln und Gewichte sind eigene Heuristiken,
keine Übernahme einer validierten deutschen Rap-Norm.
