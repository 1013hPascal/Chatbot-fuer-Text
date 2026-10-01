# Tests zur Barrierefreiheit: Chatbot für Text (Version 3)

## 1. Automatisch geprüft (pytest, 120 schnelle Tests bestanden)

- **Tab-Reihenfolge:** genau vier Tab-Stopps: Frage, Antwort, Aktionen, Verlauf. Nach dem Verlauf führt Tab zur Frage, Umschalt+Tab von der Frage zum Verlauf.
- **Frage:** Enter sendet und leert das Feld sofort. Bei Abbruch oder Fehler kommt die Frage zurück. Umschalt+Enter macht einen Zeilenumbruch.
- **Antwortfeld:** mehrzeilig, mindestens zehn Zeilen hoch, bearbeitbar, Pfeiltasten bewegen den Cursor, Cursor am Anfang nach einer Antwort, Fokus danach im Feld.
- **Aktionen:** Liste mit Antwort kopieren, Datei hinzufügen, Ordner hinzufügen. Text kopieren und Word-Dokument speichern erscheinen nur, wenn sie passen. Enter führt aus, Entf entfernt nur hinzugefügte Dateien und Ordner (die Dateien bleiben).
- **Verlauf:** nur ansehen, keine Schaltflächen, Entf löscht nichts. Jede neue Frage ergibt einen neuen Eintrag oben. Enter, Leertaste und Klick laden in die Antwort, das Fragefeld bleibt unberührt.
- **Menüleiste:** Projekte, Chatliste, Einstellungen, Datei, Ansicht, Hilfe. Oberster Eintrag bei Projekten: Neues Projekt, bei der Chatliste: Neuer Chat.
- **Projekte:** Enter öffnet die Chatliste des Projekts, oberster Eintrag Neuer Chat. Neue Chats dort gehören zum Projekt. Enter auf einem Chat öffnet ihn samt Verlauf und Gedächtnis.
- **Chatliste:** nur Chats ohne Projekt.
- **Kontextmenü:** Auf Projekten: Projekt entfernen. Auf Chats in der Chatliste: In Projekt verschieben, Chat entfernen. Auf Chats in Projekten: In anderes Projekt verschieben, In anderes Projekt kopieren, Aus dem Projekt in die Chatliste, Chat entfernen. Die Projektlisten enthalten nicht das eigene Projekt. Menütaste und Umschalt+F10 lösen das Kontextmenü aus (nur auf Einträgen mit Kontextmenü). Entfernen fragt nach, Enter bestätigt.
- **Einstellungen im Menü:** drei Einträge mit Häkchen, Zustand stimmt, wird gespeichert, angesagt und wirkt bei der nächsten Frage.
- **Namen und Kürzel:** Jedes Steuerelement hat einen Namen für Screenreader. Kein Alt-Kürzel ist doppelt belegt.
- **Keine festen Farben** (Hochkontrast bleibt wirksam).

## 2. Noch zu prüfen (nur mit echtem Screenreader und Tastatur möglich)

Bitte auf dem Zielrechner mit NVDA durchgehen und Ergebnis eintragen (ok, Problem, Anmerkung). Besonders die Menütaste in Menüs (Nr. 3 bis 5) wurde nur mit simulierten Tastendrücken geprüft.

