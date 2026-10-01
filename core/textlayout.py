"""Antworttext in kurze Zeilen bringen, damit man ihn mit Pfeiltasten und auf der Braillezeile
zeilenweise lesen kann.

Ein Absatz aus mehreren Sätzen ist für einen Screenreader eine einzige lange Zeile, und jeder
Pfeiltastendruck zeigt wieder den Anfang. Deshalb: ein Satz je Zeile, lange Sätze an Wortgrenzen
umbrochen, Absätze (Leerzeile) und Listenpunkte bleiben, Quellen stehen je eine Zeile.
Der Text eines Dokuments (Anschreiben) wird nicht angefasst, er ist das Ergebnis der Person.
"""
from __future__ import annotations

import re
import textwrap

WIDTH = 70

# Wörter, nach denen ein Punkt kein Satzende ist (klein geschrieben, ohne Punkt).
ABBREVIATIONS = {
    "ca", "bzw", "usw", "etc", "vgl", "evtl", "ggf", "ggfs", "inkl", "zzgl", "nr", "dr", "prof", "str",
    "tel", "abs", "art", "ff", "std", "min", "max", "mrd", "mio", "sog", "insb", "bspw", "uvm", "hrsg",
    "geb", "gem", "vs", "tsd", "jh", "fr", "hr", "dipl", "ing", "mwst", "ust", "kfz", "lkw", "pkw",
}
_SENTENCE_END = re.compile(r"([.!?…]+[\"“”«»)\]]*)(\s+)")
_LIST_ITEM = re.compile(r"^\s*(?:[-•*–]|\d{1,2}[.)])\s+")
_SOURCES = re.compile(r"^(Quellen aus dem Internet|Gelesene Dateien):\s+(.*)$")


def _starts_sentence(char: str, after: str) -> bool:
    if char.isupper() or char in "„\"“(«[":
        return True
    return char.isdigit() and after[-1:] in "!?"


def split_sentences(line: str) -> list[str]:
    """Teilt eine Zeile an Satzenden. Abkürzungen, Einzelbuchstaben (z. B.) und kurze Zahlen
    mit Punkt (1. Mai) sind kein Satzende, ebenso wenig ein Punkt vor einem Kleinbuchstaben."""
    parts, start = [], 0
    for match in _SENTENCE_END.finditer(line):
        rest = line[match.end():]
        if not rest or not _starts_sentence(rest[0], match.group(1)):
            continue
        if match.group(1).startswith("."):
            word = re.search(r"(\w+)$", line[:match.start(1)])
            w = word.group(1).lower() if word else ""
            if w in ABBREVIATIONS or len(w) == 1 or (w.isdigit() and len(w) <= 2):
                continue
        parts.append(line[start:match.end(1)].strip())
        start = match.end()
    parts.append(line[start:].strip())
    return [p for p in parts if p]


def _wrap(text: str, indent: str = "") -> list[str]:
    return textwrap.wrap(text, WIDTH, subsequent_indent=indent, break_long_words=False,
                         break_on_hyphens=False) or [""]


def to_lines(text: str) -> str:
    """Formatiert Fließtext zeilenweise. Leerzeilen bleiben (höchstens eine hintereinander)."""
    out: list[str] = []
    for raw in text.replace(" ", "\n").splitlines():
        line = raw.rstrip()
        if not line.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        sources = _SOURCES.match(line)
        if sources:
            out.append(sources.group(1) + ":")
            out += [f"- {item.strip()}" for item in sources.group(2).split(";") if item.strip()]
        elif _LIST_ITEM.match(line):
            out += _wrap(line.strip(), "  ")
        else:
            for sentence in split_sentences(line.strip()):
                out += _wrap(sentence)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)
