"""Technische Prüfung eines PDFs auf Layoutfehler und Lesbarkeit für Screenreader.

Ohne Sprachmodell, deshalb schnell und zuverlässig. Gefunden werden nur messbare Fehler: Text
außerhalb der Seite, überlappende Zeilen, winzige Schrift, unlesbare Zeichen, Bilder über dem Rand,
leere Seiten, unterschiedliche Seitengrößen, nicht eingebettete Schriften und fehlende Angaben für
Screenreader (Titel, Sprache, Struktur). Ob ein PDF "schön" aussieht, kann nur ein Mensch oder ein
Blick auf die Seite (seite_ansehen) beurteilen.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from core.files import FileReadError

MM = 72 / 25.4                    # Punkt je Millimeter
OUTSIDE_TOLERANCE = 1.5           # so viele Punkte über den Rand gelten noch als Rundungsfehler
EDGE_MM = 5                       # Text näher als so viele Millimeter am Rand ist auffällig
MIN_FONT_PT = 6
OVERLAP_SHARE = 0.4               # Anteil der kleineren Zeile, der überdeckt sein muss
MAX_LINES_FOR_OVERLAP = 500
MAX_PAGES = 300
BASE14 = ("helvetica", "times", "courier", "symbol", "zapfdingbats", "arial", "timesnewroman")

SEVERITY_ORDER = {"Fehler": 0, "Warnung": 1, "Hinweis": 2}


@dataclass
class Finding:
    page: int                     # 0: betrifft das ganze Dokument
    severity: str                 # Fehler, Warnung oder Hinweis
    text: str


def _mm(points: float) -> str:
    return f"{points / MM:.0f} mm"


def _sample(text: str, size: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= size else text[:size].rstrip() + " …"


def _overlap(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    smaller = min(a.get_area(), b.get_area())
    return inter.get_area() / smaller if smaller > 0 else 0.0


def _wordy(text: str) -> bool:
    """Mindestens zwei Buchstaben oder Ziffern: Striche, Punkte und Rahmen zählen nicht als Text."""
    return sum(ch.isalnum() for ch in text) >= 2


def _cut_sides(line: dict, bbox: pymupdf.Rect, rect: pymupdf.Rect) -> dict[str, float]:
    """Um wie viele Punkte ein Zeilentext an welcher Seite über die Seite hinausragt.

    Die Zeilenbox enthält Ober- und Unterlängen der Schrift und ist oben und unten großzügig. Bei
    waagerechtem Text zählt deshalb die Grundlinie (unten) und die Kappenhöhe (oben). Gedrehter Text
    bekommt eine Toleranz nach der Schriftgröße."""
    spans = line.get("spans", [])
    size = max((s.get("size", 0) for s in spans), default=0)
    dx, dy = line.get("dir", (1, 0))
    if abs(dy) < 0.1:                                       # waagerecht
        base = max(s["origin"][1] for s in spans)
        top = min(s["origin"][1] - 0.7 * s.get("size", 0) for s in spans)
        over = {"rechts": bbox.x1 - rect.x1, "links": rect.x0 - bbox.x0,
                "oben": rect.y0 - top, "unten": base - rect.y1}
        tolerance = OUTSIDE_TOLERANCE
    else:                                                   # gedreht
        over = {"rechts": bbox.x1 - rect.x1, "links": rect.x0 - bbox.x0,
                "oben": rect.y0 - bbox.y0, "unten": bbox.y1 - rect.y1}
        tolerance = max(OUTSIDE_TOLERANCE, 0.4 * size)
    return {side: v for side, v in over.items() if v > tolerance}


def _is_scan(page: pymupdf.Page) -> bool:
    """Ein Bild bedeckt fast die ganze Seite: ein Scan. Ein Text darüber ist unsichtbare Texterkennung."""
    area = page.rect.get_area()
    return area > 0 and any(pymupdf.Rect(i["bbox"]).intersect(page.rect).get_area() >= 0.8 * area
                            for i in page.get_image_info())


def _check_page(page: pymupdf.Page, number: int, findings: list[Finding]) -> None:
    rect = page.rect
    if _is_scan(page):
        findings.append(Finding(number, "Hinweis", "Gescannte Seite (ein Bild füllt die Seite). Der "
                                "Text darüber ist unsichtbare Texterkennung und wird nicht geprüft."))
        return
    # Ohne "clip" schneidet pymupdf Text am Seitenrand ab und wir würden ihn nie sehen.
    wide = pymupdf.Rect(rect.x0 - 3000, rect.y0 - 3000, rect.x1 + 3000, rect.y1 + 3000)
    data = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_LIGATURES, clip=wide)
    outside: dict[str, list[str]] = {}
    edge: list[str] = []
    tiny: list[str] = []
    broken = 0
    lines: list[tuple[pymupdf.Rect, str]] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(s.get("text", "") for s in line.get("spans", []))
            if not text.strip():
                continue
            broken += text.count("\ufffd") + sum(1 for ch in text if "\ue000" <= ch <= "\uf8ff")
            if not _wordy(text):
                continue
            bbox = pymupdf.Rect(line["bbox"])
            lines.append((pymupdf.Rect(bbox.x0, bbox.y0 + 0.15 * bbox.height,
                                       bbox.x1, bbox.y1 - 0.15 * bbox.height), text))
            sides = _cut_sides(line, bbox, rect)
            if sides:
                for side, v in sides.items():
                    outside.setdefault(side, []).append(f"{_sample(text)} ({_mm(v)})")
            elif min(bbox.x0 - rect.x0, rect.x1 - bbox.x1, bbox.y0 - rect.y0,
                     rect.y1 - bbox.y1) < EDGE_MM * MM:
                edge.append(_sample(text))
            for span in line.get("spans", []):
                if _wordy(span.get("text", "")) and span.get("size", 99) < MIN_FONT_PT:
                    tiny.append(_sample(span["text"], 25))

    for side, examples in outside.items():
        findings.append(Finding(number, "Fehler",
                                f"Text ragt {side} über die Seite hinaus und ist abgeschnitten: "
                                f"{len(examples)} Zeile(n), zum Beispiel {examples[0]}."))
    if edge:
        findings.append(Finding(number, "Warnung", f"Text steht weniger als {EDGE_MM} mm vom "
                                f"Seitenrand entfernt: {len(edge)} Zeile(n), zum Beispiel {edge[0]}."))
    if tiny:
        findings.append(Finding(number, "Warnung", f"Sehr kleine Schrift (unter {MIN_FONT_PT} Punkt): "
                                f"{len(tiny)} Stelle(n), zum Beispiel {tiny[0]}."))
    if broken:
        findings.append(Finding(number, "Fehler", f"{broken} Zeichen sind nicht lesbar "
                                "(Ersatz- oder Sonderzeichen, Schrift ohne Zuordnung)."))

    if 1 < len(lines) <= MAX_LINES_FOR_OVERLAP:
        clashes = []
        for i, (ra, ta) in enumerate(lines):
            for rb, tb in lines[i + 1:]:
                if ta.strip() != tb.strip() and _overlap(ra, rb) >= OVERLAP_SHARE:
                    clashes.append((ta, tb))
        if clashes:
            a, b = clashes[0]
            findings.append(Finding(number, "Fehler", f"Text überlappt sich: {len(clashes)} Stelle(n), "
                                    f"zum Beispiel {_sample(a, 30)} und {_sample(b, 30)}."))

    cut = []
    for info in page.get_image_info():
        box = pymupdf.Rect(info["bbox"])
        if (box.x1 - rect.x1 > 2 * OUTSIDE_TOLERANCE or rect.x0 - box.x0 > 2 * OUTSIDE_TOLERANCE
                or box.y1 - rect.y1 > 2 * OUTSIDE_TOLERANCE or rect.y0 - box.y0 > 2 * OUTSIDE_TOLERANCE):
            cut.append(box)
    if cut:
        findings.append(Finding(number, "Warnung", f"{len(cut)} Bild(er) ragen über den Seitenrand "
                                "hinaus und sind angeschnitten."))

    if not lines and not page.get_images() and not page.get_drawings():
        findings.append(Finding(number, "Hinweis", "Die Seite ist leer."))


def check_pdf(path: str | Path) -> tuple[int, list[Finding]]:
    """Prüft das PDF. Gibt (Seitenzahl, Befunde) zurück. Wirft FileReadError."""
    try:
        doc = pymupdf.open(str(path))
    except Exception as exc:
        raise FileReadError(f"Die Datei konnte nicht geöffnet werden: {exc}") from exc
    findings: list[Finding] = []
    with doc:
        if doc.needs_pass:
            raise FileReadError("Die PDF-Datei ist passwortgeschützt.")
        if not doc.is_pdf:
            raise FileReadError("Das ist keine PDF-Datei.")
        pages = doc.page_count
        sizes: dict[tuple[int, int], list[int]] = {}
        loose_fonts: set[str] = set()
        text_pages = 0
        for number in range(1, min(pages, MAX_PAGES) + 1):
            page = doc[number - 1]
            _check_page(page, number, findings)
            if page.get_text("text").strip():
                text_pages += 1
            sizes.setdefault((round(page.rect.width / MM), round(page.rect.height / MM)), []).append(number)
            for font in page.get_fonts():
                name = str(font[3]).split("+")[-1]
                if font[1] == "n/a" and not name.lower().replace("-", "").startswith(BASE14):
                    loose_fonts.add(name)
        if pages > MAX_PAGES:
            findings.append(Finding(0, "Hinweis", f"Nur die ersten {MAX_PAGES} von {pages} Seiten "
                                    "wurden geprüft."))
        if len(sizes) > 1:
            listing = "; ".join(f"{w} x {h} mm: Seite {_numbers(n)}" for (w, h), n in sizes.items())
            findings.append(Finding(0, "Hinweis", f"Die Seiten haben unterschiedliche Größen ({listing})."))
        if loose_fonts:
            findings.append(Finding(0, "Hinweis", "Schriften sind nicht eingebettet und werden auf "
                                    f"anderen Rechnern eventuell ersetzt: {', '.join(sorted(loose_fonts)[:5])}."))
        if text_pages == 0:
            findings.append(Finding(0, "Fehler", "Das PDF enthält keinen Text. Vermutlich ein Scan: "
                                    "Ein Screenreader kann es nicht lesen."))
        _accessibility(doc, findings)
    findings.sort(key=lambda f: (f.page, SEVERITY_ORDER[f.severity]))
    return pages, findings


def _numbers(pages: list[int]) -> str:
    from core.pdfs import ranges
    return ranges(pages)


def _accessibility(doc: pymupdf.Document, findings: list[Finding]) -> None:
    """Angaben, die Screenreader brauchen: Titel, Sprache und Struktur (getaggtes PDF)."""
    catalog = doc.pdf_catalog()
    if not (doc.metadata or {}).get("title", "").strip():
        findings.append(Finding(0, "Hinweis", "Das PDF hat keinen Titel in den Dokumenteigenschaften."))
    if doc.xref_get_key(catalog, "Lang")[0] in ("null", "undefined"):
        findings.append(Finding(0, "Hinweis", "Keine Dokumentsprache eingetragen. Ein Screenreader "
                                "kann die falsche Aussprache wählen."))
    tagged = doc.xref_get_key(catalog, "StructTreeRoot")[0] not in ("null", "undefined")
    if not tagged:
        findings.append(Finding(0, "Warnung", "Das PDF ist nicht getaggt (keine Struktur). Ein "
                                "Screenreader liest Überschriften, Listen und Tabellen dann schlecht."))


def format_report(name: str, pages: int, findings: list[Finding]) -> str:
    """Bericht als einfacher Text, geeignet zum Vorlesen."""
    problems = [f for f in findings if f.severity != "Hinweis"]
    head = f"Prüfung von {name}: {pages} Seite(n), {len(problems)} Auffälligkeit(en)"
    if len(findings) > len(problems):
        head += f" und {len(findings) - len(problems)} Hinweis(e)"
    lines = [head + "."]
    for f in findings:
        where = "Dokument" if f.page == 0 else f"Seite {f.page}"
        lines.append(f"{where}, {f.severity}: {f.text}")
    layout_pages = sorted({f.page for f in problems if f.page})
    if not layout_pages:
        lines.append("Es wurden keine messbaren Layoutfehler auf den Seiten gefunden. Ob die Seiten "
                     "gut aussehen, zeigt nur ein Blick auf die Seite: bitten Sie darum, eine Seite "
                     "anzusehen.")
    else:
        lines.append(f"Auffällige Seiten: {_numbers(layout_pages)}. Ein Blick auf die Seite zeigt "
                     "genauer, was los ist: bitten Sie darum, die Seite anzusehen.")
    return "\n".join(lines)
