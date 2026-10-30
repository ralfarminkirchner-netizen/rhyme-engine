# REiMWERK als Schreibraum und Weg zum Song

REiMWERK soll aus einem Anliegen, einer Grundfrage oder einem Aufhänger einen
inhaltlich tragfähigen, rhythmisch sprechbaren und gut gereimten Text entwickeln
können. Menschen sollen diesen Raum erkunden und bearbeiten können; ein
Schreibagent soll dieselben Arbeitsschritte selbstständig ausführen können.
Die anschließende Songproduktion über Suno gehört zu diesem Ziel.

Diese Zielsetzung stammt aus dem Gespräch vom 27. Oktober 2026. Die folgenden
Architekturentscheidungen konkretisieren sie als Vorschlag. Der vorhandene
Reimatlas stellt bereits Lautsuche, Quellenbezüge und geordnete Reimfolgen
bereit. Der hier beschriebene Schreibraum und die automatische Songproduktion
sind die anschließenden Entwicklungsstufen.

## Gemeinsames Prinzip

Als gemeinsame Arbeitsgrundlage für KiNTEGRiTY, Mooncells, MOONFiNGERS, FASKA,
PHÄNOMENAUTiK, DAS DAZWISCHEN und REiMWERK bietet sich an: Gegenstände und ihre
Herkunft erhalten, Unterschiede bearbeitbar halten und durch begründete
Übergänge neue Möglichkeiten und Werke hervorbringen. Auch eine gelungene
Verbindungsweise kann als eigenes, später wiederverwendbares Ergebnis
erhalten werden.

Innerhalb verschiedener Ansichten desselben Bestands bleiben Identitäten und
Beziehungen wiedererkennbar. Zwischen Fachgebieten wird diese Arbeitsweise
übertragen; ein Lernweg, eine Aussage und ein Reim behalten ihre jeweiligen
Eigenschaften und Prüfweisen. Neue Fassungen erhalten eigene Identitäten und
einen Bezug zu ihren Ausgangsfassungen.

## Klang und Aussage gemeinsam entwickeln

Ein Schreibanliegen umfasst Thema, Aussageabsicht, Perspektive, Adressaten,
Ton und gewünschte Form. Daraus entstehen mögliche Aussagen, Bilder und
Formulierungen. Die Lautsuche erschließt dazu geeignete Reimkombinationen.
Umgekehrt kann ein Klangfund ein neues Bild oder eine treffendere Aussage
anregen. Änderungen an der Aussageabsicht bleiben als Änderungen erkennbar.

Eine Fortsetzung muss ihre Beziehung benennen. Relevante Arten sind etwa
`reimt_mit`, `behandelt_dasselbe_thema`, `ist_formulierungsvariante_von`,
`veranschaulicht`, `begründet`, `setzt_voraus`, `stellt_in_frage` und
`führt_den_gedanken_weiter`. Ein thematischer oder lexikalischer Zusammenhang
belegt noch keine argumentative Fortsetzung. Die Richtung einer Suche
begründet ebenfalls keine inhaltliche Richtung.

Klang, Aussageabsicht, Grammatik, Rhythmus und Dramaturgie bleiben getrennt
beurteilbar. Ein günstiger Reimwert darf eine fehlende Aussageentwicklung
nicht verdecken. Bewusst gesetzte Gegensätze, Perspektivwechsel und Brüche
gehören zu den Gestaltungsmöglichkeiten.

## Schreibwege und Varianten erhalten

Eine Schreibsitzung hält das Anliegen, gewählte Aussagen und Textsegmente,
offene Alternativen sowie die Entwicklung des gesamten Entwurfs fest.
Jeder Übergang nennt Ausgang, Ziel, Beziehungsart, Begründung, Herkunft,
Verfahrensfassung und Urheber des Vorschlags. Ein Urheber kann ein Mensch,
ein Modell oder ein bestimmtes Verfahren sein.

Für jeden Übergang lässt sich untersuchen, was er übernimmt, verändert und
neu ermöglicht. Behauptung, Zitat, belegte Wortgruppe und neue Formulierung
behalten unterscheidbare Herkunft. Frühere Bewertungen und verworfene
Varianten bleiben erhalten. Eine neue Bewertung bekommt eine eigene Fassung.

