"""Werkzeuge, die das Modell aufrufen darf: Internet (Suche, Seiten lesen) und freigegebene Ordner."""
from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse

from core import pdfcheck, websearch
from core.files import FileReadError
from core.folders import FolderAccess, FolderError
from core.llm import ToolCall
from core.pdfs import Library

SEARCH = "internet_suche"
READ_PAGE = "webseite_lesen"
LIST_FILES = "ordner_auflisten"
FIND_IN_FILES = "in_dateien_suchen"
READ_FILE = "datei_lesen"
DOC_READ = "dokument_lesen"
DOC_FIND = "dokument_suchen"
DOC_LOOK = "seite_ansehen"
PDF_CHECK = "pdf_pruefen"

MAX_IMAGES_PER_STEP = 3
SNIPPET_CHARS = 350          # längere Auszüge (Tavily) kosten je 1000 Zeichen etwa 3 Sekunden Einlesezeit

# Diese Werkzeuge brauchen kein Sprachmodell und dürfen gleichzeitig laufen.
PARALLEL_SAFE = {SEARCH, READ_PAGE, LIST_FILES, FIND_IN_FILES, READ_FILE, DOC_READ, DOC_FIND, PDF_CHECK}


def _shorten(text: str, limit: int = SNIPPET_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def _tool(name: str, description: str, **properties) -> dict:
    props = {key: {"type": kind, "description": desc} for key, (kind, desc, _) in properties.items()}
    required = [key for key, (_, _, req) in properties.items() if req]
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": props,
                                                            "required": required}}}


WEB_SPECS = [
    _tool(SEARCH, "Sucht im Internet und liefert Titel, Adresse und einen Auszug zu den besten "
                  "Treffern.", anfrage=("string", "Die Suchanfrage", True)),
    _tool(READ_PAGE, "Liest den Text einer Webseite. Die Adresse stammt aus einer Suche.",
          url=("string", "Vollständige Adresse der Seite", True)),
]
FOLDER_SPECS = [
    _tool(LIST_FILES, "Listet die Dateien in den Ordnern auf, die die Person freigegeben hat."),
    _tool(FIND_IN_FILES, "Sucht einen Begriff in allen Dateien der freigegebenen Ordner und "
                         "liefert Dateinamen mit Auszügen.",
          begriff=("string", "Suchbegriff oder kurze Wortfolge", True)),
    _tool(READ_FILE, "Liest den Text einer Datei aus den freigegebenen Ordnern. Lange Dateien "
                     "werden in Stücken gelesen.",
          datei=("string", "Dateiname oder Pfad, wie ihn ordner_auflisten zeigt", True),
          start=("integer", "Zeichen, ab dem gelesen wird (Standard 0)", False)),
]


DOC_SPECS = [
    _tool(DOC_READ, "Liest den Text von Seiten eines hinzugefügten PDFs. Lange Abschnitte werden in "
                    "Stücken geliefert.",
          datei=("string", "Dateiname des Dokuments", True),
          von=("integer", "Erste Seite (ab 1)", True),
          bis=("integer", "Letzte Seite (Standard: nur die erste)", False)),
    _tool(DOC_FIND, "Sucht Wörter in allen hinzugefügten PDFs und nennt Seiten mit Auszug. Nutze "
                    "wenige, wichtige Wörter, zum Beispiel Namen oder Fachbegriffe.",
          begriff=("string", "Suchwörter", True),
          datei=("string", "Nur in diesem Dokument suchen (optional)", False)),
    _tool(PDF_CHECK, "Prüft ein PDF technisch auf Layoutfehler: Text über dem Seitenrand, "
                     "überlappender Text, winzige Schrift, leere Seiten, fehlende Angaben für "
                     "Screenreader. Liefert einen Bericht mit Seitenzahlen.",
          datei=("string", "Dateiname des PDFs", True)),
]
LOOK_SPEC = _tool(DOC_LOOK, "Zeigt dir eine PDF-Seite oder ein Bild als Bild in der nächsten Nachricht. "
                            "Nutze das für Bilder, Fotos, Diagramme, Scans und wenn es ums Aussehen geht.",
                  datei=("string", "Dateiname des PDFs oder Bildes", True),
                  seite=("integer", "Seite (ab 1). Bei einem Bild 1.", False))


