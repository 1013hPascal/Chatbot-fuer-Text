"""Der "Planer" in Code statt in einem Modell: Er erkennt sofort, wann eine Frage sicher eine
Internetsuche braucht. Die Suche läuft dann schon vor dem ersten Modellaufruf. Das spart eine ganze
Modellrunde (etwa 7 bis 9 Sekunden), in der das Modell sonst nur beschließt, zu suchen.

Vorsichtig gewählt: Nur eindeutige Fälle. Im Zweifel entscheidet weiter das Modell selbst, denn
es behält die Suchwerkzeuge. Eine unnötige Suche kostet etwa 7 Sekunden Einlesezeit.
"""
from __future__ import annotations

import re

# Wörter, bei denen die Antwort sich ändern kann. Mehrdeutige wie "heute", "gerade", "Kurs" fehlen
# absichtlich. "kostet" und "Preis" zählen nur, wenn nichts Eigenes (Datei, Text) im Spiel ist.
# Das prüft wants_web_search.
_NEEDS_WEB = re.compile(
    r"(?<!\w)(aktuell\w*|derzeit\w*|momentan\w*|neueste\w*|wetter\w*|nachrichten|öffnungszeiten|"
    r"fahrplan|recherchier\w*|kostet|preis\w*|im internet|im netz)(?!\w)", re.I)
_WRITING = re.compile(
    r"^\W*(schreib\w*|formulier\w*|verfass\w*|übersetz\w*|korrigier\w*|kürz\w*|überarbeit\w*|"
    r"fass\w*|mach\w*|ändere\w*|erstell\w*)(?!\w)", re.I)
_MAX_QUERY = 200


def wants_web_search(question: str, has_text: bool = False, has_material: bool = False) -> bool:
    """has_text: im Antwortfeld steht ein Text zum Weiterarbeiten. has_material: es gibt
    hinzugefügte Dateien, Ordner oder Dokumente, dann geht es meist um diese."""
    if has_text or has_material or _WRITING.match(question):
        return False
    return bool(_NEEDS_WEB.search(question))


def search_query(question: str) -> str:
    """Die Frage selbst als Suchanfrage (Suchmaschinen verstehen ganze Fragen gut)."""
    return " ".join(question.split())[:_MAX_QUERY]