Für portable Bezüge dient der vorhandene `entry_key` zusätzlich zur lokalen
SQLite-ID. Textsegmente und ihre Aussprachevarianten erhalten eigene Bezüge;
die sichtbare Schreibweise bleibt erhalten. Ein erhaltener Schreibweg kann
anschließend als Material für weitere Texte oder als untersuchbares
Schreibverfahren dienen.

## Bedienung durch Menschen und Maschinen

Oberfläche und Schreibagent verwenden denselben Arbeitsvertrag: Anliegen
anlegen, Alternativen suchen, Beziehungen prüfen, Varianten abzweigen,
Segmente in eine Textfassung übernehmen, eine Gesamtfassung untersuchen
und einen erhaltenen Stand wieder öffnen. Operationen geben die entstandene
Fassung und ihre Herkunft zurück.

Ein selbstständiger Lauf arbeitet mit bezeichnetem Auftrag, Auswahlregeln,
Ressourcenrahmen und Abbruchbedingungen. Er kann Fassungen vergleichen und
gezielt überarbeiten. Ein technisch erfolgreicher Lauf und ein sprachlich
gelungener Text bleiben unterschiedliche Befunde. Bewertungen sollen an
konkreten Stellen nachvollziehbar sein; eine weitere Reimkette allein
belegt noch keine gelungene Strophe.

## Nächster ausführbarer Entwicklungsschritt

Zuerst entsteht eine Schreibsitzung mit Anliegen, Textvarianten und erhaltenen
Übergängen. Die bestehenden Atlas-Operationen `search` und `expand` liefern
die Klangseite. OpenThesaurus-Gruppen und die Textsuche über die vorhandenen
Tatoeba-Sätze können eine erste lexikalisch belegte Bedeutungsachse liefern.
Eine solche Suche erhält ihre Bezeichnung als lexikalischer Zusammenhang;
das Verstehen einer Aussageabsicht benötigt darüber hinaus eigene Verfahren.

Die vorhandenen Graph-Sessions bieten ein Muster für Analysestände und ein
ergänzbares Entscheidungsprotokoll. Die Atlas-Ketten benötigen diese
Versionsgeschichte noch. Die bisherige Bedeutungssuche der persönlichen
Bibliothek ist noch keine semantische Navigation über den gesamten Atlas.

Als erste Gesamtprobe dient ein Thema mit zwei verschiedenen Aussagewegen.
Für beide entstehen Formulierungs- und Reimvarianten. Der ausgewählte Textweg
lässt sich schließen, wieder öffnen und an einer Stelle verändern; seine
Alternativen und früheren Begründungen bleiben zugänglich. Eine weitere Probe
prüft eine klanglich passende Fortsetzung, die die beabsichtigte Aussage
verfehlt: Das System muss diesen Konflikt kenntlich machen können.

## Übergabe an die Songproduktion

Eine bezeichnete Textfassung wird zusammen mit Titel, Abschnittsstruktur,
Stil und Vortragsabsicht zum Produktionspaket. Suno dokumentiert die Eingabe
eigener Texte im [Custom-Modus](https://help.suno.com/en/articles/2415873).
Eine vollständig automatische Übergabe und das Rücklesen des erzeugten Songs
benötigen einen gesondert geprüften Anschluss; im aktuellen REiMWERK ist dieser
noch nicht vorhanden.

Ein Produktionslauf verknüpft seine tatsächlichen Eingaben, Auftragskennung,
Ergebnisse und gewählten Takes mit der verwendeten Textfassung. Der fertige
Song kann als eigenständiges Werk und als Material weiterer Arbeit in den
Zusammenhang zurückkehren.

## Bezug zu den vorhandenen Konzepten

- `INVARIANZ-TRANSDUKTION-WELTENSYSTEM.md`, Konzeptfassung vom 12. Oktober
  2026: Identitäten und Beziehungen bleiben bei wechselnder Metrik und
  Darstellung erhalten.
- KiNTEGRiTY-Systemmodell „Mooncells · Vom Netz zur Werkbildung“, Revision 9,
  gelesen am 27. Oktober 2026: Verfahrensfassungen, tatsächliche Läufe,
  aufgabenbezogene Prüfbefunde und die Verbindungsweise als eigenes Ergebnis.
- [Reimatlas](reimatlas.md): vorhandene Lautsuche, Quellen und geordnete
  Reimfolgen als Ausgangspunkt des Schreibraums.
