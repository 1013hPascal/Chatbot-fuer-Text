"""Schnittstelle zum Sprachmodell.

Der Rest der App spricht nur mit LLMBackend. Wer ein anderes Modell oder einen
anderen Server verwenden will, ändert den Namen in core/config.py (gleiches Backend)
oder schreibt eine neue Backend-Klasse und trägt sie in BACKENDS ein.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Sequence

from core.config import Config


class LLMError(Exception):
    """Der Modellserver ist nicht erreichbar oder meldet einen Fehler."""


class Cancelled(Exception):
    """Der Vorgang wurde von der Person abgebrochen."""


@dataclass
class DeviceStatus:
    text: str          # z. B. "GPU: Intel Arc 140V (Vulkan)" oder "CPU-Modus"
    on_gpu: bool


@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class ChatChunk:
    """Ein Stück der Modellausgabe: Antworttext, Denktext oder ein Werkzeugaufruf."""
    kind: str                                  # "content" | "thinking" | "tool_call"
    text: str = ""
    tool: ToolCall | None = None


class LLMBackend(ABC):
    def __init__(self, cfg: Config):
        self.cfg = cfg

    @abstractmethod
    def start(self) -> None:
        """Server bereitstellen (starten, falls nötig). Wirft LLMError."""

    def stop(self) -> None:
        """Nur selbst gestartete Server beenden."""

    @abstractmethod
    def installed_models(self) -> list[str]: ...

    def missing_models(self) -> list[str]:
        have: set[str] = set()
        for name in self.installed_models():
            have.add(name)
            have.add(name.removesuffix(":latest"))
        return [m for m in [self.cfg.chat_model] if m.removesuffix(":latest") not in have]

    def capabilities(self) -> set[str]:
        """Was das gewählte Modell kann: "tools" (Internet, Ordner, Dokumente), "thinking"
        (Nachdenken) und "vision" (Bilder ansehen). Unbekannt gilt als "kann alles", damit nichts
        grundlos gesperrt wird."""
        return {"tools", "thinking", "vision"}

    def unload(self, model: str) -> None:
        """Ein nicht mehr gebrauchtes Modell aus dem Arbeitsspeicher nehmen."""

    def take_stats(self) -> list[dict]:
        """Zeiten der Modellaufrufe seit dem letzten Abruf (Sekunden und Tokenzahlen), sonst leer.
        Schlüssel: load_s, prefill_tokens, prefill_s, gen_tokens, gen_s."""
        return []

    @abstractmethod
    def chat_stream(self, messages: Sequence[dict], tools: Sequence[dict] | None = None,
                    think: bool = False, max_tokens: int | None = None,
                    cancel: threading.Event | None = None) -> Iterator[ChatChunk]:
        """Liefert die Ausgabe stückweise. Wirft Cancelled bei Abbruch, LLMError bei Fehlern."""

    @abstractmethod
    def warmup(self) -> None:
        """Modell laden und mit Mini-Anfrage aufwärmen."""

    @abstractmethod
    def device_status(self) -> DeviceStatus: ...


def _ollama(cfg: Config) -> LLMBackend:
    from core.ollama_backend import OllamaBackend
    return OllamaBackend(cfg)


# Name -> Fabrik. Hier neue Backends eintragen.
BACKENDS = {"ollama": _ollama}


def create_backend(cfg: Config) -> LLMBackend:
    try:
        return BACKENDS[cfg.backend](cfg)
    except KeyError:
        raise LLMError(f"Unbekanntes Backend: {cfg.backend}") from None
