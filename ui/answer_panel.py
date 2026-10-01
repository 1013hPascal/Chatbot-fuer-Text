"""Antwortfeld: mehrzeilig, groß und frei bearbeitbar. Hier arbeitet man mit dem Modell am Text.

Schreibt das Modell einen Text (Anschreiben, E-Mail ...), steht oben sein kurzer Kommentar, dann
eine Leerzeile, dann der Text. Kopieren und Word-Export nehmen nur den Text. Was in dem Feld
steht (auch mit Ihren Änderungen), geht bei der nächsten Frage ans Modell, wenn es ein Text ist
oder Sie ihn geändert haben.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core import textlayout
from ui.common import PlainEdit, name_widget

SEPARATOR = "\n\n"
MIN_LINES = 10


class AnswerPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QLabel("Antwort:")             # ohne Alt-Kürzel, siehe question_panel.py
        self.edit = PlainEdit()
        self.edit.setTabChangesFocus(True)
        self.edit.setCursorWidth(2)
        self.label.setBuddy(self.edit)
        name_widget(self.edit, "Antwort")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        layout.addWidget(self.edit, 1)
        self.is_doc = False
        self._prefixes: list[str] = []  # Kommentar samt Leerzeile vor dem Text (in Zeilen und roh)
        self.update_height()

    def update_height(self) -> None:
        """Mindestens zehn Zeilen hoch, auch nach Änderung der Schriftgröße."""
        self.edit.setMinimumHeight(self.edit.fontMetrics().lineSpacing() * MIN_LINES + 16)

    # -- Inhalt setzen -------------------------------------------------------------
    def load(self, answer: str, comment: str = "", is_doc: bool = False) -> None:
        """Ganzen Inhalt auf einmal setzen, Cursor an den Anfang."""
        self.is_doc = is_doc
        self._prefixes = ([textlayout.to_lines(comment) + SEPARATOR, comment + SEPARATOR]
                          if is_doc and comment else [])
        self.edit.setPlainText(answer)
        cursor = self.edit.textCursor()
        cursor.setPosition(0)
        self.edit.setTextCursor(cursor)
        self.edit.verticalScrollBar().setValue(0)
        self.edit.document().setModified(False)

    def set_result(self, comment: str, doc_text: str | None) -> str:
        """Ergebnis einer Modellantwort anzeigen. Gibt den Feldinhalt zurück.

        Antwort und Kommentar stehen zeilenweise (ein Satz je Zeile), siehe core/textlayout.py. Der
        Text eines Dokuments bleibt unverändert."""
        shown = textlayout.to_lines(comment)
        if doc_text is None:
            self.load(shown)
        else:
            self.load(shown + SEPARATOR + doc_text, comment, True)
        return self.text()

    def clear(self) -> None:
        self.load("")

    # -- Inhalt lesen ----------------------------------------------------------------
    def text(self) -> str:
        return self.edit.toPlainText()

    def is_modified(self) -> bool:
        return self.edit.document().isModified()

    def mark_saved(self) -> None:
        self.edit.document().setModified(False)

    def document_text(self) -> str:
        """Nur der Text ohne den Kommentar des Modells (sonst der ganze Inhalt)."""
        text = self.text()
        if self.is_doc:
            for prefix in self._prefixes:
                if text.startswith(prefix):
                    return text[len(prefix):]
        return text

    def context_text(self) -> str:
        """Was das Modell bei der nächsten Frage als 'Aktueller Text' bekommt."""
        return self.document_text() if (self.is_doc or self.is_modified()) else ""
