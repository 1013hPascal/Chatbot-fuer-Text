"""Bereich 3: Frage. Ein Textfeld, Enter sendet. Kein Absenden-Knopf im Tab-Weg, damit auf das
Fragefeld direkt die Antwort folgt."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.common import PlainEdit, name_widget


class QuestionEdit(PlainEdit):
    """Enter und Strg+Enter senden, Umschalt+Enter macht einen echten Zeilenumbruch (neue Zeile)."""
    submitted = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setTabChangesFocus(True)          # keine Tastenfalle

    def keyPressEvent(self, event) -> None:
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class QuestionPanel(QWidget):
    askRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Bewusst ohne Alt-Kürzel ("&"): Qt meldet das Kürzel des Beschriftungs-Buddys sonst als
        # Tastenkürzel des Feldes an den Screenreader, und es erscheint auf der Braillezeile.
        self.label = QLabel("Ihre Frage:")
        self.edit = QuestionEdit()
        self.label.setBuddy(self.edit)
        name_widget(self.edit, "Ihre Frage")
        self.status = QLabel("")
        name_widget(self.status, "Status")
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        layout.addWidget(self.edit)
        layout.addWidget(self.status)
        self.edit.submitted.connect(self.askRequested)
        self.update_height()

    def update_height(self) -> None:
        """Etwa drei Zeilen hoch, auch nach Änderung der Schriftgröße."""
        margins = int(self.edit.document().documentMargin() * 2) + 2 * self.edit.frameWidth()
        self.edit.setFixedHeight(self.edit.fontMetrics().lineSpacing() * 3 + margins + 4)

    def set_status(self, text: str) -> None:
        self.status.setText(text)
