"""Fenster mit den Tastenkürzeln (Standard-Widgets, Tab führt immer weiter)."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QPlainTextEdit, QPushButton, QVBoxLayout

from ui.common import name_widget

SHORTCUTS = """\
Seitenaufbau: Frage, Antwort, Aktionen, Verlauf. Mit Tab geht es nach unten, nach dem Verlauf
wieder zur Frage. Umschalt+Tab geht zurück. Alles lässt sich mit Enter bestätigen.

Frage und Antwort
Enter: Frage senden. Das Fragefeld wird danach geleert, jede Frage ergibt einen Verlaufseintrag.
Umschalt+Enter: Zeilenumbruch im Fragefeld
Esc: laufende Anfrage abbrechen (die Frage kommt zurück ins Fragefeld)
Die Antwort ist ein Textfeld, in dem Sie mit den Pfeiltasten lesen und direkt arbeiten können.
Strg+Umschalt+C: Antwort kopieren
Strg+Umschalt+T: nur den Text kopieren (ohne Kommentar des Modells)
Strg+S: Text als Word-Dokument speichern

Aktionen (Liste, Enter führt aus)
Antwort kopieren, Text kopieren, Word-Dokument speichern, Datei hinzufügen, Ordner hinzufügen
Entf bei einer hinzugefügten Datei oder einem Ordner: entfernen (die Datei bleibt unverändert)
Strg+O: Datei hinzufügen. Strg+Umschalt+O: Ordner hinzufügen. Das Modell darf darin lesen.

Verlauf
Die letzten Fragen dieses Chats. Enter, Leertaste oder Klick lädt den Eintrag in die Antwort.
Einträge lassen sich hier nicht löschen.

Menüs (Alt plus Buchstabe)
Alt+P: Projekte. Neues Projekt erstellen (Name eingeben, Tab, OK). Darunter stehen die Projekte.
       Enter auf einem Projekt öffnet es: Neuer Chat, Projektdateien, darunter die Chats.
       Projektdateien: oben Datei hochladen, darunter die Dateien (Menütaste: entfernen).
       Alle Chats des Projekts können diese Dateien lesen, Chats ohne Projekt nicht.
       Enter auf einem Chat öffnet ihn.
Alt+T: Chatliste. Neuer Chat, darunter alle Chats ohne Projekt.
Alt+E: Einstellungen mit Häkchen: Lange Antworten, Nachdenken, Internetrecherche.
       Modell: Gemma 4 (12b) oder Qwen 2.5 VL (7b), das gewählte hat ein Häkchen. Der Wechsel lädt
       das Modell neu (etwa 15 Sekunden). Qwen kann nicht im Internet suchen, keine Ordner lesen
       und nicht nachdenken, das sagt die App an.
       Tavily-Schlüssel: Mit Schlüssel sucht die App über Tavily (besser und schneller),
       ohne Schlüssel oder wenn Tavily ausfällt über DuckDuckGo.
Alt+D: Datei. Datei hinzufügen nimmt Text, Word, PDF und Bilder (JPG, PNG). Lange PDFs, Scans
       und Bilder liest das Modell gezielt, das dauert etwas länger. PDF prüfen: technische Prüfung
       eines PDFs auf abgeschnittenen Text, Überlappung, kleine Schrift und Screenreader-Angaben.
Alt+N: Ansicht
Alt+H: Hilfe

Kontextmenü (Menütaste oder Umschalt+F10 auf einem Eintrag im Menü)
Auf einem Projekt: Projekt entfernen (die Chats bleiben erhalten)
Auf einem Chat in der Chatliste: In Projekt verschieben, Chat entfernen
Auf einem Chat in einem Projekt: In anderes Projekt verschieben, In anderes Projekt kopieren,
Aus dem Projekt in die Chatliste, Chat entfernen
Bei Verschieben und Kopieren erscheint die Projektliste, Enter wählt.

Navigation
Strg+N: neuer Chat
Strg+1: Frage
Strg+2: Antwort
Strg+3: Aktionen
Strg+4: Verlauf
F6 und Umschalt+F6: nächster und vorheriger Bereich

Ansicht
Strg+Plus: Schrift größer
Strg+Minus: Schrift kleiner

Hilfe
F1: dieses Fenster
"""


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tastenkürzel")
        self.text = QPlainTextEdit(SHORTCUTS)
        self.text.setReadOnly(True)
        self.text.setTabChangesFocus(True)
        name_widget(self.text, "Liste der Tastenkürzel")
        close = QPushButton("&Schließen")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(self.text)
        layout.addWidget(close)
        self.resize(560, 560)
        self.text.setFocus()
