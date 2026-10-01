"""Richtet die Modell-Engine ein: prüft Ollama, startet den Server, lädt das fehlende Modell.

Aufruf:  python scripts/setup_engine.py
Der Modellname kommt aus core/config.py (oder %APPDATA%\\TextChat\\config.json).
Ollama prüft die Prüfsummen der Modelldatei selbst. Nach dem Herunterladen läuft alles lokal.
"""
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import Config  # noqa: E402
from core.engine import find_ollama_exe  # noqa: E402
from core.llm import LLMError, create_backend  # noqa: E402


def pull(host: str, model: str) -> None:
    print(f"Lade {model} ...")
    last = -1
    with httpx.stream("POST", host + "/api/pull", json={"model": model, "stream": True},
                      timeout=None) as resp:
        for line in resp.iter_lines():
            if not line:
                continue
            info = json.loads(line)
            if "error" in info:
                raise SystemExit(f"Fehler beim Laden von {model}: {info['error']}")
            if info.get("total"):
                percent = int(100 * info.get("completed", 0) / info["total"])
                if percent // 10 != last // 10:
                    print(f"  {info.get('status', '')}: {percent} Prozent")
                last = percent
    print(f"{model} ist installiert.")


def main() -> None:
    cfg = Config.load()
    if find_ollama_exe() is None:
        raise SystemExit("Ollama fehlt. Bitte von https://ollama.com/download installieren "
                         "und dieses Skript erneut starten.")
    backend = create_backend(cfg)
    try:
        backend.start()
        for model in backend.missing_models():
            pull(cfg.host, model)
        print("Aufwärmen ...")
        backend.warmup()
        print("Gerät:", backend.device_status().text)
        print("Fertig. Modell:", cfg.chat_model)
    except LLMError as exc:
        raise SystemExit(f"Fehler: {exc}")
    finally:
        backend.stop()


if __name__ == "__main__":
    main()
