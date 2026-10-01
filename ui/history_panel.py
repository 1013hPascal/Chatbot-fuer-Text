"""Verlauf des aktuellen Chats: die letzten Fragen untereinander, neueste oben.

Nur zum Nachschlagen: Enter, Leertaste oder Klick lädt Frage, Antwort und Text dieses Eintrags in
das Antwortfeld. Einträge lassen sich hier nicht löschen (der ganze Chat lässt sich in der
Chatliste entfernen).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from core.store import Exchange
from ui.common import name_widget


def entry_text(entry: Exchange) -> str:
    question = " ".join(entry.question.split())
    if len(question) > 80:
        question = question[:80].rstrip() + " …"
    text = f"{question}, {entry.created:%d.%m.%Y}, {entry.created:%H:%M}"
    if entry.is_doc:
        text += ", mit Text"
    return text


class HistoryPanel(QWidget):
    entryActivated = Signal(object)        # Exchange

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: dict[int, Exchange] = {}
        self.list = QListWidget()
        self.list.setMinimumHeight(90)
        name_widget(self.list, "Verlauf")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Verlauf:"))           # nur zur Orientierung, ohne Kürzel
        layout.addWidget(self.list)

        self.list.itemActivated.connect(self._activated)      # Enter, Doppelklick
        self.list.itemClicked.connect(self._activated)        # Mausklick
        space = QShortcut(QKeySequence(Qt.Key.Key_Space), self.list)
        space.setContext(Qt.ShortcutContext.WidgetShortcut)
        space.activated.connect(lambda: self._activated(self.list.currentItem()))

    def set_entries(self, entries: list[Exchange]) -> None:
        """Neueste zuerst."""
        self._entries = {e.id: e for e in entries}
        self.list.clear()
        for entry in entries:
            self._add(entry, at_end=True)

    def add_on_top(self, entry: Exchange) -> None:
        """Neuer Verlaufspunkt für eine neue Frage. Er wird zum aktuellen Eintrag."""
        self._entries[entry.id] = entry
        self._add(entry, at_end=False)
        self.list.setCurrentRow(0)

    def update_entry(self, entry: Exchange) -> None:
        self._entries[entry.id] = entry

    def _add(self, entry: Exchange, at_end: bool) -> None:
        item = QListWidgetItem(entry_text(entry))
        item.setData(Qt.ItemDataRole.UserRole, entry.id)
        if at_end:
            self.list.addItem(item)
        else:
            self.list.insertItem(0, item)

    def _activated(self, item: QListWidgetItem | None) -> None:
        if item is not None:
            self.entryActivated.emit(self._entries[item.data(Qt.ItemDataRole.UserRole)])

    def entries(self) -> list[Exchange]:
        """Neueste zuerst, wie angezeigt."""
        return [self._entries[self.list.item(r).data(Qt.ItemDataRole.UserRole)]
                for r in range(self.list.count())]

    def count(self) -> int:
        return self.list.count()
