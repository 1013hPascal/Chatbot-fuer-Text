"""PDF-Dateien und Bilder für das Modell: Seiten lesen, durchsuchen und ansehen.

Das Einlesen der Seiten (Blöcke sortiert, Silbentrennung aufgelöst) stammt aus dem PDF-Assistenten
(core/ingest.py dort). Kurze PDFs stehen als Text im Prompt (siehe conversation.py). Lange PDFs, Scans
und Bilder liest das Modell über Werkzeuge: Seiten lesen, Stichwort suchen, Seite als Bild ansehen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from core.files import FileReadError, read_file

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff"}
DOCUMENT_SUFFIXES = IMAGE_SUFFIXES | {".pdf"}
SPARSE_CHARS = 300            # Seiten mit weniger Text sind vermutlich Bild oder Grafik
RENDER_DPI = 130              # wie im PDF-Assistenten für die Texterkennung gescannter Seiten
MAX_IMAGE_SIDE = 1600         # längste Kante in Pixeln, die das Modell zu sehen bekommt
MAX_READ_CHARS = 6000         # so viel Text liefert ein Aufruf von dokument_lesen höchstens
OUTLINE_PAGES = 20            # so viele Seitenanfänge stehen höchstens in der Übersicht (jedes Token kostet Zeit)


def _clean_block(text: str) -> str:
    text = re.sub(r"(?<=\w)-\n(?=[a-zäöüß])", "", text)      # Silbentrennung am Zeilenende
    return re.sub(r"\s*\n\s*", " ", text).strip()


def ranges(numbers: list[int]) -> str:
    """[1, 2, 3, 7] -> '1 bis 3, 7'."""
    parts, start, prev = [], None, None
    for n in sorted(set(numbers)):
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            parts.append((start, prev))
            start = prev = n
    if start is not None:
        parts.append((start, prev))
    return ", ".join(str(a) if a == b else f"{a} bis {b}" if b > a + 1 else f"{a}, {b}"
                     for a, b in parts)


def _plain(text: str) -> str:
    """Kleinbuchstaben ohne Umlaute, damit 'Übung' und 'uebung' und 'Ubung' zusammenpassen."""
    text = text.lower().replace("ß", "ss")
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ae", "a"), ("oe", "o"), ("ue", "u")):
        text = text.replace(a, b)
    return text


@dataclass
class Page:
    number: int
    text: str
    images: int = 0

    @property
    def sparse(self) -> bool:
        return len(self.text.strip()) < SPARSE_CHARS


@dataclass
class Hit:
    doc: str
    page: int
    score: float
    excerpt: str


@dataclass
class Document:
    path: str
    name: str
    kind: str                      # "pdf" oder "bild"
    pages: list[Page] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return sum(len(p.text) for p in self.pages)

    @property
    def sparse_pages(self) -> list[int]:
        return [p.number for p in self.pages if p.sparse]

    def inline_text(self) -> str:
        """Der ganze Text mit Seitenmarken, so wie er im Prompt stehen würde."""
        return "\n\n".join(f"[Seite {p.number}]\n{p.text}" for p in self.pages if p.text.strip())

    def render(self, number: int) -> bytes:
        """Seite (ab 1) als Bild für das Modell: PNG bei PDF-Seiten, JPEG bei Fotos."""
        if not 1 <= number <= len(self.pages):
            raise FileReadError(f"{self.name} hat keine Seite {number} (1 bis {len(self.pages)}).")
        try:
            with pymupdf.open(self.path) as doc:
                page = doc[number - 1]
                width = page.rect.width
                if self.kind == "bild":
                    native = pymupdf.Pixmap(self.path)
                    scale = min(1.0, MAX_IMAGE_SIDE / max(native.width, native.height)) * native.width / width
                else:
                    scale = min(RENDER_DPI / 72, MAX_IMAGE_SIDE / max(page.rect.width, page.rect.height))
                pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                return pix.tobytes("jpeg", jpg_quality=90) if self.kind == "bild" else pix.tobytes("png")
        except FileReadError:
            raise
        except Exception as exc:
            raise FileReadError(f"Die Seite konnte nicht als Bild erzeugt werden: {exc}") from exc


def load(path: str | Path) -> Document:
    """Liest ein PDF (Text je Seite) oder ein Bild ein. Wirft FileReadError."""
    p = Path(path)
    suffix = p.suffix.lower()
    try:
        if suffix in IMAGE_SUFFIXES:
            with pymupdf.open(str(p)) as doc:
                if doc.page_count < 1:
                    raise FileReadError("Das Bild ist leer.")
            return Document(str(p), p.name, "bild", [Page(1, "", 1)])
        with pymupdf.open(str(p)) as doc:
            if doc.needs_pass:
                raise FileReadError("Die PDF-Datei ist passwortgeschützt.")
            pages = []
            for number, page in enumerate(doc, start=1):
                blocks = page.get_text("blocks", sort=True)
                paras = [_clean_block(b[4]) for b in blocks if b[6] == 0]
                pages.append(Page(number, "\n\n".join(x for x in paras if x), len(page.get_images())))
            if not pages:
                raise FileReadError("Die PDF-Datei hat keine Seiten.")
            return Document(str(p), p.name, "pdf", pages)
    except FileReadError:
        raise
    except Exception as exc:
        raise FileReadError(f"Die Datei konnte nicht gelesen werden: {exc}") from exc


def check_readable(path: str | Path) -> str:
    """Prüft, ob die Datei als Anhang taugt. Gibt den Dateinamen zurück. Wirft FileReadError."""
    if Path(path).suffix.lower() in DOCUMENT_SUFFIXES:
        return load(path).name
    return read_file(path).name


class Library:
    """Die PDFs und Bilder eines Chats. Das Modell erreicht sie über die Dokument-Werkzeuge."""

    def __init__(self) -> None:
        self.docs: dict[str, Document] = {}
        self.inline: set[str] = set()              # Pfade, deren Text schon im Prompt steht

    def __bool__(self) -> bool:
        return bool(self.docs)

    def add(self, path: str | Path) -> Document:
        doc = load(path)
        self.docs[doc.path] = doc
        return doc

    def has(self, path: str | Path) -> bool:
        return str(Path(path)) in self.docs

    def remove(self, path: str | Path) -> None:
        key = str(Path(path))
        self.docs.pop(key, None)
        self.inline.discard(key)

    def clear(self) -> None:
        self.docs.clear()
        self.inline.clear()

    def find(self, name: str) -> Document:
        """Dokument nach Dateiname (Groß-/Kleinschreibung egal, eindeutiger Anfang genügt)."""
        wanted = Path(str(name).strip()).name.lower()
        exact = [d for d in self.docs.values() if d.name.lower() == wanted]
        starts = [d for d in self.docs.values() if wanted and d.name.lower().startswith(wanted)]
        found = exact or starts
        if len(found) == 1:
            return found[0]
        if not found and len(self.docs) == 1 and not wanted:
            return next(iter(self.docs.values()))
        names = ", ".join(d.name for d in self.docs.values())
        raise FileReadError(f"Dokument nicht gefunden oder nicht eindeutig: {name!r}. "
                            f"Vorhanden: {names}.")

    # -- Übersicht für den Prompt ---------------------------------------------------
    def outline(self) -> str:
        lines = []
        for doc in self.docs.values():
            if doc.kind == "bild":
                lines.append(f"- {doc.name}: Bild (mit seite_ansehen ansehen)")
                continue
            where = "Text steht schon in dieser Nachricht" if doc.path in self.inline \
                else "nur über Werkzeuge lesbar"
            head = f"- {doc.name}: PDF, {len(doc.pages)} Seiten, {where}"
            sparse = doc.sparse_pages
            if sparse:
                head += f". Seiten mit wenig oder ohne Text (Bilder, Grafiken, Scans): {ranges(sparse)}"
            lines.append(head)
            if doc.path not in self.inline and len(doc.pages) > 1:
                step = max(1, -(-len(doc.pages) // OUTLINE_PAGES))       # bei langen PDFs jede n-te Seite
                for page in doc.pages[::step]:
                    first = next((ln.strip() for ln in page.text.splitlines() if ln.strip()), "")
                    if first:
                        lines.append(f"    Seite {page.number}: {first[:45]}")
                if step > 1:
                    lines.append(f"    (nur jede {step}. Seite gezeigt, das PDF hat {len(doc.pages)} Seiten)")
        return "\n".join(lines)

    # -- Lesen und Suchen -----------------------------------------------------------
    def read(self, name: str, first: int = 1, last: int | None = None) -> tuple[Document, str, int, int]:
        """Text der Seiten first bis last. Gibt (Dokument, Text, erste, letzte gelieferte Seite) zurück."""
        doc = self.find(name)
        total = len(doc.pages)
        first = max(1, min(int(first or 1), total))
        last = max(first, min(int(last or first), total))
        out, used, end = [], 0, first - 1
        for page in doc.pages[first - 1:last]:
            body = page.text.strip() or "(kein Text auf dieser Seite, mit seite_ansehen ansehen)"
            if page.text.strip() and page.sparse:
                body += "\n(wenig Text: Bilder oder Grafiken auf der Seite? mit seite_ansehen ansehen)"
            chunk = f"--- Seite {page.number} von {total} ---\n{body}"
            if out and used + len(chunk) > MAX_READ_CHARS:
                break
            out.append(chunk if used + len(chunk) <= MAX_READ_CHARS
                       else chunk[:MAX_READ_CHARS - used].rsplit(" ", 1)[0] + " … [Seite gekürzt]")
            used += len(chunk)
            end = page.number
        text = "\n\n".join(out)
        if end < last:
            text += f"\n\n[Weiter ab Seite {end + 1}. Rufe dokument_lesen erneut auf.]"
        return doc, text, first, end

    def search(self, term: str, name: str = "", max_hits: int = 6) -> list[Hit]:
        """Seiten mit den Suchwörtern, beste zuerst. Ohne Namen in allen Dokumenten."""
        words = [w for w in re.findall(r"\w+", _plain(term)) if len(w) >= 3]
        if not words:
            return []
        stems = [w[:max(4, len(w) - 2)] for w in words]
        docs = [self.find(name)] if name.strip() else list(self.docs.values())
        hits = []
        for doc in docs:
            for page in doc.pages:
                plain = _plain(page.text)
                counts = [plain.count(s) for s in stems]
                present = sum(1 for c in counts if c)
                if not present:
                    continue
                score = present * 10 + min(sum(counts), 10)
                first = min(plain.find(s) for s, c in zip(stems, counts) if c)
                start = max(0, first - 120)
                excerpt = " ".join(page.text[start:first + 220].split())
                hits.append(Hit(doc.name, page.number, score, excerpt))
        hits.sort(key=lambda h: (-h.score, h.doc, h.page))
        return hits[:max_hits]
