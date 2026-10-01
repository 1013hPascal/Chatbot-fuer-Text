"""LLMBackend für Ollama (Chat mit Werkzeugen und Denk-Modus über die HTTP-Schnittstelle)."""
from __future__ import annotations

import json
import threading
from typing import Iterator, Sequence

import httpx

from core.config import Config
from core.engine import OllamaServer, clean_device_name
from core.llm import Cancelled, ChatChunk, DeviceStatus, LLMBackend, LLMError, ToolCall

_NO_SERVER = "Der Modellserver (Ollama) ist nicht erreichbar."


class OllamaBackend(LLMBackend):
    def __init__(self, cfg: Config):
        super().__init__(cfg)
        self.server = OllamaServer(cfg)
        self._http = httpx.Client(base_url=cfg.host, timeout=httpx.Timeout(900, connect=5))
        self._think_unsupported: set[str] = set()     # Modelle ohne Denk-Schalter
        self._caps: dict[str, set[str]] = {}          # Fähigkeiten je Modell (aus /api/show)
        self._stats: list[dict] = []                  # Zeiten der Aufrufe (siehe take_stats)

    # -- Lebenszyklus ------------------------------------------------------
    def start(self) -> None:
        self.server.start()

    def stop(self) -> None:
        self._http.close()
        self.server.stop()

    def installed_models(self) -> list[str]:
        try:
            r = self._http.get("/api/tags")
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(_NO_SERVER) from exc
        return [m["name"] for m in r.json().get("models", [])]

    def capabilities(self) -> set[str]:
        model = self.cfg.chat_model
        if model not in self._caps:
            try:
                r = self._http.post("/api/show", json={"model": model})
                r.raise_for_status()
                found = set(r.json().get("capabilities") or [])
            except (httpx.HTTPError, ValueError):
                return super().capabilities()          # unbekannt: nichts sperren, nichts merken
            self._caps[model] = found or super().capabilities()
        return self._caps[model]

    def take_stats(self) -> list[dict]:
        stats, self._stats = self._stats, []
        return stats

    def unload(self, model: str) -> None:
        try:
            self._http.post("/api/generate", json={"model": model, "keep_alive": 0}, timeout=30)
        except httpx.HTTPError:
            pass

    # -- Chat --------------------------------------------------------------
    def _options(self, max_tokens: int | None) -> dict:
        opts = {"num_ctx": self.cfg.num_ctx, "temperature": self.cfg.temperature}
        if max_tokens:
            opts["num_predict"] = max_tokens
        if not self.cfg.use_gpu:
            opts["num_gpu"] = 0
        return opts

    def chat_stream(self, messages: Sequence[dict], tools: Sequence[dict] | None = None,
                    think: bool = False, max_tokens: int | None = None,
                    cancel: threading.Event | None = None) -> Iterator[ChatChunk]:
        model = self.cfg.chat_model
        caps = self.capabilities()
        payload = {"model": model, "messages": list(messages), "stream": True,
                   "keep_alive": self.cfg.keep_alive, "options": self._options(max_tokens)}
        if tools and "tools" in caps:
            payload["tools"] = list(tools)
        if "thinking" in caps and model not in self._think_unsupported:
            payload["think"] = think
        try:
            yield from self._request(payload, cancel)
        except LLMError as exc:
            if "does not support thinking" in str(exc) and "think" in payload:
                self._think_unsupported.add(model)      # einmal merken und ohne den Schalter neu
                payload.pop("think")
                yield from self._request(payload, cancel)
            else:
                raise

    def _request(self, payload: dict, cancel: threading.Event | None) -> Iterator[ChatChunk]:
        done = threading.Event()
        try:
            with self._http.stream("POST", "/api/chat", json=payload) as resp:
                if resp.status_code != 200:
                    resp.read()
                    raise LLMError(_error_text(resp))
                if cancel is not None:
                    threading.Thread(target=_close_on_cancel, args=(cancel, done, resp),
                                     daemon=True).start()
                try:
                    for line in resp.iter_lines():
                        if cancel is not None and cancel.is_set():
                            raise Cancelled()
                        if not line:
                            continue
                        obj = json.loads(line)
                        if "error" in obj:
                            raise LLMError(str(obj["error"]))
                        message = obj.get("message", {})
                        if message.get("thinking"):
                            yield ChatChunk("thinking", message["thinking"])
                        if message.get("content"):
                            yield ChatChunk("content", message["content"])
                        for call in message.get("tool_calls") or []:
                            fn = call.get("function", {})
                            args = fn.get("arguments") or {}
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except ValueError:
                                    args = {}
                            yield ChatChunk("tool_call", tool=ToolCall(fn.get("name", ""), args))
                        if obj.get("done"):
                            self._stats.append({
                                "load_s": obj.get("load_duration", 0) / 1e9,
                                "prefill_tokens": obj.get("prompt_eval_count", 0),
                                "prefill_s": obj.get("prompt_eval_duration", 0) / 1e9,
                                "gen_tokens": obj.get("eval_count", 0),
                                "gen_s": obj.get("eval_duration", 0) / 1e9})
                            return
                finally:
                    done.set()
        except httpx.ConnectError as exc:
            raise LLMError(_NO_SERVER) from exc
        except httpx.HTTPError as exc:
            if cancel is not None and cancel.is_set():
                raise Cancelled() from exc
            raise LLMError(f"Fehler bei der Verbindung zum Modellserver: {exc}") from exc

    # -- Aufwärmen und Gerät -----------------------------------------------
    def warmup(self) -> None:
        for _ in self.chat_stream([{"role": "user", "content": "Hallo"}], max_tokens=1):
            pass
        self.server.raise_child_priority()

    def device_status(self) -> DeviceStatus:
        if not self.cfg.use_gpu:
            return DeviceStatus("CPU-Modus (in der Konfiguration gewählt)", False)
        try:
            models = self._http.get("/api/ps").json().get("models", [])
        except (httpx.HTTPError, ValueError):
            return DeviceStatus("Gerät unbekannt", False)
        chat = next((m for m in models if m["name"] == self.cfg.chat_model
                     or m["name"].split(":")[0] == self.cfg.chat_model.split(":")[0]), None)
        if chat is None or not chat.get("size"):
            return DeviceStatus("Gerät unbekannt", False)
        share = chat.get("size_vram", 0) / chat["size"]
        if share < 0.05:
            return DeviceStatus("CPU-Modus, die GPU wird nicht genutzt", False)
        name = self._gpu_name()
        if share < 0.95:
            return DeviceStatus(f"GPU teilweise genutzt ({round(share * 100)} Prozent), {name}",
                                True)
        return DeviceStatus(f"GPU: {name} (Vulkan)", True)

    def _gpu_name(self) -> str:
        found = self.server.gpu_from_log()
        if found:
            return found[0]
        from core.hardware import gpu_names
        names = gpu_names()
        return clean_device_name(names[0]) if names else "unbekannte GPU"


def _close_on_cancel(cancel: threading.Event, done: threading.Event, resp: httpx.Response):
    while not done.is_set():
        if cancel.wait(0.1):
            resp.close()
            return


def _error_text(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("error", resp.text))
    except ValueError:
        return resp.text or f"HTTP {resp.status_code}"
