# REiMATLAS

Der Atlas erschließt einen dauerhaften Wort- und Lautbestand. Eine eingegebene
Reimfolge bildet geordnete Ausgangspunkte für die Suche nach weiteren Wörtern,
Komposita und Wortgruppen. Ein Reimsegment kann mehrere Wörter umfassen;
die Reihenfolge seiner Wörter und Silben bleibt erhalten.

## Bestand und Belege

`app/data/atlas/atlas.sqlite` und die Rohquellen unter `app/data/atlas/raw/`
bleiben lokal und sind git-ignoriert. `sources-manifest.json` dokumentiert die
heruntergeladenen Fassungen, Prüfsummen, Fundstellen und jeweiligen Lizenzen.

- IPA-Dict: deutsche Wiktionary-Aussprachen und englische CMUdict-Aussprachen.
  Aussprachealternativen bleiben getrennte Einträge. Die Lizenz der deutschen
  Daten ist von der MIT-Lizenz des Repository-Codes zu unterscheiden.
- OpenThesaurus: vorhandene Wörter und Wendungen, einschließlich Gruppen- und
  Registerangaben. Die Aussprache einer Wendung wird aus Wörterbuchteilen
  zusammengesetzt; Lücken erhalten ausdrücklich markierte Regelvorschläge.
- Tatoeba: vollständiger deutscher Satzbestand mit Satzkennung, Autor,
  Originaltext und Quellenlink. Eine daraus erschlossene Wortgruppe behält
  ihre Zeichenposition und den ursprünglichen Satzkontext.

Die Anzahl der normalisierten Begriffe unterscheidet sich von der Anzahl ihrer
Aussprachen. Die Kartenregionen zählen Ausspracheeinträge. Einträge mit
unlesbaren Lautsymbolen bleiben im Bestand und tragen entsprechende Notizen.
Die Erkennung zusammengesetzter Nomen anhand bekannter Wortteile ist eine
Hypothese; `source_ref.construction_basis` kennzeichnet sie.

## Karte und Suche

Die Silbenzahl verläuft von links oben nach rechts unten. Grobe Regionen fassen
Anfangs- und Endklangfamilien zusammen. Die Detailansicht einer Region zeigt
die vollständigen **geordneten** Klangfamilienfolgen; sie kann darauf gefiltert
werden. Genaue Laute und Aussprachevarianten stehen als IPA an den Einträgen.
Klangfamilien ersetzen diese Einzelvarianten nicht.

Gespeicherte Reimfolgen bewahren die Reihenfolge der Segmente. Ihre nummerierten
Kartenpunkte führen zur Nachbarsuche. Die Darstellung versetzt überlagerte
Markierungen und verbindet sie mit ihrer tatsächlichen Überblicksregion.

Die Suche schließt ihre eigenen Ausgangspunkte aus und vergleicht ganze
geordnete Lautfolgen. Der enge Modus verlangt die gleiche Lautfolge ab dem
ersten Silbenkern. Die weiteren Modi lassen abgestufte Abweichungen zu. Ein
einsilbiger Ausgangspunkt bleibt in der einsilbigen Suche. Filter beschränken
Silbenzahl, Aufbau, Sprache und Herkunft. Bei einem englischen Fund verwendet
„Nachbarn erkunden“ genau dessen gespeicherte Aussprache.

Satzfenster werden bei der Suche gezielt aus dem gespeicherten Korpus
erschlossen. Neue Kombinationen tragen die Herkunft `constructed` und die
Belege ihrer Teile und Übergänge; die vollständige neue Kombination wird
dadurch nicht als vorhandener Satz ausgegeben. Die Herkunftsfilter halten
belegte Einträge und neue Kombinationen auseinander. Erschlossene Pfade,
Silbenübergänge und geprüfte Reimnachbarschaften bleiben in SQLite erhalten.

Ein endlicher Wortbestand kann mögliche neue Komposita und frei kombinierbare
Äußerungen nicht vollständig vorwegnehmen. Der Atlas speichert deshalb Wörter,
belegte Folgen und ihre Bausteine und erweitert die erschlossenen Pfade bei
der Suche. Eine Nachbarsuche prüft einen begrenzten Ausschnitt, keine vollständige
Rangliste sämtlicher denkbarer deutscher Ausdrücke.

## Betrieb

```sh
.venv/bin/python scripts/build_rhyme_atlas.py
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8003
npm run build --prefix frontend
```

Der Aufbau setzt das lokale Quellenmanifest und die Rohquellen voraus, lässt
vollständige Importe bestehen und setzt unterbrochene Importe fort. Eine
Dateisperre verhindert einen zweiten gleichzeitigen Aufbau desselben Atlas.
`REIM_ATLAS_DIR` kann einen anderen lokalen Datenordner auswählen. Für eine
gezielte Reparatur bereits zusammengesetzter Aussprachen gibt es
`scripts/repair_atlas_pronunciations.py`; es erstellt zuerst ein SQLite-Backup.

API: `/api/atlas/status`, `/map`, `/neighborhood`, `/search`, `/expand`, `/chains`.
Die bisherige Bibliothek und der Textgraph bleiben als eigene Arbeitsbereiche
erhalten. Der Atlas benötigt keinen API-Schlüssel und sendet die Reimfolgen
nicht an einen Modellanbieter.

Die weitere Zielsetzung verbindet Klang, Aussageabsicht, erhaltene Schreibwege
und die spätere Songproduktion: [REiMWERK als Schreibraum und Weg zum Song](schreibraum-zielarchitektur.md).
