"""Aktionen (Tab vom Antwortfeld): eine Liste, Enter führt die markierte Aktion aus.

Immer: Antwort kopieren, Datei hinzufügen, Ordner hinzufügen. Nur wenn es passt: Text kopieren
(wenn das Modell einen Text geschrieben hat) und Word-Dokument speichern (wenn danach gefragt
wurde). Am Ende stehen die hinzugefügten Dateien und Ordner, Entf entfernt einen Eintrag.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ui.common import name_widget

COPY_ANSWER = "copy_answer"
COPY_TEXT = "copy_text"
WORD = "word"
ADD_FILE = "add_file"
ADD_FOLDER = "add_folder"
ATTACHMENT = "attachment"


class ActionsPanel(QWidget):
    actionRequested = Signal(str)                  # eine der Konstanten oben
    removeAttachmentRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.has_text = False
        self.word_filename: str | None = None
        self.attachments: list[str] = []
        self.list = QListWidget()
        self.list.setMinimumHeight(110)
        name_widget(self.list, "Aktionen")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Aktionen:"))          # nur zur Orientierung, ohne Kürzel
        layout.addWidget(self.list)

        self.list.itemActivated.connect(self._activated)      # Enter, Doppelklick
        self.list.itemClicked.connect(self._activated)        # Mausklick
        space = QShortcut(QKeySequence(Qt.Key.Key_Space), self.list)
        space.setContext(Qt.ShortcutContext.WidgetShortcut)
        space.activated.connect(lambda: self._activated(self.list.currentItem()))
        delete = QShortcut(QKeySequence.StandardKey.Delete, self.list)
        delete.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete.activated.connect(self._remove_current)
        self.refresh()

    # -- Inhalt ------------------------------------------------------------------
    def set_state(self, has_text: bool | None = None, word_filename: str | None | bool = False,
                  attachments: list[str] | None = None) -> None:
        """Nur die übergebenen Teile ändern. word_filename=None blendet den Word-Eintrag aus."""
        if has_text is not None:
            self.has_text = has_text
        if word_filename is not False:
            self.word_filename = word_filename
        if attachments is not None:
            self.attachments = attachments
        self.refresh()

    def rows(self) -> list[tuple[str, str]]:
        rows = [(COPY_ANSWER, "Antwort kopieren")]
        if self.has_text:
            rows.append((COPY_TEXT, "Text kopieren"))
        if self.word_filename is not None:
            rows.append((WORD, f"Word-Dokument speichern: {self.word_filename}"
                         if self.word_filename else "Word-Dokument speichern"))
        rows += [(ADD_FILE, "Datei hinzufügen"), (ADD_FOLDER, "Ordner hinzufügen")]
        rows += [(ATTACHMENT, label) for label in self.attachments]
        return rows

    def refresh(self) -> None:
        current = self.list.currentRow()
        self.list.clear()
        for key, label in self.rows():
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.list.addItem(item)
        self.list.setCurrentRow(min(max(current, 0), self.list.count() - 1))

    def texts(self) -> list[str]:
        return [self.list.item(r).text() for r in range(self.list.count())]

    # -- Bedienung -----------------------------------------------------------------
    def _activated(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key == ATTACHMENT:
            return                              # nur Entf entfernt, Enter tut hier nichts
        self.actionRequested.emit(key)

    def _remove_current(self) -> None:
        item = self.list.currentItem()
        if item is None or item.data(Qt.ItemDataRole.UserRole) != ATTACHMENT:
            return
        index = sum(1 for r in range(self.list.currentRow())
                    if self.list.item(r).data(Qt.ItemDataRole.UserRole) == ATTACHMENT)
        self.removeAttachmentRequested.emit(index)

    def focus_attachments_or_actions(self, index: int | None) -> None:
        """Nach dem Entfernen: Fokus auf den nächsten Anhang, sonst auf 'Datei hinzufügen'."""
        self.list.setFocus()
        keys = [self.list.item(r).data(Qt.ItemDataRole.UserRole) for r in range(self.list.count())]
        attachment_rows = [r for r, k in enumerate(keys) if k == ATTACHMENT]
        if attachment_rows and index is not None:
            self.list.setCurrentRow(attachment_rows[min(index, len(attachment_rows) - 1)])
        else:
            self.list.setCurrentRow(keys.index(ADD_FILE))
