"""Gemeinsame Test-Hilfen: Modell-Attrappe, temporäre Datenordner."""
import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config  # noqa: E402
from core.store import Store  # noqa: E402
from core.llm import Cancelled, ChatChunk, DeviceStatus, LLMBackend, ToolCall  # noqa: E402


def content(text: str) -> list[ChatChunk]:
    return [ChatChunk("content", text)]


def tool_call(name: str, **arguments) -> list[ChatChunk]:
    return [ChatChunk("tool_call", tool=ToolCall(name, arguments))]


class FakeBackend(LLMBackend):
    """Ersetzt das Sprachmodell. Gibt der Reihe nach die vorbereiteten Ausgaben zurück."""

    def __init__(self, cfg: Config, script=None, delay: float = 0.0):
        super().__init__(cfg)
        self.script = list(script or [])
        self.delay = delay
        self.calls: list[dict] = []        # was das Modell bekommen hat
        self.gpu = True
        self.caps = {"tools", "thinking", "vision"}   # was das Modell kann (Tests ändern das)
        self.installed: list[str] | None = None
        self.unloaded: list[str] = []
        self.warmed: list[str] = []        # welche Modelle aufgewärmt wurden

    def start(self): pass
    def stop(self): pass
    def warmup(self): self.warmed.append(self.cfg.chat_model)
    def capabilities(self): return set(self.caps)
    def unload(self, model): self.unloaded.append(model)

    def installed_models(self):
        return [self.cfg.chat_model] if self.installed is None else self.installed

    def device_status(self):
        return DeviceStatus("GPU: Testgerät (Vulkan)" if self.gpu else "CPU-Modus", self.gpu)

    def chat_stream(self, messages, tools=None, think=False, max_tokens=None, cancel=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools,
                           "think": think, "max_tokens": max_tokens})
        chunks = self.script.pop(0) if self.script else content("Standardantwort.")
        end = time.monotonic() + self.delay
        while time.monotonic() < end:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            time.sleep(0.01)
        yield from chunks


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("TEXTCHAT_HOME", str(tmp_path / "home"))
    return Config()


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "chats.db")
    yield s
    try:
        s.close()
    except Exception:
        pass
