"""Unterhaltung mit dem Modell: Gedächtnis, Anhänge, Ordner, Dokumente, Werkzeug-Schleife, Auswertung."""
from __future__ import annotations

import base64
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from core import pdfs, prompts, router
from core.config import Config
from core.files import AttachedFile, read_file
from core.llm import Cancelled, LLMBackend
from core.llm import ToolCall
from core.tools import PARALLEL_SAFE, SEARCH, ToolBox
from core.websearch import Searcher

log = logging.getLogger(__name__)

CHARS_PER_TOKEN = 3.2
MAX_TEXT_CHARS = 20000
STATUS_THINKING = "Nachdenken"
STATUS_ANSWERING = "Antwort wird erstellt"
SHORTENED = "[Ergebnis gekürzt, um Platz zu sparen]"
MAX_PARALLEL_TOOLS = 4

StatusFn = Callable[[str], None]


def _pages(n: int) -> str:
    return "1 Seite" if n == 1 else f"{n} Seiten"


@dataclass
class AddedFile:
    """Ergebnis von ChatSession.add_file: was mit der Datei geschehen ist."""
    name: str
    mode: str                              # text, pdf_inline, pdf_tools, pdf_scan oder image
    words: int = 0
    pages: int = 0
    truncated: bool = False
    sparse: list[int] = field(default_factory=list)   # PDF-Seiten mit wenig Text

    def message(self) -> str:
        if self.mode == "image":
            return f"{self.name} hinzugefügt. Das Modell sieht es sich an, wenn Sie danach fragen."
        if self.mode == "pdf_scan":
            return (f"{self.name} hinzugefügt, {_pages(self.pages)} ohne Text (Scan). Das Modell "
                    "sieht sich Seiten bei Bedarf als Bild an.")
        if self.mode in ("pdf_inline", "pdf_tools"):
            text = f"{self.name} hinzugefügt, {_pages(self.pages)}"
            text += f", {self.words} Wörter." if self.mode == "pdf_inline" else (
                ". Zu lang für eine einzelne Anfrage: Das Modell sucht und liest gezielt Seiten.")
            if self.sparse:
                text += (f" Seiten mit wenig Text (Bilder oder Grafiken): {pdfs.ranges(self.sparse)}. "
                         "Das Modell kann sie ansehen.")
            return text
        text = f"{self.name} hinzugefügt, {self.words} Wörter."
        if self.truncated:
            text += " Die Datei war zu lang und wurde gekürzt."
        return text


@dataclass
class TurnResult:
    answer: str                            # gesprochener Teil, inklusive Quellenzeilen
    doc_title: str = ""
    doc_text: str | None = None            # gesetzt, wenn das Modell einen Text geschrieben hat
    word_filename: str | None = None       # gesetzt, wenn ein Word-Download angeboten wird
    web_sources: list[str] = field(default_factory=list)
    file_sources: list[str] = field(default_factory=list)
    timing: dict = field(default_factory=dict)   # wohin die Zeit ging, siehe format_timing


def format_timing(t: dict) -> str:
    """Eine Zeile: Gesamtzeit, Modellaufrufe (Einlesen, Schreiben, Laden) und Werkzeuge."""
    calls = t.get("calls", [])
    parts = [f"gesamt {t.get('total_s', 0):.1f} s"]
    if calls:
        parts.append("Modell " + "; ".join(
            f"{c['prefill_tokens']} Token einlesen {c['prefill_s']:.1f} s, "
            f"{c['gen_tokens']} Token schreiben {c['gen_s']:.1f} s"
            + (f", laden {c['load_s']:.1f} s" if c["load_s"] > 0.5 else "") for c in calls))
    if t.get("tools"):
        parts.append("Werkzeuge " + ", ".join(f"{name} {s:.1f} s" for name, s in t["tools"]))
    return " | ".join(parts)


