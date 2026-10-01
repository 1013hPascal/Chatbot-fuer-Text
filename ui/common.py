"""Kleine Hilfen für die Oberfläche."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QPlainTextEdit, QWidget


class PlainEdit(QPlainTextEdit):
    """Mehrzeiliges Textfeld mit echten Zeilenumbrüchen.

    Qt fügt bei Umschalt+Enter sonst den Unicode-Zeilentrenner U+2028 ein: Der Text bleibt dann im
    selben Absatz, und Screenreader und Braillezeile sehen keine neue Zeile. Hier wird daraus ein
    richtiger Absatz. Dasselbe gilt für eingefügten Text."""

    def keyPressEvent(self, event) -> None:
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.insertPlainText("\n")
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source) -> None:
        if source.hasText():
            self.insertPlainText(source.text().replace("\u2028", "\n").replace("\u2029", "\n"))
        else:
            super().insertFromMimeData(source)


def name_widget(widget: QWidget, name: str) -> None:
    """Namen für Screenreader setzen. Bewusst keine Beschreibung: Die Braillezeile zeigt sonst
    Name, Rolle und Beschreibung, und Tastenkürzel gehören nur ins Menü."""
    widget.setAccessibleName(name)


def confirm(parent: QWidget, title: str, text: str, yes: str = "Ja", no: str = "Nein",
            default_yes: bool = False) -> bool:
    """Standard-Rückfrage mit deutschen Schaltflächen. Enter wählt die Vorgabe, Esc bricht ab.
    Vorgabe ist standardmäßig die sichere Antwort (Nein)."""
    box = QMessageBox(QMessageBox.Icon.Question, title, text, QMessageBox.StandardButton.NoButton,
                      parent)
    yes_button = box.addButton(yes, QMessageBox.ButtonRole.YesRole)
    no_button = box.addButton(no, QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(yes_button if default_yes else no_button)
    box.setEscapeButton(no_button)
    box.exec()
    return box.clickedButton() is yes_button


def show_info(parent: QWidget, title: str, text: str) -> None:
    box = QMessageBox(QMessageBox.Icon.Information, title, text,
                      QMessageBox.StandardButton.NoButton, parent)
    box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def show_error(parent: QWidget, title: str, text: str) -> None:
    box = QMessageBox(QMessageBox.Icon.Warning, title, text, QMessageBox.StandardButton.NoButton,
                      parent)
    box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    box.exec()
