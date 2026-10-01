"""Hintergrund-Thread für alles Schwere. Die Oberfläche blockiert nie."""
from __future__ import annotations

import logging
import threading
from typing import Callable

from PySide6.QtCore import QThread, Signal

from core.llm import Cancelled, LLMError

log = logging.getLogger(__name__)


class Task(QThread):
    """Führt fn(task) im Hintergrund aus. Ergebnisse kommen über Signale zurück."""
    progress = Signal(float, str)
    event = Signal(object)
    token = Signal(str)
    result = Signal(object)
    error = Signal(str)
    cancelled = Signal()

    def __init__(self, fn: Callable[["Task"], object], parent=None):
        super().__init__(parent)
        self._fn = fn
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            outcome = self._fn(self)
        except Cancelled:
            self.cancelled.emit()
        except LLMError as exc:
            self.error.emit(str(exc))
        except Exception as exc:                       # nie den Thread still sterben lassen
            log.exception("Unerwarteter Fehler im Hintergrund")
            self.error.emit(f"Unerwarteter Fehler: {exc}")
        else:
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.result.emit(outcome)
