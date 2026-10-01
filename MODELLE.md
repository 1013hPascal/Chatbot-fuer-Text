# Modelle und Software: Überblick, Installation und Entfernen

Stand: 19.09.2026. Alle Modelle liegen lokal auf diesem Rechner und werden von Ollama verwaltet. Beide Programme (Assistent - Infos aus PDF und Chatbot für Text) teilen sich denselben Ollama-Speicher und dieselbe Python-Umgebung.

## Installierte Modelle (aktueller Stand)

| Modell | Größe | Wird benutzt von | Herkunft |
|---|---|---|---|
| gemma4:12b | 7,6 GB | Chatbot für Text (Standard) | am 19.09.2026 von Claude für dieses Programm geladen |
| qwen2.5vl:7b | 6,0 GB | Assistent - Infos aus PDF (Antworten, gescannte Seiten); seit 20.09.2026 auch in "Chatbot für Text" wählbar (Einstellungen, Modell) | war schon vor den Projekten installiert |
| bge-m3 | 1,2 GB | Assistent - Infos aus PDF (Suche) | am 19.09.2026 von Claude für das PDF-Programm geladen |

Zusammen 13,7 GB in `C:\Users\pasca\.ollama\models`. Wer nur "Chatbot für Text" nutzt, braucht nur `gemma4:12b`. Wer nur den PDF-Assistenten nutzt, braucht `qwen2.5vl:7b` und `bge-m3`.

## Was Claude beim Bauen zusätzlich verwendet hat

| Modell | Zweck | Stand |
|---|---|---|
| qwen3:8b (5,2 GB) | Nur zum Vergleich mit gemma4:12b (Modelltest für "Chatbot für Text") | **am 19.09.2026 wieder entfernt** (`ollama rm qwen3:8b`) |
| qwen3.5:9b (6,6 GB) | Nachtest für "Chatbot für Text" (zweiter Vergleich) | **am 20.09.2026 wieder entfernt** (`ollama rm qwen3.5:9b`) |
| qwen3.8:27b (18 GB) | Sollte mitgetestet werden, ließ sich aber nicht laden (braucht neueres Ollama als 0.31.1) | nie installiert |

Ergebnis der Vergleiche steht in `DECISIONS.md`, die Liste der benutzten KI Tools und Algorithmen in `BENUTZTE_TOOLS.md`. Sonst wurden keine Modelle geladen.

## Aktuelle Liste abrufen

In PowerShell (Ollama muss laufen, siehe unten):

```
ollama list
```

## Ein Modell entfernen

```
ollama rm MODELLNAME
```

Beispiele:

```
ollama rm gemma4:12b
ollama rm bge-m3
ollama rm qwen2.5vl:7b
```

Das gibt den Speicherplatz sofort frei. Vorher die Programme schließen. Entfernen Sie nur Modelle, die kein Programm mehr braucht (siehe Tabelle oben). Ein entferntes Modell lässt sich jederzeit mit `ollama pull MODELLNAME` wieder herunterladen.

## Ein anderes Modell für "Chatbot für Text" verwenden

1. Neues Modell herunterladen: `ollama pull MODELLNAME`
2. Namen eintragen: in `core/config.py` die Zeile `DEFAULT_CHAT_MODEL` ändern. Falls bereits eine Datei `%APPDATA%\TextChat\config.json` existiert, steht der Name auch dort im Feld `chat_model` und hat Vorrang.
3. Altes Modell entfernen, falls nicht mehr gebraucht: `ollama rm ALTER_NAME`

Das Modell muss "Werkzeuge" (tools) und für den Schalter "Nachdenken" auch "thinking" können. Das steht bei jedem Modell auf https://ollama.com/library. Ohne Thinking-Fähigkeit funktioniert das Programm trotzdem, der Schalter "Nachdenken" hat dann keine Wirkung. Ohne Werkzeug-Fähigkeit funktionieren Internetrecherche und Ordnerzugriff nicht.

Vor einem Wechsel lohnt ein Probelauf, der Anschreiben, Änderungswunsch, Word-Wunsch, Nachdenken und Internetfrage prüft:

```
python scripts/try_chat.py --model NEUES_MODELL
```

