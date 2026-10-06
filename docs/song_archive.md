# Versioniertes Songgedächtnis

Der private Textbestand liegt in `ralfarminkirchner-netizen/mindlaxy-vault`,
`songtexte/manifest.json`. ChatGPT hält die Arbeitskopien in
`/REiMWERK/Songtexte` und sichert gespeicherte neue Fassungen nach GitHub.
Ungespeicherte andere Chats sind kein verfügbarer Ereignisauslöser.

## Direkter Zugriff im REiMWERKER

`SONG_ARCHIVE_GITHUB_TOKEN` serverseitig setzen: ein Fine-grained GitHub Token
mit Contents: Read für das private `mindlaxy-vault`. Keine Tokens im Frontend.
Die GitHub-Verbindung von ChatGPT gibt der separat laufenden Anwendung keine
Zugangsdaten. Ohne diese Konfiguration bleibt der lokale Import unverändert.

```bash
python3 scripts/song_archive.py sync
python3 scripts/run_personal_rhyme_pipeline.py "schattenkabinett"
```

Jeder reguläre Import und Pipeline-Lauf synchronisiert vor dem Import, wenn der
Token gesetzt ist. Der Import liest einen festen Commit, prüft private Sichtbarkeit,
Dateipfade und SHA-256-Prüfsummen. Originale, Leerzeilen und Wiederholungen bleiben
in der Inbox erhalten; der bestehende Suchindex bleibt ein abgeleitetes Format.
Alle Fassungen bleiben zugänglich, auch wenn eine neuere Fassung existiert.
Bei Zugriffsproblemen arbeitet der Import mit vorhandenen lokalen Quellen weiter
und meldet eine Warnung. Es gibt keine automatische Veröffentlichung von Texten.

## Aussagen unabhängig von Reimen nutzen

Die vorhandene Bedeutungssuche sucht sämtliche importierte Textzeilen unabhängig
vom Reimwert. Für bewusst ausgewählte Passagen und konkrete Nutzerbewertungen:

```bash
python3 scripts/song_archive.py feedback <document-id> <sha256> 4 6 meaning 9 --comment "Aussage behalten"
python3 scripts/song_archive.py feedback <document-id> <sha256> 4 6 rhyme 2 --comment "Reim überarbeiten"
python3 scripts/song_archive.py search "zugehörig Welt"
python3 scripts/song_archive.py export-training
```

Bewertungen gelten für einen unveränderlichen Zeilenbereich in einer bestimmten
Version. `meaning`, `rhyme` und `rhythm` sind unabhängig; unbewertet bleibt unbewertet.
Die Suchausgabe enthält Originalpassage, Herkunft, Zeilenbereich und Bewertungen.
Die Feedbackhistorie bleibt erhalten; neue Bewertungen ersetzen nur die aktuelle
Bewertung derselben Achse. Aufgezeichnet werden ausdrücklich eingegebene Bewertungen,
keine automatisch erfundenen Nutzerurteile.

`archive/reviewed_training.jsonl` exportiert diese Bewertungen als private Lernbeispiele.
Dies ist ein Datenexport, kein zusätzlicher Trainer. Der bestehende lokale
Reimtrainer bleibt getrennt und nutzt weiterhin seine eigene Pipeline. Die
Gewichte von ChatGPT werden durch das Archiv nicht verändert.

Das CLI enthält keinen automatischen GitHub-Rückschreibzugriff auf private
Bewertungen. Diese bleiben lokal; die ChatGPT-Nachsicherung betrifft Songdokumente.
Private Dateien, Datenbanken und Exporte sind im öffentlichen App-Repository
git-ignoriert. Vor neuen Texten die Archiv-Regeln lesen und passende Originalpassagen
abrufen; Aussagen nur mit passendem Zusammenhang übernehmen.
