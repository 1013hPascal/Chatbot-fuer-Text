"""Ansagen für Screenreader.

announce(text, dringend=False) sendet ein Accessibility-Ereignis, das NVDA und die
Windows-Sprachausgabe vorlesen, ohne dass der Fokus wechselt. Ab Qt 6.8 gibt es dafür
QAccessibleAnnouncementEvent. Ältere Versionen: Fallback über ein Namensänderungs-Ereignis.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject
from PySide6.QtGui import QAccessible, QAccessibleEvent

try:
    from PySide6.QtGui import QAccessibleAnnouncementEvent
except ImportError:                                    # Qt vor 6.8
    QAccessibleAnnouncementEvent = None

log = logging.getLogger(__name__)


class Announcer:
    def __init__(self) -> None:
        self.target: QObject | None = None       # Objekt, an dem das Ereignis hängt
        self.last_text = ""
        self.history: list[tuple[str, bool]] = []

    def announce(self, text: str, dringend: bool = False) -> None:
        self.last_text = text
        self.history.append((text, dringend))
        log.info("Ansage%s: %s", " (dringend)" if dringend else "", text)
        target = self.target
        if target is None:
            return
        if QAccessibleAnnouncementEvent is not None:
            event = QAccessibleAnnouncementEvent(target, text)
            event.setPoliteness(QAccessible.AnnouncementPoliteness.Assertive if dringend
                                else QAccessible.AnnouncementPoliteness.Polite)
        else:
            event = QAccessibleEvent(target, QAccessible.Event.NameChanged)
        QAccessible.updateAccessibility(event)


announcer = Announcer()


def announce(text: str, dringend: bool = False) -> None:
    announcer.announce(text, dringend)
