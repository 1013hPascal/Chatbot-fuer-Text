"""Speicher für Projekte, Chats und deren Verlauf (SQLite).

Ein Projekt fasst Chats zusammen. Ein Chat ist eine Unterhaltung. Jede Frage mit Antwort ist ein
Verlaufseintrag (Exchange) des Chats. Angehängte Dateien und Ordner gehören zum Chat,
Projektdateien zum Projekt (alle Chats darin können sie lesen).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.config import app_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    attachments TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS exchanges (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    created TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,                  -- Inhalt des Antwortfelds
    comment TEXT NOT NULL DEFAULT '',      -- gesprochener Teil, wenn ein Text dabei ist
    is_doc INTEGER NOT NULL DEFAULT 0,     -- 1: hinter dem Kommentar steht ein Text
    doc_title TEXT NOT NULL DEFAULT '',
    word_filename TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS project_files (      -- Projektdateien: für alle Chats des Projekts lesbar
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    added TEXT NOT NULL,
    UNIQUE (project_id, path)
);
CREATE INDEX IF NOT EXISTS exchanges_chat ON exchanges(chat_id);
CREATE INDEX IF NOT EXISTS chats_project ON chats(project_id);
"""


def _now() -> datetime:
    return datetime.now()          # mit Mikrosekunden, damit die Reihenfolge eindeutig bleibt


@dataclass
class Project:
    id: int
    name: str
    created: datetime


@dataclass
class Chat:
    id: int
    title: str
    project_id: int | None
    created: datetime
    updated: datetime
    attachments: list[dict] = field(default_factory=list)   # {"type": "file"|"folder", "path"}


@dataclass
class ProjectFile:
    id: int
    project_id: int
    path: str
    added: datetime

    @property
    def name(self) -> str:
        return Path(self.path).name


@dataclass
class Exchange:
    id: int
    chat_id: int
    created: datetime
    question: str
    answer: str
    comment: str = ""
    is_doc: bool = False
    doc_title: str = ""
    word_filename: str = ""


def title_from_question(question: str, limit: int = 60) -> str:
    text = " ".join(question.split())
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


