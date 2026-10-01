# Chatbot für Text: Konzept und Entscheidungen

Stand: 19.09.2026 (Version 3, Oberfläche neu nach der Beschreibung der Person). Lokaler, barrierefreier Schreib- und Recherche-Assistent für Windows (PySide6, Ollama). Schwesterprogramm von "Assistent - Infos aus PDF", gleicher technischer Unterbau.

## 1. Ziel

Ein Chat, in dem man zusammen mit dem Sprachmodell an Texten arbeitet, ähnlich wie bei Claude: Man stellt eine Frage oder einen Schreibauftrag, das Modell antwortet, und längere Texte (Anschreiben, E-Mail, Bericht) stehen direkt im Antwortfeld, das man frei bearbeiten kann. Man kann Dateien und ganze Ordner hinzufügen, das Modell darf im Internet recherchieren, und ein Text lässt sich als Word-Dokument speichern. Chats lassen sich in Projekten sammeln. Alles läuft lokal, nur die Internetrecherche verlässt den Rechner. Nur Text, keine Bilder.

## 2. Das Hauptfenster

Vier Bereiche mit genau vier Tab-Stopps, von oben nach unten. Nach dem Verlauf führt Tab wieder zur Frage (Umschalt+Tab geht rückwärts). Alles lässt sich mit Enter bestätigen.

1. **Frage:** ein Textfeld. Enter sendet, Umschalt+Enter macht einen Zeilenumbruch. **Nach dem Senden wird das Feld sofort geleert.** Bei Abbruch (Esc) oder Fehler kommt die Frage zurück ins Feld, damit nichts verloren geht.
2. **Antwort:** ein großes, mehrzeiliges Textfeld (mindestens zehn Zeilen, das Fenster startet maximiert). Mit den Pfeiltasten navigieren, und man kann direkt darin arbeiten (Text ändern, ergänzen).
3. **Aktionen:** eine Liste, Enter führt die markierte Aktion aus. Immer: *Antwort kopieren*, *Datei hinzufügen*, *Ordner hinzufügen*. Nur wenn es passt: *Text kopieren* (wenn das Modell einen Text geschrieben hat) und *Word-Dokument speichern* (wenn danach gefragt wurde). Darunter stehen die zu diesem Chat hinzugefügten Dateien und Ordner (Entf entfernt einen Eintrag, die Datei selbst bleibt unangetastet).
4. **Verlauf:** die letzten Fragen dieses Chats untereinander, neueste oben. **Jede neue Frage erzeugt einen neuen Verlaufspunkt.** Enter, Leertaste oder Klick lädt Frage, Antwort und Text dieses Eintrags in das Antwortfeld, der Fokus landet dort. Der Verlauf ist nur zum Nachschlagen: Einträge lassen sich hier nicht löschen. Das Fragefeld bleibt dabei unberührt.

## 3. Menüleiste

Projekte | Chatliste | Einstellungen | Datei | Ansicht | Hilfe (Alt+P, Alt+T, Alt+E, Alt+D, Alt+N, Alt+H).

- **Projekte:** Oberster Eintrag *Neues Projekt …* (Enter öffnet ein Textfeld für den Namen, Tab zu OK). Darunter stehen die Projekte alphabetisch. **Enter auf einem Projekt öffnet dessen Chatliste**, der oberste Eintrag ist *Neuer Chat* (neuer Chat in diesem Projekt), darunter die Chats des Projekts. **Enter auf einem Chat öffnet ihn** im Hauptfenster (Verlauf, letzte Antwort, Gedächtnis, Dateien; Fokus im Antwortfeld).
- **Chatliste:** oberster Eintrag *Neuer Chat* (Strg+N), darunter alle Chats, die in keinem Projekt sind. Enter öffnet.
- **Einstellungen:** *Lange Antworten*, *Nachdenken*, *Internetrecherche* als Einträge mit Häkchen. Enter schaltet um, die App bestätigt per Ansage.
- **Datei:** Datei hinzufügen (Strg+O), Ordner hinzufügen (Strg+Umschalt+O), Text als Word-Dokument speichern (Strg+S), Beenden.
- **Kontextmenü** (Menütaste oder Umschalt+F10 auf einem Eintrag im Menü, auch rechte Maustaste):
  - auf einem **Projekt:** *Projekt entfernen* (die Chats bleiben erhalten und stehen danach in der Chatliste).
  - auf einem **Chat in der Chatliste:** *In Projekt verschieben* (die Projektliste erscheint, Enter wählt), *Chat entfernen*.
  - auf einem **Chat in einem Projekt:** *In anderes Projekt verschieben*, *In anderes Projekt kopieren* (jeweils die Projektliste ohne das eigene Projekt), *Aus dem Projekt in die Chatliste*, *Chat entfernen*.
  - Beim Entfernen fragt ein Dialog nach. Enter bestätigt (vorgewählt ist "Entfernen"), Esc bricht ab.
- Weitere Kürzel ohne Menüeintrag: Esc bricht ab, Strg+Umschalt+C kopiert die Antwort, Strg+Umschalt+T den Text. Strg+1 bis Strg+4 springen zu Frage, Antwort, Aktionen, Verlauf, F6 wechselt reihum. Vollständige Liste: F1.

## 4. Das Antwortfeld als Arbeitsfläche

