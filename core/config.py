"""Konfiguration der App.

DIE MODELLWAHL STEHT AN DIESER EINEN STELLE (Abschnitt "Modelle").
Ändern Sie dort den Namen, oder tragen Sie ihn in %APPDATA%\\TextChat\\config.json ein.
Der restliche Code kennt keine Modellnamen.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

APP_NAME = "TextChat"

# --------------------------------------------------------------------------
# Modelle (einzige Stelle im Code)
# --------------------------------------------------------------------------
DEFAULT_BACKEND = "ollama"              # registriert in core/llm.py
DEFAULT_CHAT_MODEL = "gemma4:12b"       # muss Werkzeuge und (für "Nachdenken") Denken können
# Modelle, die im Menü Einstellungen, Modell zur Wahl stehen: (Ollama-Name, Menütext).
# Ohne Werkzeuge (qwen2.5vl) gibt es keine Internetrecherche und keinen Ordnerzugriff,
# ohne Denken keinen Schalter "Nachdenken". Die App sagt das beim Wechseln an.
AVAILABLE_MODELS = [
    ("gemma4:12b", "Gemma 4 (12b)"),
    ("qwen2.5vl:7b", "Qwen 2.5 VL (7b)"),
]
# --------------------------------------------------------------------------


def app_dir() -> Path:
    """Datenordner. Mit TEXTCHAT_HOME überschreibbar (Tests)."""
    override = os.environ.get("TEXTCHAT_HOME")
    if override:
        base = Path(override)
    else:
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


@dataclass
class Config:
    # Modell
    backend: str = DEFAULT_BACKEND
    chat_model: str = DEFAULT_CHAT_MODEL
    host: str = "http://127.0.0.1:11434"

    # Modellparameter
    num_ctx: int = 16384
    temperature: float = 0.7
    tokens_normal: int = 1500          # maximale Antwortlänge in Tokens
    tokens_long: int = 4000            # bei "Lange Antworten"
    tokens_thinking_extra: int = 3000  # zusätzlich bei "Nachdenken"
    keep_alive: str = "30m"
    flash_attention: bool = True
    kv_cache_type: str = ""            # "", "q8_0" oder "q4_0"
    use_gpu: bool = True               # False erzwingt CPU-Betrieb
    max_tool_steps: int = 8            # höchstens so viele Werkzeug-Schritte je Frage

    # Die drei Schalter der Oberfläche
    long_answers: bool = False
    thinking: bool = False
    web_search: bool = True

    # Internetsuche: mit Schlüssel Tavily, sonst DuckDuckGo (Umgebungsvariable TAVILY_API_KEY geht auch)
    tavily_key: str = ""
    tavily_depth: str = "basic"        # "basic" kostet 1 Credit je Suche, "advanced" 2 (genauer)
    web_prefetch: bool = True          # bei eindeutigen Internetfragen schon vor dem Modell suchen (schneller)

    # Anhänge
    max_attachment_chars: int = 30000  # Gesamtgröße aller angehängten Texte

    # Oberfläche
    font_size: int = 12
    beep_on_answer: bool = True

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or app_dir() / "config.json"
        cfg = cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cfg
        known = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key in known and isinstance(value, type(getattr(cfg, key))):
                setattr(cfg, key, value)
        return cfg

    def save(self, path: Path | None = None) -> None:
        path = path or app_dir() / "config.json"
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False),
                        encoding="utf-8")