Hinweis: Ein solcher Probelauf belastet die Grafikeinheit lange. Bei diesem Laptop gab es bei sehr langen Testläufen mit dem 12-Milliarden-Modell zweimal einen Systemabsturz (Windows-Hardwarefehler). Nicht mehrere Läufe hintereinander starten, Netzteil verwenden, Treiber und BIOS aktuell halten.

## Wenn "ollama" nicht gefunden wird oder nicht antwortet

- Die Befehle `ollama list` und `ollama rm` brauchen einen laufenden Ollama-Server. Die Programme starten ihn selbst. Ohne Programm in einer PowerShell starten:
  ```
  ollama serve
  ```
  und in einem zweiten PowerShell-Fenster die Befehle ausführen. Danach den Server wieder beenden (Strg+C im ersten Fenster).
- Wenn der Befehl `ollama` gar nicht bekannt ist, liegt das Programm hier: `C:\Users\pasca\AppData\Local\Programs\Ollama\ollama.exe`.
- Nach dem Beenden eines Programms über den Task-Manager bleiben Prozesse namens `ollama` und `llama-server` zurück. Sie belegen Arbeitsspeicher und sollten dort ebenfalls beendet werden. Schließen Sie die Programme deshalb immer normal (Alt+F4 oder Datei, Beenden).

## Software, die Claude für die Programme installiert hat

Alles Übrige (Ollama selbst, Python 3.14, der Umgebungsvariable `OLLAMA_IGPU_ENABLE`) war schon vorher auf dem Rechner.

| Was | Wo | Wozu |
|---|---|---|
| Python-Umgebung `pdfchat` | `C:\venvs\pdfchat` | gemeinsam für beide Programme. Pakete: PySide6, pymupdf, numpy, httpx, psutil, ddgs (Internetsuche), python-docx (Word-Dateien), pytest, pytest-qt (nur für Tests) |
| Programmordner | `...\Projekte\Chatbot für PDF\Assistent - Infos aus PDF` und `...\Projekte\Chatbot für Text` | die Programme selbst |
| Daten PDF-Assistent | `%APPDATA%\PDFChat` | Dokumentindex, Einstellungen, Protokolle |
| Daten Chatbot für Text | `%APPDATA%\TextChat` | Chats, Projekte, Einstellungen, Protokolle (`history.db` ist ein Rest aus Version 1 und wird nicht mehr gebraucht) |

Temporäre Testdateien, die Claude im Windows-Temp-Ordner angelegt hatte, sind am 19.09.2026 gelöscht worden.

## Alles deinstallieren (theoretisch)

Reihenfolge, wenn Sie alles von diesem Projekt wieder entfernen wollen:

1. Beide Programme schließen. Im Task-Manager prüfen, dass keine Prozesse `ollama`, `llama-server` oder `pythonw` laufen.
2. Modelle entfernen (Ollama muss laufen):
   ```
   ollama rm gemma4:12b
   ollama rm bge-m3
   ```
   `qwen2.5vl:7b` war schon vorher da. Entfernen Sie es nur, wenn Sie es nirgends sonst brauchen: `ollama rm qwen2.5vl:7b`.
3. Daten der Programme löschen: die Ordner `%APPDATA%\PDFChat` und `%APPDATA%\TextChat` (im Explorer die Adresse `%APPDATA%` eingeben). Ihre PDF-Dateien und alle anderen Dokumente bleiben dabei unangetastet.
4. Python-Umgebung löschen: den Ordner `C:\venvs\pdfchat` (und danach `C:\venvs`, wenn er leer ist).
5. Programmordner löschen: `Assistent - Infos aus PDF`, `Chatbot für Text` und die Projektordner darüber, wenn Sie sie nicht mehr wollen.
6. Nur wenn Sie Ollama nicht mehr brauchen: Windows-Einstellungen, Apps, Ollama deinstallieren. Der Ordner `C:\Users\pasca\.ollama` mit den restlichen Modellen bleibt dabei liegen und kann von Hand gelöscht werden.

Nur einzelne Pakete aus der Python-Umgebung entfernen (falls die Umgebung bleiben soll):

```
C:\venvs\pdfchat\Scripts\python.exe -m pip uninstall ddgs python-docx
```