class ChatSession:
    def __init__(self, cfg: Config, backend: LLMBackend, toolbox: ToolBox | None = None):
        self.cfg = cfg
        self.backend = backend
        self.toolbox = toolbox or ToolBox(search_fn=Searcher(cfg))
        self.folders = self.toolbox.folders
        self.docs = self.toolbox.docs
        self.turns: list[tuple[str, str]] = []          # (Frage, Antwort) dieser Unterhaltung
        self.attachments: list[AttachedFile] = []
        self._timing: dict = {}

    # -- Zustand -------------------------------------------------------------
    def reset(self) -> None:
        """Neuer Chat: Gedächtnis, Anhänge, Dokumente und Ordner leeren."""
        self.turns.clear()
        self.attachments.clear()
        self.docs.clear()
        self.folders.clear()

    def load(self, turns: list[tuple[str, str]]) -> None:
        """Gedächtnis eines gespeicherten Chats wiederherstellen (älteste Runde zuerst)."""
        self.turns = list(turns)

    def attachment_chars(self) -> int:
        return sum(len(a.text) for a in self.attachments)

    def add_attachment(self, attached: AttachedFile) -> bool:
        """Fügt hinzu und kürzt bei Bedarf auf das Gesamtlimit. True, wenn gekürzt wurde."""
        room = max(0, self.cfg.max_attachment_chars - self.attachment_chars())
        truncated = len(attached.text) > room
        if truncated:
            attached.text = attached.text[:room].rsplit(" ", 1)[0] + " … [gekürzt]" if room else ""
        if not attached.text:
            return True
        self.attachments.append(attached)
        return truncated

    def remove_attachment(self, index: int) -> None:
        if 0 <= index < len(self.attachments):
            del self.attachments[index]

    # -- Dateien: Text, PDF und Bild -----------------------------------------------------------
    def has_file(self, path: str) -> bool:
        key = str(Path(path))
        return self.docs.has(key) or any(a.path == key for a in self.attachments)

    def add_file(self, path: str) -> AddedFile:
        """Fügt eine Datei hinzu. Wirft FileReadError.

        Textdateien und kurze PDFs stehen ganz im Prompt. Lange PDFs, Scans und Bilder liest das
        Modell mit Werkzeugen (Seiten, Suche, Ansehen)."""
        if Path(path).suffix.lower() not in pdfs.DOCUMENT_SUFFIXES:
            attached = read_file(path)
            truncated = self.add_attachment(attached)
            return AddedFile(attached.name, "text", attached.words, truncated=truncated)
        doc = self.docs.add(path)
        if doc.kind == "bild":
            return AddedFile(doc.name, "image", pages=1)
        if doc.chars == 0:
            return AddedFile(doc.name, "pdf_scan", pages=len(doc.pages))
        text = doc.inline_text()
        room = self.cfg.max_attachment_chars - self.attachment_chars()
        mode = "pdf_tools"
        if len(text) <= room:
            self.attachments.append(AttachedFile(doc.name, text, doc.path))
            self.docs.inline.add(doc.path)
            mode = "pdf_inline"
        return AddedFile(doc.name, mode, len(text.split()), len(doc.pages), sparse=doc.sparse_pages)

    def remove_file(self, path: str) -> None:
        key = str(Path(path))
        self.docs.remove(key)
        self.attachments[:] = [a for a in self.attachments if a.path != key]

    # -- Was das gewählte Modell kann ------------------------------------------------------------
    # Ohne Werkzeuge gibt es weder Internet noch Ordner noch gezieltes Lesen von PDFs, ohne Denken
    # kein Nachdenken. Das Modell bekommt dann auch keine Anweisung dazu.
    def _thinking(self) -> bool:
        return self.cfg.thinking and "thinking" in self.backend.capabilities()

    def _tools(self) -> bool:
        return "tools" in self.backend.capabilities()

    def _web(self) -> bool:
        return self.cfg.web_search and self._tools()

    def _folder_names(self) -> list[str]:
        return [r.name for r in self.folders.roots] if self._tools() else []

    def _docs_on(self) -> bool:
        return bool(self.docs) and self._tools()

    def _vision(self) -> bool:
        return "vision" in self.backend.capabilities()

    def limits_note(self) -> str:
        """Hinweis, wenn eingeschaltete Funktionen mit diesem Modell nicht gehen. Sonst leer."""
        caps = self.backend.capabilities()
        missing = []
        if self.cfg.web_search and "tools" not in caps:
            missing.append("nicht im Internet suchen")
        if self.folders.roots and "tools" not in caps:
            missing.append("keine Ordner lesen")
        if any(d.path not in self.docs.inline for d in self.docs.docs.values()) and "tools" not in caps:
            missing.append("lange PDFs, Scans und Bilder nicht gezielt ansehen")
        if self.cfg.thinking and "thinking" not in caps:
            missing.append("nicht nachdenken")
        return "Dieses Modell kann " + " und ".join(missing) + "." if missing else ""

    # -- Nachrichten aufbauen --------------------------------------------------
    def _max_tokens(self) -> int:
        tokens = self.cfg.tokens_long if self.cfg.long_answers else self.cfg.tokens_normal
        return tokens + (self.cfg.tokens_thinking_extra if self._thinking() else 0)

    def _budget_chars(self) -> int:
        return int((self.cfg.num_ctx - self._max_tokens() - 500) * CHARS_PER_TOKEN)

    def _attachment_texts(self) -> list[tuple[str, str]]:
        items = [(a.name, a.text) for a in self.attachments]
        if not self._tools():
            # Ohne Werkzeuge bekommt das Modell wenigstens den Anfang langer PDFs.
            room = max(0, self.cfg.max_attachment_chars - self.attachment_chars())
            for doc in self.docs.docs.values():
                if doc.kind == "pdf" and doc.chars and doc.path not in self.docs.inline and room > 200:
                    text = doc.inline_text()[:room].rsplit(" ", 1)[0] + " … [gekürzt]"
                    items.append((doc.name, text))
                    room -= len(text)
        return items

    def build_messages(self, question: str, text: str) -> list[dict]:
        system = prompts.build_system(self.cfg.long_answers, self._web(), self._attachment_texts(),
                                      self._folder_names(),
                                      docs_outline=self.docs.outline() if self._docs_on() else "",
                                      vision=self._vision())
        user = prompts.build_user_message(question, text[:MAX_TEXT_CHARS])
        # Platz für frühere Runden: Kontext minus Antwortlänge minus feste Teile.
        budget = self._budget_chars() - 1000 - len(system) - len(user)
        history: list[dict] = []
        for q, a in reversed(self.turns):
            cost = len(q) + len(a)
            if cost > budget:
                break
            budget -= cost
            history[:0] = [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
        return [{"role": "system", "content": system}, *history,
                {"role": "user", "content": user}]

    def _fit(self, messages: list[dict]) -> None:
        """Werkzeugergebnisse, die zusammen den Kontext sprengen würden, von alt nach neu kürzen."""
        def total() -> int:
            return sum(len(str(m.get("content", ""))) for m in messages)
        tools = [i for i, m in enumerate(messages) if m["role"] == "tool"]
        for i in tools[:-1]:
            if total() <= self._budget_chars():
                return
            messages[i]["content"] = SHORTENED

    # -- Eine Runde ------------------------------------------------------------
    def ask(self, question: str, text: str = "", cancel: threading.Event | None = None,
            on_status: StatusFn | None = None) -> TurnResult:
        """text: aktueller Text im Antwortfeld (leer, wenn dort kein Text zum Weiterarbeiten steht)."""
        status = on_status or (lambda s: None)
        started = time.perf_counter()
        self._timing = {"calls": [], "tools": []}
        self.backend.take_stats()                       # alte Zeiten verwerfen
        messages = self.build_messages(question, text)
        self.toolbox.reset()
        web, has_folders = self._web(), bool(self._folder_names())
        docs, vision = self._docs_on(), self._vision()
        note = self.limits_note()
        if note:
            status(note)
        if web and self.cfg.web_prefetch and router.wants_web_search(
                question, bool(text.strip()), bool(self.attachments or self.docs or has_folders)):
            self._prefetch_search(messages, question, cancel, status)
        raw = ""
        for step in range(self.cfg.max_tool_steps + 1):
            tools = (self.toolbox.specs(web, has_folders, docs, vision) or None) \
                if step < self.cfg.max_tool_steps else None
            self._fit(messages)
            content, calls = self._one_call(messages, tools, cancel, status)
            self._timing["calls"] += self.backend.take_stats()
            if not calls:
                raw = content
                break
            messages.append({"role": "assistant", "content": content, "tool_calls": [
                {"function": {"name": c.name, "arguments": c.arguments}} for c in calls]})
            for call, result in zip(calls, self._run_calls(calls, cancel, status)):
                messages.append({"role": "tool", "tool_name": call.name, "content": result})
            images = self.toolbox.take_images()
            if images:          # Seiten und Bilder sieht das Hauptmodell selbst, in derselben Unterhaltung
                messages.append({"role": "user", "content": prompts.images_message(question, [l for l, _ in images]),
                                 "images": [base64.b64encode(data).decode("ascii") for _, data in images]})
        self._timing["total_s"] = time.perf_counter() - started
        log.info("Zeiten: %s", format_timing(self._timing))
        return self._result(question, raw, text)

    def _prefetch_search(self, messages: list[dict], question: str, cancel, status: StatusFn) -> None:
        """Sucht schon vor dem ersten Modellaufruf und legt das Ergebnis so ab, als hätte das Modell
        die Suche selbst aufgerufen. Das spart die Runde, in der es sonst nur beschließt zu suchen."""
        call = ToolCall(SEARCH, {"anfrage": router.search_query(question)})
        result = self._run_calls([call], cancel, status)[0]
        messages.append({"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": call.name, "arguments": call.arguments}}]})
        messages.append({"role": "tool", "tool_name": call.name, "content": result})

    def _run_calls(self, calls, cancel, status: StatusFn) -> list[str]:
        """Führt die Werkzeugaufrufe eines Schritts aus. Mehrere unabhängige laufen gleichzeitig."""
        def one(call) -> str:
            began = time.perf_counter()
            result = self.toolbox.run(call)
            self._timing["tools"].append((call.name, time.perf_counter() - began))
            return result

        if len(calls) > 1 and all(c.name in PARALLEL_SAFE for c in calls):
            for call in calls:
                status(self.toolbox.status(call))
            with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_TOOLS, len(calls))) as pool:
                results = list(pool.map(one, calls))
        else:
            results = []
            for call in calls:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                status(self.toolbox.status(call))
                results.append(one(call))
        for notice in self.toolbox.take_notices():
            status(notice)
        return results

    def _result(self, question: str, raw: str, previous_text: str) -> TurnResult:
        reply = prompts.parse_reply(raw)
        answer = reply.answer
        if not answer:      # Das Modell hat nur den Text oder gar nichts geschrieben
            if reply.doc_text is not None:
                answer = prompts.DOC_CHANGED if previous_text.strip() else prompts.DOC_CREATED
            elif reply.word_filename is not None:
                answer = prompts.WORD_READY
            else:
                answer = prompts.NO_ANSWER
        web_sources = self.toolbox.web_sources()
        file_sources = self.toolbox.file_sources()
        if answer != prompts.NO_ANSWER:
            if web_sources:
                answer += "\n\nQuellen aus dem Internet: " + "; ".join(web_sources)
            if file_sources:
                answer += "\n\nGelesene Dateien: " + "; ".join(file_sources)
        self.turns.append((question, answer))
        return TurnResult(answer, reply.doc_title, reply.doc_text, reply.word_filename,
                          web_sources, file_sources, dict(self._timing))

    def _one_call(self, messages, tools, cancel, status: StatusFn):
        """Ein Modellaufruf. Gibt (Antworttext, Werkzeugaufrufe) zurück."""
        content = ""
        calls = []
        announced = ""
        for chunk in self.backend.chat_stream(messages, tools, self._thinking(),
                                              self._max_tokens(), cancel):
            if chunk.kind == "thinking" and announced != STATUS_THINKING:
                announced = STATUS_THINKING
                status(STATUS_THINKING)
            elif chunk.kind == "content":
                content += chunk.text
                if announced != STATUS_ANSWERING and not calls:
                    announced = STATUS_ANSWERING
                    status(STATUS_ANSWERING)
            elif chunk.kind == "tool_call" and chunk.tool is not None:
                calls.append(chunk.tool)
        return content, calls
