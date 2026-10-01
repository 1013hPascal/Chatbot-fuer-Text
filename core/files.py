"""Angehängte Dateien als Text einlesen (txt, md, csv, json, html, docx, pdf)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.websearch import html_to_text

TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log", ".xml", ".ini", ".yaml", ".yml", ".tex"}
SUPPORTED = TEXT_SUFFIXES | {".html", ".htm", ".docx", ".pdf"}


class FileReadError(Exception):
    pass


@dataclass
class AttachedFile:
    name: str
    text: str
    path: str = ""

    @property
    def words(self) -> int:
        return len(self.text.split())


def _read_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(parts)


def _read_pdf(path: Path) -> str:
    import pymupdf
    with pymupdf.open(str(path)) as doc:
        if doc.needs_pass:
            raise FileReadError("Die PDF-Datei ist passwortgeschützt.")
        return "\n\n".join(page.get_text() for page in doc)


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise FileReadError("Die Datei ist keine lesbare Textdatei.")


def read_file(path: str | Path) -> AttachedFile:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix not in SUPPORTED:
        raise FileReadError(f"Dateityp {suffix or 'ohne Endung'} wird nicht unterstützt. "
                            "Möglich sind: Text, Markdown, CSV, HTML, Word (docx), PDF und Bilder.")
    try:
        if suffix == ".docx":
            text = _read_docx(p)
        elif suffix == ".pdf":
            text = _read_pdf(p)
        elif suffix in (".html", ".htm"):
            text = html_to_text(_read_text(p))[1]
        else:
            text = _read_text(p)
    except FileReadError:
        raise
    except Exception as exc:
        raise FileReadError(f"Die Datei konnte nicht gelesen werden: {exc}") from exc
    text = text.strip()
    if not text:
        raise FileReadError("Die Datei enthält keinen lesbaren Text (bei gescannten PDFs "
                            "ist das normal).")
    return AttachedFile(p.name, text, str(p))
