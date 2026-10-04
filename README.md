# Chatbot für Text

Deutsch | [English](README.en.md)
Ein lokaler, barrierefreier Schreib- und Recherche-Assistent für Windows.

## Download
Es gibt eine Exe für Windows.

## Funktionen
- Zusammenarbeit mit einem Sprachmodell an Texten.
- Bearbeiten von langen Texten wie Anschreiben, E-Mail oder Berichten direkt im Antwortfeld.
- Hinzufügen von Dateien und ganzen Ordnern.
- Internetrecherche durch das Modell.
- Speichern von Texten als Word-Dokumente.
- Sammeln von Chats in Projekten.
- Lokale Verarbeitung (außer bei der Internetrecherche).

## Bedienung
- Navigation mit Tab-Stopps zwischen Frage, Antwort, Aktionen und Verlauf.
- Bestätigen mit der Enter-Taste.
- Zeilenumbruch mit Umschalt+Enter im Fragenfeld.
- Abbrechen mit der Esc-Taste.
- Auswahl und Ausführung von Aktionen über die Liste (z.B. Antwort kopieren, Datei hinzufügen).

## Systemanforderungen
Windows.

## Werkzeuge und Bibliotheken

- PySide6
- pymupdf
- httpx
- psutil
- ddgs
- python-docx
- pytest
- pytest-qt

## Installation aus dem Quellcode

Sie brauchen Python 3.11 oder neuer und Git.

```
git clone https://github.com/1013hPascal/Chatbot-fuer-Text.git
cd Chatbot-fuer-Text
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Windows-Warnungen

Windows warnt vielleicht mit „Der Computer wurde durch Windows geschützt“, weil die Exe nicht signiert ist. Wählen Sie „Weitere Informationen“ und dann „Trotzdem ausführen“.

## Lizenz

Lizenz: MIT. Der vollständige Text steht in [LICENSE](LICENSE).
