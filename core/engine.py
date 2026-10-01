"""Serverprozess: startet und beendet Ollama als Unterprozess.

Läuft schon ein Ollama-Server, wird er mitbenutzt und beim Beenden nicht
angetastet. Einstellungen wie Flash Attention gelten dann nur, wenn wir den
Server selbst starten.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import psutil

from core.config import Config, app_dir
from core.llm import LLMError

_GPU_LINE = re.compile(r'inference compute.*?description="([^"]+)".*?type=(\w+)')


def find_ollama_exe() -> Path | None:
    found = shutil.which("ollama")
    if found:
        return Path(found)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidate = Path(local) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.exists():
            return candidate
    return None


def clean_device_name(name: str) -> str:
    return re.sub(r"\((R|TM)\)", "", name).replace("  ", " ").strip()


class OllamaServer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._proc: subprocess.Popen | None = None
        self.log_path = app_dir() / "logs" / "ollama.log"

    # -- Zustand -----------------------------------------------------------
    def is_running(self) -> bool:
        try:
            return httpx.get(self.cfg.host + "/api/version", timeout=2).status_code == 200
        except httpx.HTTPError:
            return False

    @property
    def owned(self) -> bool:
        return self._proc is not None

    # -- Start und Stop ----------------------------------------------------
    def _environment(self) -> dict[str, str]:
        env = dict(os.environ)
        env["OLLAMA_HOST"] = self.cfg.host.removeprefix("http://")
        env["OLLAMA_NUM_PARALLEL"] = "1"
        env["OLLAMA_MAX_LOADED_MODELS"] = "2"          # Chat- und Embedding-Modell
        env["OLLAMA_KEEP_ALIVE"] = self.cfg.keep_alive
        env["OLLAMA_FLASH_ATTENTION"] = "1" if self.cfg.flash_attention else "0"
        if self.cfg.kv_cache_type:
            env["OLLAMA_KV_CACHE_TYPE"] = self.cfg.kv_cache_type
        env["OLLAMA_NOHISTORY"] = "1"
        if self.cfg.use_gpu:
            env["OLLAMA_VULKAN"] = "1"                 # Weg zur Intel- und AMD-GPU
            env["OLLAMA_IGPU_ENABLE"] = "1"            # integrierte GPU zulassen
        else:
            env["OLLAMA_VULKAN"] = "0"
            env["GGML_VK_VISIBLE_DEVICES"] = "-1"
        return env

    def start(self, timeout: float = 60) -> None:
        if self.is_running():
            return
        exe = find_ollama_exe()
        if exe is None:
            raise LLMError("Ollama ist nicht installiert. Bitte von ollama.com installieren "
                           "oder scripts/setup_engine.py ausführen.")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(self.log_path, "w", encoding="utf-8")
        self._proc = subprocess.Popen(
            [str(exe), "serve"], env=self._environment(), stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.ABOVE_NORMAL_PRIORITY_CLASS,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise LLMError("Ollama wurde sofort wieder beendet. Siehe " + str(self.log_path))
            if self.is_running():
                return
            time.sleep(0.3)
        raise LLMError("Ollama antwortet nicht.")

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            parent = psutil.Process(self._proc.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
        except psutil.Error:
            pass
        self._proc = None

    def raise_child_priority(self) -> None:
        """Die Modell-Prozesse (Kinder des Servers) leicht bevorzugen."""
        if self._proc is None:
            return
        try:
            for child in psutil.Process(self._proc.pid).children(recursive=True):
                child.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
        except psutil.Error:
            pass

    # -- Geräteinfo aus dem Protokoll ---------------------------------------
    def gpu_from_log(self) -> tuple[str, str] | None:
        """(Name, Typ) des Geräts, das der Server beim Start erkannt hat."""
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        matches = _GPU_LINE.findall(text)
        if not matches:
            return None
        name, kind = matches[-1]
        return clean_device_name(name), kind
