"""Freigegebene Ordner: Das Modell darf darin Dateien auflisten, durchsuchen und lesen.

Nur unterhalb der freigegebenen Ordner (auch nicht über Verknüpfungen oder ".."). Nur lesend.
"""
from __future__ import annotations

from pathlib import Path

from core.files import SUPPORTED, FileReadError, read_file

MAX_FILES = 500
MAX_FILE_BYTES = 25_000_000
READ_CHUNK = 8000


class FolderError(Exception):
    """Der Zugriff ist nicht möglich. Der Text ist für das Modell und die Person gedacht."""


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _hidden(path: Path, root: Path) -> bool:
    """Versteckte Ordner und Dateien (Name beginnt mit Punkt) bleiben unsichtbar und gesperrt."""
    return any(part.startswith(".") for part in path.relative_to(root).parts)


class FolderAccess:
    def __init__(self) -> None:
        self.roots: list[Path] = []
        self._cache: dict[tuple[str, float], str] = {}

    # -- Freigabe ----------------------------------------------------------------
    def grant(self, path: str | Path) -> Path:
        root = Path(path).resolve()
        if not root.is_dir():
            raise FolderError(f"Der Ordner {path} existiert nicht.")
        if root not in self.roots:
            self.roots.append(root)
        return root

    def revoke(self, path: str | Path) -> None:
        root = Path(path).resolve()
        self.roots = [r for r in self.roots if r != root]

    def clear(self) -> None:
        self.roots.clear()
        self._cache.clear()

    # -- Dateien -------------------------------------------------------------------
    def files(self) -> list[Path]:
        found: list[Path] = []
        for root in self.roots:
            for path in sorted(root.rglob("*")):
                if len(found) >= MAX_FILES:
                    return found
                if (path.is_file() and path.suffix.lower() in SUPPORTED
                        and not _hidden(path, root) and _inside(path.resolve(), root)):
                    found.append(path)
        return found

    def _label(self, path: Path) -> str:
        for root in self.roots:
            if _inside(path.resolve(), root):
                prefix = root.name if len(self.roots) > 1 else ""
                rel = path.resolve().relative_to(root).as_posix()
                return f"{prefix}/{rel}" if prefix else rel
        return path.name

    def list_text(self) -> str:
        files = self.files()
        if not files:
            return "Die freigegebenen Ordner enthalten keine lesbaren Dateien."
        lines = [f"{self._label(p)} ({max(1, p.stat().st_size // 1024)} KB)" for p in files]
        more = "\n(Weitere Dateien wurden nicht aufgelistet.)" if len(files) >= MAX_FILES else ""
        return "Dateien in den freigegebenen Ordnern:\n" + "\n".join(lines) + more

    def _resolve(self, name: str) -> Path:
        name = name.strip().strip('"')
        if not name:
            raise FolderError("Es wurde kein Dateiname angegeben.")
        candidate = Path(name)
        # 1. Pfad relativ zu einem Ordner (oder absolut)
        options = [candidate] if candidate.is_absolute() else [r / name for r in self.roots]
        if not candidate.is_absolute() and len(self.roots) > 1:
            first, _, rest = name.replace("\\", "/").partition("/")
            options += [r / rest for r in self.roots if r.name == first and rest]
        for option in options:
            try:
                resolved = option.resolve()
            except OSError:
                continue
            if resolved.is_file() and any(_inside(resolved, r) and not _hidden(resolved, r)
                                          for r in self.roots):
                return resolved
        # 2. nur der Dateiname
        matches = [p for p in self.files() if p.name.lower() == candidate.name.lower()]
        if len(matches) == 1:
            return matches[0].resolve()
        if len(matches) > 1:
            raise FolderError("Der Name ist nicht eindeutig: "
                              + ", ".join(self._label(p) for p in matches[:5]))
        raise FolderError(f"Die Datei {name} wurde in den freigegebenen Ordnern nicht gefunden.")

    def _text(self, path: Path) -> str:
        key = (str(path), path.stat().st_mtime)
        if key not in self._cache:
            if path.stat().st_size > MAX_FILE_BYTES:
                raise FolderError(f"Die Datei {path.name} ist zu groß.")
            try:
                self._cache[key] = read_file(path).text
            except FileReadError as exc:
                raise FolderError(f"{path.name}: {exc}") from exc
        return self._cache[key]

    def read(self, name: str, start: int = 0) -> tuple[str, str]:
        """(Bezeichnung, Text) ab Zeichen start, höchstens READ_CHUNK Zeichen."""
        path = self._resolve(name)
        text = self._text(path)
        start = max(0, int(start))
        piece = text[start:start + READ_CHUNK]
        label = self._label(path)
        if not piece:
            return label, f"Die Datei hat nur {len(text)} Zeichen."
        end = start + len(piece)
        note = (f"\n[Zeichen {start} bis {end} von {len(text)}. Für den Rest datei_lesen mit "
                f"start={end} aufrufen.]" if end < len(text) else "")
        return label, piece + note

    def search(self, term: str, max_hits: int = 8) -> str:
        return self.search_with_labels(term, max_hits)[0]

    def search_with_labels(self, term: str, max_hits: int = 8) -> tuple[str, list[str]]:
        """(Text für das Modell, Bezeichnungen der Dateien mit Treffern)."""
        term = term.strip().lower()
        if not term:
            raise FolderError("Es wurde kein Suchbegriff angegeben.")
        words = term.split()
        hits: list[str] = []
        labels: list[str] = []
        scanned = 0
        for path in self.files():
            scanned += 1
            try:
                text = self._text(path)
            except FolderError:
                continue
            lower = text.lower()
            pos = lower.find(term)
            if pos < 0 and not all(w in lower for w in words):
                continue
            pos = max(0, pos if pos >= 0 else lower.find(words[0]))
            snippet = " ".join(text[max(0, pos - 80):pos + 160].split())
            labels.append(self._label(path))
            hits.append(f"{labels[-1]}: … {snippet} …")
            if len(hits) >= max_hits:
                break
        if not hits:
            return f"Kein Treffer für \"{term}\" in {scanned} Dateien.", []
        return f"Treffer für \"{term}\":\n" + "\n".join(hits), labels
