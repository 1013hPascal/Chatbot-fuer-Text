"""Menü mit Kontextmenü auf den Einträgen (Menütaste, Umschalt+F10 oder rechte Maustaste)."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAccessible, QAccessibleEvent, QContextMenuEvent
from PySide6.QtWidgets import QApplication, QMenu

# Windows meldet Menütaste und Umschalt+F10 je nach Lage als Taste, als Kontextmenü-Ereignis oder
# beides nacheinander. Das Ereignis direkt nach einer schon behandelten Taste wird ignoriert,
# sonst öffnete sich das Kontextmenü zweimal.
_KEY_DEDUP_SECONDS = 0.5
_last_key_request = 0.0


FOCUS_REPEAT_MS = 200


class AccessibleMenu(QMenu):
    """Menü mit eigenem Namen und verlässlicher Ansage des ersten Eintrags.

    Ohne Namen nennt NVDA beim Öffnen den Programmnamen ("Chatbot für Text Menü"). Die Meldung des
    ersten markierten Eintrags geht dabei unter. Deshalb wird sie kurz nach dem Öffnen noch einmal
    gesendet, sobald ein Eintrag markiert ist."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(title, parent)
        self.setAccessibleName(title.replace("&", ""))
        self._repeat_pending = False
        self.hovered.connect(self._schedule_repeat)

    def showEvent(self, event) -> None:
        self._repeat_pending = True
        super().showEvent(event)

    def _schedule_repeat(self, _action=None) -> None:
        if self._repeat_pending:
            self._repeat_pending = False
            QTimer.singleShot(FOCUS_REPEAT_MS, self.repeat_focus_event)

    def repeat_focus_event(self) -> None:
        action = self.activeAction()
        if action is None or not self.isVisible():
            return
        event = QAccessibleEvent(self, QAccessible.Event.Focus)
        event.setChild(self.actions().index(action))
        QAccessible.updateAccessibility(event)


class ContextMenu(AccessibleMenu):
    """Ein Eintrag mit Daten (QAction.data) kann ein Kontextmenü bekommen. Das Menü meldet das
    mit contextRequested(Eintrag, Bildschirmposition)."""
    contextRequested = Signal(object, object)

    def _request_for_active(self) -> bool:
        action = self.activeAction()
        if action is None or action.data() is None:
            return False
        self.contextRequested.emit(action, self.mapToGlobal(self.actionGeometry(action).center()))
        return True

    def keyPressEvent(self, event) -> None:
        global _last_key_request
        is_menu_key = event.key() == Qt.Key.Key_Menu or (
            event.key() == Qt.Key.Key_F10 and event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if is_menu_key and self.activeAction() is not None and self.activeAction().data() is not None:
            _last_key_request = time.monotonic()
            self._request_for_active()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        if event.reason() == QContextMenuEvent.Reason.Keyboard:
            # Tastatur: die Mausposition sagt nichts, der markierte Eintrag zählt.
            if time.monotonic() - _last_key_request < _KEY_DEDUP_SECONDS:
                event.accept()
                return
            if self._request_for_active():
                event.accept()
                return
            super().contextMenuEvent(event)
            return
        action = self.actionAt(event.pos())
        if action is not None and action.data() is not None:
            self.contextRequested.emit(action, event.globalPos())
            return
        super().contextMenuEvent(event)


def close_all_popups() -> None:
    """Nach einer Auswahl im Kontextmenü auch die darunterliegenden Menüs schließen.
    Begrenzt und mit Wiederholungsschutz, damit die Schleife nie endlos läuft."""
    last = None
    for _ in range(10):
        popup = QApplication.activePopupWidget()
        if popup is None or popup is last:
            return
        last = popup
        popup.close()
        QApplication.processEvents()