- Schreibt das Modell einen Text, steht oben sein kurzer Kommentar ("Ich habe das Anschreiben erstellt."), dann eine Leerzeile, dann der Text. "Text kopieren" und der Word-Export nehmen nur den Text, "Antwort kopieren" alles.
- Was im Feld steht (auch mit Ihren Änderungen), geht bei der nächsten Frage als "Aktueller Text" ans Modell, wenn es ein vom Modell geschriebener Text ist oder Sie etwas geändert haben. Eine unveränderte einfache Antwort wird nicht zurückgeschickt.
- Ihre Änderungen gehen nicht verloren: Bevor eine neue Antwort oder ein anderer Chat das Feld ersetzt, werden sie im Verlaufseintrag gespeichert. Jeder Verlaufseintrag ist damit eine Textversion.
- Jede neue Antwort ersetzt den Inhalt des Feldes. Die vorige Fassung bleibt im Verlauf abrufbar.
- Der Text wird auf einmal eingesetzt (keine Live-Anzeige), der Fokus springt danach in das Feld, der Cursor steht am Anfang.

## 5. Chats, Projekte, Speicher

- Ein **Chat** ist eine Unterhaltung mit Gedächtnis. Er wird beim Absenden der ersten Frage angelegt (Titel = Anfang der Frage). Beim Öffnen wird das Gedächtnis aus dem Verlauf wiederhergestellt, ebenso die hinzugefügten Dateien und Ordner. Fehlt eine Datei inzwischen, sagt die App das (dringend).
- Ein **Projekt** fasst Chats zusammen. Ein Chat gehört zu höchstens einem Projekt. *Verschieben* ändert die Zuordnung, *Kopieren* legt eine unabhängige Kopie mit Verlauf und Anhängen im anderen Projekt an.
- Alles steht in `%APPDATA%\TextChat\chats.db`. Ältere Daten aus Version 1 (`history.db`) werden nicht übernommen.

## 6. Dateien und Ordner

- **Datei hinzufügen:** Text, Markdown, CSV, JSON, HTML, Word (docx), PDF mit Text. Der Inhalt geht bei jeder Frage des Chats mit, zusammen höchstens etwa 30000 Zeichen. Längeres wird gekürzt, und die App sagt das.
- **Ordner hinzufügen:** Der ganze Ordner wird freigegeben, nicht in den Kontext geladen. Das Modell hat drei Werkzeuge: `ordner_auflisten`, `in_dateien_suchen`, `datei_lesen` (lange Dateien stückweise). Es liest, was die Frage braucht. Zugriff nur lesend, nur unterhalb des Ordners (keine `..`, keine absoluten Pfade nach außen, keine versteckten Dateien), höchstens 500 Dateien. Unter der Antwort steht "Gelesene Dateien: ...", von der App selbst angefügt (auch wenn das Modell nur einen Suchauszug gebraucht hat).
- Ergebnisse von Werkzeugen, die den Kontext sprengen würden, werden von alt nach neu gekürzt.

## 7. Internetrecherche

`internet_suche` (DuckDuckGo über das Paket ddgs, ohne Schlüssel) und `webseite_lesen`. Höchstens 8 Werkzeug-Schritte je Frage. Die gelesenen Adressen hängt die App als "Quellen aus dem Internet:" an. Nur öffentliche http- und https-Adressen (auch nicht über Weiterleitungen). Inhalte aus dem Internet und aus Dateien gelten dem Modell als Information, nicht als Anweisung. Ist "Internetrecherche" ausgeschaltet, verlassen keine Daten den Rechner.

## 8. Text und Word-Dokument

Das Modell schreibt längere Texte in einen Block `<dokument titel="...">...</dokument>` und außerhalb nur kurz, was es getan hat (core/prompts.py). Die App zieht den Block heraus. Verlangt die Person eine Word-Datei, hängt das Modell `<word_dokument dateiname="..."/>` an, und der Eintrag erscheint bei den Aktionen. Strg+S speichert jederzeit.

## 9. Modell

Standard ist gemma4:12b (siehe DECISIONS.md), an einer Stelle änderbar: core/config.py (DEFAULT_CHAT_MODEL). Es muss Werkzeuge und Denken können. Der Schalter "Nachdenken" setzt den Denk-Modus ein, der Denktext wird nicht angezeigt.

## 10. Struktur

- app.py, start.bat
- core: config.py (Modellwahl), llm.py (Schnittstelle), ollama_backend.py, engine.py, prompts.py, tools.py, websearch.py, folders.py, files.py, wordexport.py, conversation.py, store.py, hardware.py
- ui: main_window.py, question_panel.py, answer_panel.py, actions_panel.py, history_panel.py, menus.py (Menü mit Kontextmenü), announcer.py, dialogs.py, workers.py, common.py
- scripts: setup_engine.py, try_chat.py, hardware_report.py
- tests: test_core.py, test_ui.py, test_integration.py (echte Modelle, nur mit pytest -m integration)
- KONZEPT.md, DECISIONS.md, MODELLE.md, ACCESSIBILITY_TESTS.md

## 11. Bewusst nicht enthalten

Bilder, Sprachausgabe, Live-Anzeige während des Erzeugens (wegen Screenreader), Formatierung im Textfeld (nur reiner Text mit Absätzen und Aufzählungen), Suche in gescannten Dokumenten, Dateien auf Projektebene (Dateien und Ordner gehören zum einzelnen Chat), Löschen einzelner Verlaufseinträge, Übernahme des alten Verlaufs aus Version 1.