class ToolBox:
    """Führt Werkzeugaufrufe aus und merkt sich die Quellen für die Quellenzeilen."""

    def __init__(self, search_fn: Callable = websearch.search,
                 read_fn: Callable = websearch.read_page, folders: FolderAccess | None = None,
                 docs: Library | None = None):
        self._search = search_fn
        self._read = read_fn
        self.folders = folders or FolderAccess()
        self.docs = docs or Library()
        self.pending_images: list[tuple[str, bytes]] = []    # (Beschriftung, Bild) für die nächste Nachricht
        self.read_urls: list[str] = []
        self.found_urls: list[str] = []
        self.read_files: list[str] = []
        self.found_files: list[str] = []

    def reset(self) -> None:
        self.read_urls.clear()
        self.found_urls.clear()
        self.read_files.clear()
        self.found_files.clear()
        self.pending_images.clear()

    def specs(self, web: bool, folders: bool, docs: bool = False, vision: bool = False) -> list[dict]:
        return ((WEB_SPECS if web else []) + (FOLDER_SPECS if folders else [])
                + (DOC_SPECS if docs else []) + ([LOOK_SPEC] if docs and vision else []))

    def take_notices(self) -> list[str]:
        """Hinweise der Suche (zum Beispiel: Tavily nicht nutzbar, DuckDuckGo übernimmt)."""
        take = getattr(self._search, "take_notices", None)
        return take() if take else []

    def web_sources(self) -> list[str]:
        """Gelesene Seiten, sonst die ersten Suchtreffer."""
        return list(dict.fromkeys(self.read_urls or self.found_urls[:3]))

    def file_sources(self) -> list[str]:
        """Gelesene Dateien, sonst die Dateien mit Suchtreffern (Auszüge zählen als gelesen)."""
        return list(dict.fromkeys(self.read_files or self.found_files[:3]))

    def status(self, call: ToolCall) -> str:
        args = call.arguments
        if call.name == SEARCH:
            return f"Internetrecherche: {args.get('anfrage', '')}"
        if call.name == READ_PAGE:
            host = urlparse(str(args.get("url", ""))).hostname or "Webseite"
            return f"Seite wird gelesen: {host}"
        if call.name == LIST_FILES:
            return "Dateien im Ordner werden aufgelistet"
        if call.name == FIND_IN_FILES:
            return f"Dateien werden durchsucht: {args.get('begriff', '')}"
        if call.name == READ_FILE:
            return f"Datei wird gelesen: {args.get('datei', '')}"
        if call.name == DOC_READ:
            return f"Seiten werden gelesen: {args.get('datei', '')}"
        if call.name == DOC_FIND:
            return f"Dokumente werden durchsucht: {args.get('begriff', '')}"
        if call.name == DOC_LOOK:
            return f"Seite wird angesehen: {args.get('datei', '')}, Seite {args.get('seite') or 1}"
        if call.name == PDF_CHECK:
            return f"PDF wird geprüft: {args.get('datei', '')}"
        return "Werkzeug wird verwendet"

    def run(self, call: ToolCall) -> str:
        """Ergebnis als Text für das Modell. Fehler werden als Text zurückgegeben."""
        a = call.arguments
        try:
            if call.name == SEARCH:
                return self._do_search(str(a.get("anfrage", "")))
            if call.name == READ_PAGE:
                return self._do_read_page(str(a.get("url", "")))
            if call.name == LIST_FILES:
                return self.folders.list_text()
            if call.name == FIND_IN_FILES:
                text, labels = self.folders.search_with_labels(str(a.get("begriff", "")))
                self.found_files += labels
                return text
            if call.name == READ_FILE:
                return self._do_read_file(str(a.get("datei", "")), a.get("start", 0))
            if call.name == DOC_READ:
                return self._do_doc_read(str(a.get("datei", "")), a.get("von"), a.get("bis"))
            if call.name == DOC_FIND:
                return self._do_doc_find(str(a.get("begriff", "")), str(a.get("datei", "") or ""))
            if call.name == DOC_LOOK:
                return self._do_look(str(a.get("datei", "")), a.get("seite"))
            if call.name == PDF_CHECK:
                return self._do_pdf_check(str(a.get("datei", "")))
            return f"Fehler: Unbekanntes Werkzeug {call.name}."
        except (websearch.WebError, FolderError, FileReadError) as exc:
            return f"Fehler: {exc}"

    def _do_search(self, query: str) -> str:
        results = self._search(query)
        if not results:
            return "Keine Treffer."
        self.found_urls += [r["url"] for r in results]
        return "\n\n".join(f"{i}. {r['title']}\n   Adresse: {r['url']}\n   Auszug: {_shorten(r['snippet'])}"
                           for i, r in enumerate(results, start=1))

    def _do_read_page(self, url: str) -> str:
        title, text = self._read(url)
        self.read_urls.append(url)
        return f"Seite: {title}\n\n{text}" if title else text

    @staticmethod
    def _page(value, default: int = 1) -> int:
        try:
            return int(value or default)
        except (TypeError, ValueError):
            return default

    def _do_doc_read(self, name: str, first, last) -> str:
        first = self._page(first)
        doc, text, start, end = self.docs.read(name, first, self._page(last, first))
        self.read_files.append(f"{doc.name}, Seite {start}" if start == end
                               else f"{doc.name}, Seite {start} bis {end}")
        return text

    def _do_doc_find(self, term: str, name: str) -> str:
        hits = self.docs.search(term, name)
        if not hits:
            return "Keine Treffer. Versuche andere oder kürzere Suchwörter, oder lies Seiten direkt."
        self.found_files += [f"{h.doc}, Seite {h.page}" for h in hits]
        return "\n\n".join(f"{i}. {h.doc}, Seite {h.page}\n   Auszug: {h.excerpt}"
                           for i, h in enumerate(hits, start=1))

    def _do_look(self, name: str, page) -> str:
        """Das Bild geht nicht als Text zurück, sondern als Bild in die nächste Nachricht. So sieht
        das Hauptmodell es selbst: kein zweiter Modellaufruf, kein langer Beschreibungstext."""
        doc = self.docs.find(name)
        number = self._page(page)
        label = f"{doc.name}, Seite {number}" if doc.kind == "pdf" else doc.name
        if any(existing == label for existing, _ in self.pending_images):
            return f"{label} liegt schon als Bild in der nächsten Nachricht."
        if len(self.pending_images) >= MAX_IMAGES_PER_STEP:
            return f"Fehler: Höchstens {MAX_IMAGES_PER_STEP} Seiten oder Bilder auf einmal. Frage später nach weiteren."
        self.pending_images.append((label, doc.render(number)))
        self.read_files.append(label)
        return f"{label} liegt als Bild in der nächsten Nachricht. Sieh es dir dort an."

    def take_images(self) -> list[tuple[str, bytes]]:
        images, self.pending_images = self.pending_images, []
        return images

    def _do_pdf_check(self, name: str) -> str:
        doc = self.docs.find(name)
        if doc.kind != "pdf":
            return "Fehler: Das ist ein Bild, kein PDF."
        pages, findings = pdfcheck.check_pdf(doc.path)
        self.read_files.append(doc.name)
        return pdfcheck.format_report(doc.name, pages, findings)

    def _do_read_file(self, name: str, start) -> str:
        try:
            start = int(start or 0)
        except (TypeError, ValueError):
            start = 0
        label, text = self.folders.read(name, start)
        self.read_files.append(label)
        return f"Datei: {label}\n\n{text}"