class Store:
    def __init__(self, path: Path | str | None = None):
        self.conn = sqlite3.connect(str(path or app_dir() / "chats.db"), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.execute("PRAGMA foreign_keys = ON")
            columns = [r["name"] for r in self.conn.execute("PRAGMA table_info(project_files)")]
            if columns and "project_id" not in columns:
                # Die erste Fassung kannte nur gemeinsame Dateien ohne Projekt. Sie gehören jetzt
                # zu einem Projekt, und diese Einträge haben keins. Die Tabelle wird neu angelegt.
                self.conn.execute("DROP TABLE project_files")
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    # -- Projekte ------------------------------------------------------------
    def add_project(self, name: str) -> Project:
        now = _now()
        with self.lock:
            cur = self.conn.execute("INSERT INTO projects (name, created) VALUES (?, ?)",
                                    (name.strip(), now.isoformat()))
            self.conn.commit()
        return Project(cur.lastrowid, name.strip(), now)

    def projects(self) -> list[Project]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM projects ORDER BY name COLLATE NOCASE").fetchall()
        return [Project(r["id"], r["name"], datetime.fromisoformat(r["created"])) for r in rows]

    def get_project(self, project_id: int) -> Project | None:
        with self.lock:
            r = self.conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return Project(r["id"], r["name"], datetime.fromisoformat(r["created"])) if r else None

    def rename_project(self, project_id: int, name: str) -> None:
        with self.lock:
            self.conn.execute("UPDATE projects SET name=? WHERE id=?", (name.strip(), project_id))
            self.conn.commit()

    def delete_project(self, project_id: int) -> None:
        """Löscht nur das Projekt. Die Chats bleiben erhalten und sind danach ohne Projekt."""
        with self.lock:
            self.conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
            self.conn.commit()

    # -- Chats -----------------------------------------------------------------
    @staticmethod
    def _chat(r: sqlite3.Row) -> Chat:
        return Chat(r["id"], r["title"], r["project_id"], datetime.fromisoformat(r["created"]),
                    datetime.fromisoformat(r["updated"]), json.loads(r["attachments"]))

    def create_chat(self, title: str, project_id: int | None = None) -> Chat:
        now = _now()
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO chats (title, project_id, created, updated) VALUES (?, ?, ?, ?)",
                (title, project_id, now.isoformat(), now.isoformat()))
            self.conn.commit()
        return Chat(cur.lastrowid, title, project_id, now, now)

    def get_chat(self, chat_id: int) -> Chat | None:
        with self.lock:
            r = self.conn.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
        return self._chat(r) if r else None

    def chats(self, limit: int = 200) -> list[Chat]:
        """Zuletzt benutzte zuerst."""
        with self.lock:
            rows = self.conn.execute("SELECT * FROM chats ORDER BY updated DESC, id DESC LIMIT ?",
                                     (limit,)).fetchall()
        return [self._chat(r) for r in rows]

    def chats_in_project(self, project_id: int) -> list[Chat]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM chats WHERE project_id=? "
                                     "ORDER BY updated DESC, id DESC", (project_id,)).fetchall()
        return [self._chat(r) for r in rows]

    def chats_without_project(self, limit: int = 100) -> list[Chat]:
        """Die Chatliste: alle Chats, die in keinem Projekt sind. Zuletzt benutzte zuerst."""
        with self.lock:
            rows = self.conn.execute("SELECT * FROM chats WHERE project_id IS NULL "
                                     "ORDER BY updated DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [self._chat(r) for r in rows]

    def copy_chat(self, chat_id: int, project_id: int | None) -> Chat:
        """Legt eine Kopie des Chats (mit Verlauf und Anhängen) im Projekt an."""
        source = self.get_chat(chat_id)
        if source is None:
            raise KeyError(chat_id)
        now = _now()
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO chats (title, project_id, created, updated, attachments) "
                "VALUES (?, ?, ?, ?, ?)",
                (source.title, project_id, now.isoformat(), now.isoformat(),
                 json.dumps(source.attachments, ensure_ascii=False)))
            new_id = cur.lastrowid
            self.conn.execute(
                "INSERT INTO exchanges (chat_id, created, question, answer, comment, is_doc, "
                "doc_title, word_filename) SELECT ?, created, question, answer, comment, is_doc, "
                "doc_title, word_filename FROM exchanges WHERE chat_id=? ORDER BY id", (new_id, chat_id))
            self.conn.commit()
        return self.get_chat(new_id)

    def rename_chat(self, chat_id: int, title: str) -> None:
        with self.lock:
            self.conn.execute("UPDATE chats SET title=? WHERE id=?", (title.strip(), chat_id))
            self.conn.commit()

    def set_chat_project(self, chat_id: int, project_id: int | None) -> None:
        with self.lock:
            self.conn.execute("UPDATE chats SET project_id=? WHERE id=?", (project_id, chat_id))
            self.conn.commit()

    def set_attachments(self, chat_id: int, attachments: list[dict]) -> None:
        with self.lock:
            self.conn.execute("UPDATE chats SET attachments=? WHERE id=?",
                              (json.dumps(attachments, ensure_ascii=False), chat_id))
            self.conn.commit()

    def delete_chat(self, chat_id: int) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM chats WHERE id=?", (chat_id,))
            self.conn.commit()

    # -- Projektdateien ----------------------------------------------------------
    @staticmethod
    def _project_file(r: sqlite3.Row) -> ProjectFile:
        return ProjectFile(r["id"], r["project_id"], r["path"], datetime.fromisoformat(r["added"]))

    def add_project_file(self, project_id: int, path: str) -> ProjectFile:
        """Fügt dem Projekt eine Datei hinzu. Ist sie dort schon, bleibt es bei dem einen Eintrag."""
        with self.lock:
            self.conn.execute("INSERT OR IGNORE INTO project_files (project_id, path, added) "
                              "VALUES (?, ?, ?)", (project_id, str(path), _now().isoformat()))
            self.conn.commit()
            r = self.conn.execute("SELECT * FROM project_files WHERE project_id=? AND path=?",
                                  (project_id, str(path))).fetchone()
        return self._project_file(r)

    def project_files(self, project_id: int) -> list[ProjectFile]:
        """Die Projektdateien des Projekts, nach Dateiname sortiert."""
        with self.lock:
            rows = self.conn.execute("SELECT * FROM project_files WHERE project_id=?",
                                     (project_id,)).fetchall()
        return sorted((self._project_file(r) for r in rows), key=lambda f: (f.name.lower(), f.id))

    def get_project_file(self, file_id: int) -> ProjectFile | None:
        with self.lock:
            r = self.conn.execute("SELECT * FROM project_files WHERE id=?", (file_id,)).fetchone()
        return self._project_file(r) if r else None

    def remove_project_file(self, file_id: int) -> None:
        """Entfernt nur den Eintrag. Die Datei selbst bleibt unverändert."""
        with self.lock:
            self.conn.execute("DELETE FROM project_files WHERE id=?", (file_id,))
            self.conn.commit()

    # -- Verlauf ---------------------------------------------------------------
    def add_exchange(self, chat_id: int, question: str, answer: str, comment: str = "",
                     is_doc: bool = False, doc_title: str = "",
                     word_filename: str = "") -> Exchange:
        now = _now()
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO exchanges (chat_id, created, question, answer, comment, is_doc, "
                "doc_title, word_filename) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (chat_id, now.isoformat(), question, answer, comment, int(is_doc), doc_title,
                 word_filename))
            self.conn.execute("UPDATE chats SET updated=? WHERE id=?", (now.isoformat(), chat_id))
            self.conn.commit()
        return Exchange(cur.lastrowid, chat_id, now, question, answer, comment, is_doc,
                        doc_title, word_filename)

    def exchanges(self, chat_id: int) -> list[Exchange]:
        """Neueste zuerst."""
        with self.lock:
            rows = self.conn.execute("SELECT * FROM exchanges WHERE chat_id=? ORDER BY id DESC",
                                     (chat_id,)).fetchall()
        return [Exchange(r["id"], r["chat_id"], datetime.fromisoformat(r["created"]),
                         r["question"], r["answer"], r["comment"], bool(r["is_doc"]),
                         r["doc_title"], r["word_filename"]) for r in rows]

    def update_exchange_answer(self, exchange_id: int, answer: str) -> None:
        """Hält Änderungen der Person am Antwortfeld fest (eine Textversion mehr im Verlauf)."""
        with self.lock:
            self.conn.execute("UPDATE exchanges SET answer=? WHERE id=?", (answer, exchange_id))
            self.conn.commit()