| Nr. | Prüfpunkt | Ergebnis |
|---|---|---|
| 1 | Programmstart: Fenster maximiert, Fokus im Fragefeld, Ansage "Bereit. GPU: ..." Fenstertitel nennt Chat und Projekt. | |
| 2 | Tab-Kreis: Frage, Antwort, Aktionen, Verlauf, Frage. Aktionen und Verlauf werden als Listen mit Anzahl der Einträge gelesen. | |
| 3 | Projekte (Alt+P): Pfeil runter auf Neues Projekt, Enter, Namensfeld, Tab zu OK, Enter. Danach steht das Projekt im Menü. | |
| 4 | Enter auf einem Projekt öffnet die Chatliste, "Neuer Chat" ist der erste Eintrag, Enter auf einem Chat öffnet ihn. NVDA liest Untermenüs als solche. | |
| 5 | Menütaste oder Umschalt+F10 auf einem Projekt und auf Chats: Das Kontextmenü erscheint, Untermenüs (Projektliste) sind mit Pfeil rechts oder Enter erreichbar, Enter wählt, danach schließen sich alle Menüs. Der erste Eintrag ist beim Öffnen markiert und wird vorgelesen. Nach der Auswahl steht der Fokus wieder im Fenster. Falls nichts erscheint: Prüfen, ob in %APPDATA%\TextChat\logs\app.log die Zeile "Kontextmenü angefordert" steht (dann kam die Taste an, und es liegt an der Ansage). Fehlt die Zeile, kommt die Taste nicht an: Rückmeldung an Claude, dann gibt es eine Ersatzlösung. | |
| 5a | Alt+P, Pfeil runter: NVDA nennt gleich "Neues Projekt" (nicht "Chatbot für Text Menü"). Kontextmenü auf einem Projekt: NVDA nennt "Projekt entfernen". Auf einem Chat: erster Eintrag "In Projekt verschieben" wird genannt, Pfeil runter und hoch stimmen. | |
| 5b | Projektdateien (Alt+P, Projekt mit Enter oder Pfeil rechts öffnen: "Neuer Chat", "Projektdateien", dann die Chats): Projektdateien öffnen, oben "Datei hochladen …" (Enter öffnet den Dateidialog), darunter die Dateien. Menütaste auf einer Datei: "Datei entfernen", Enter, Rückfrage mit Enter bestätigen. In einem neuen Chat dieses Projekts fragen, was in der Datei steht. In einem Chat ohne Projekt darf die Datei nicht bekannt sein. | |
| 5c | Tavily: Alt+E, "Tavily-Schlüssel …": Dialog mit Eingabefeld (Schlüssel von tavily.com einfügen, Enter). NVDA sagt "Tavily-Schlüssel gespeichert. Die Suche nutzt Tavily." Danach eine Frage mit Internetrecherche stellen: Kommt eine Antwort mit Quellen? Zum Gegenprobe einen falschen Schlüssel eintragen: Es kommt die Ansage "Der Tavily-Schlüssel wurde abgelehnt. Es wird DuckDuckGo genutzt." und trotzdem eine Antwort. | |
| 5d | Modellwahl: Alt+E, Pfeil runter bis "Modell", Pfeil rechts: zwei Einträge, NVDA sagt bei einem "angehakt" (nicht angehakt beim anderen). Enter auf dem anderen: Ansage "Modell ... gewählt. Es wird geladen.", nach etwa 15 s "Bereit. GPU: ...". Bei Qwen mit eingeschalteter Internetrecherche folgt "Dieses Modell kann nicht im Internet suchen." Während das Modell lädt oder eine Anfrage läuft, sind die Einträge ausgegraut. | |
| 5e | PDFs und Bilder: Datei, "Datei hinzufügen" (Strg+O), ein PDF wählen: NVDA sagt Seitenzahl und ob es ganz im Prompt steht ("… Wörter") oder zu lang ist ("Das Modell sucht und liest gezielt Seiten"). Ein gescanntes PDF: "… ohne Text (Scan)". Ein Foto (JPG, PNG): "… Das Modell sieht es sich an, wenn Sie danach fragen." Danach fragen, was auf dem Bild steht: Status "Seite wird angesehen", dann die Antwort. Bei einer Frage zu einem langen PDF nennt die Antwort die Seite. | |
| 5f | PDF prüfen: Datei, "PDF prüfen …", ein PDF wählen. NVDA sagt "PDF … wird geprüft", dauert Sekunden, der Bericht steht in der Antwort (Dokument zuerst, dann Seiten; "Auffällige Seiten: …"). Lässt sich der Bericht mit Pfeiltasten gut lesen? Rückfrage zum Bericht im selben Chat möglich? | |
| 5g | Tempo: Internetfrage wie "Was kostet das Deutschlandticket aktuell?" antwortet in etwa 10 statt 18 Sekunden. Die Status-Ansage "Internetrecherche: …" kommt weiterhin. Stimmt die Antwort? Bei Zweifeln web_prefetch in %APPDATA%\TextChat\config.json auf false setzen. | |
| 5h | Fragefeld: Zwei Zeilen schreiben (Umschalt+Enter dazwischen). Sagt NVDA "Zeile"/leer, steht der weitere Text auf der Braillezeile in einer neuen Zeile, und kein Sonderzeichen ist zu sehen? Pfeil hoch und runter wechselt zwischen den Zeilen. Enter sendet, Strg+Enter auch. Antwortfeld: Eine Antwort mit mehreren Sätzen steht mit einem Satz je Zeile. Pfeil runter geht Zeile für Zeile, Braille zeigt die jeweilige Zeile. Quellen stehen je eine Zeile mit "- ". | |
| 6 | Chat entfernen und Projekt entfernen: Rückfrage wird vorgelesen, Enter bestätigt. | |
| 7 | Chatliste (Alt+T): Neuer Chat oben, Chats darunter, Enter öffnet. | |
| 8 | Einstellungen (Alt+E): NVDA sagt, ob die Einträge angehakt sind. Nach dem Umschalten kommt zusätzlich die App-Ansage. Kommt der Zustand doppelt, in ui/main_window.py (_on_setting) die Ansage entfernen. | |
| 9 | Enter im Fragefeld: Feld wird leer, Ansage "Anfrage wird bearbeitet.", Statusansagen, danach Fokus in der Antwort. Sind es zu viele Ansagen? Dann in ui/main_window.py (_on_status) einschränken. | |
| 10 | Antwort fertig: Wird der Inhalt doppelt gelesen (Ansage plus Feld)? Falls ja, "Antwort fertig. ..." in _on_answer kürzen. | |
| 11 | Antwortfeld: Zeile für Zeile lesen, wortweise mit Strg+Pfeil, selbst schreiben. | |
| 12 | Aktionen: Enter auf Antwort kopieren, Datei hinzufügen (Dateidialog), Ordner hinzufügen. Hinzugefügtes steht am Listenende, Entf entfernt. | |
| 13 | Verlauf: Pfeiltasten lesen die Einträge, Enter lädt und springt in die Antwort. | |
| 14 | Word speichern (Strg+S oder Aktion): Dateidialog bedienbar, Ansage danach. | |
| 15 | Abbruch mit Esc während der Suche und während des Nachdenkens. | |
| 16 | Fehlerfall (Ollama beenden, Frage stellen): dringende Ansage und Meldungsfenster, danach steht die Frage wieder im Feld. | |
| 17 | Windows-Hochkontrast-Design: Menühäkchen und alle Texte sichtbar. | |
