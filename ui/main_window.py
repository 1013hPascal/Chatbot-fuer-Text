"""Hauptfenster: setzt die Bereiche zusammen und regelt Menüs, Chats, Projekte, Fokus und Ansagen.

Seite von oben nach unten (Tab = weiter, nach dem Verlauf wieder zur Frage):
Frage, Antwort, Aktionen, Verlauf.
Projekte, Chatliste, Einstellungen, Datei, Ansicht und Hilfe liegen in der Menüleiste. Auf Projekten
und Chats öffnet die Menütaste (oder Umschalt+F10) ein Kontextmenü.
"""
from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

import psutil
from PySide6.QtCore import QEvent, QStandardPaths, Qt, QTimer
from PySide6.QtGui import (QAction, QActionGroup, QGuiApplication, QKeyEvent, QKeySequence,
                           QShortcut)
from PySide6.QtWidgets import (QApplication, QFileDialog, QInputDialog, QLineEdit, QMainWindow,
                               QMenu, QMenuBar, QVBoxLayout, QWidget)

from core import pdfcheck, pdfs
from core.config import AVAILABLE_MODELS, Config
from core.conversation import ChatSession, TurnResult
from core.files import SUPPORTED, FileReadError
from core.folders import FolderError
from core.llm import LLMBackend, LLMError
from core.store import Chat, Exchange, Project, Store, title_from_question
from core.tools import ToolBox
from core.wordexport import safe_filename, save_docx
from ui import actions_panel as ap
from ui.actions_panel import ActionsPanel
from ui.announcer import announce, announcer
from ui.answer_panel import AnswerPanel
from ui.common import confirm, show_error
from ui.dialogs import ShortcutsDialog
from ui.history_panel import HistoryPanel
from ui.menus import AccessibleMenu, ContextMenu, close_all_popups
from ui.question_panel import QuestionPanel
from ui.workers import Task

log = logging.getLogger(__name__)

FILE_FILTER = ("Dateien (" + " ".join(f"*{s}" for s in sorted(SUPPORTED | pdfs.IMAGE_SUFFIXES))
               + ");;Alle Dateien (*)")
MIN_FONT, MAX_FONT = 10, 32
TITLE = "Chatbot für Text"
MAX_CHATS_IN_MENU = 100
SETTING_LABELS = {"long_answers": "Lange Antworten", "thinking": "Nachdenken",
                  "web_search": "Internetrecherche"}


def _plural(n: int, one: str, many: str) -> str:
    return f"1 {one}" if n == 1 else f"{n} {many}"


def _menu_text(text: str, limit: int = 70) -> str:
    """Titel als Menütext: '&' verdoppeln, damit kein Alt-Kürzel entsteht, und kürzen."""
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit].rstrip() + " …"
    return text.replace("&", "&&")


def _select_first(menu: QMenu) -> None:
    """Wie Pfeil runter: markiert den ersten Eintrag, ohne ein Untermenü zu öffnen."""
    if menu.activeAction() is None:
        QApplication.sendEvent(menu, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down,
                                               Qt.KeyboardModifier.NoModifier))


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config, backend: LLMBackend, store: Store,
                 toolbox: ToolBox | None = None):
        super().__init__()
        self.cfg = cfg
        self.backend = backend
        self.store = store
        self.session = ChatSession(cfg, backend, toolbox)

        self.engine_ready = False
        self._startup_task: Task | None = None
        self._ask_task: Task | None = None
        self._last_status = ""
        self._pending_question = ""
        self.chat_id: int | None = None                 # None: neuer Chat, noch nichts gespeichert
        self.new_chat_project: int | None = None        # Projekt, in dem der neue Chat entsteht
        self._meta: list[dict] = []                     # Dateien und Ordner dieses Chats
        self._current_exchange: Exchange | None = None
        self._word_filename = ""
        self._doc_title = ""
        self._dynamic_chat_actions: list[QAction] = []
        self._dynamic_project_actions: list[QAction] = []
        self._focus_before_menu_bar: QWidget | None = None
        self._project_file_notes: list[str] = []
        self._loaded_project_paths: set[str] = set()   # Dateien, die als Projektdatei geladen sind
        QApplication.instance().focusChanged.connect(self._remember_focus)

        self.question = QuestionPanel()
        self.answer = AnswerPanel()
        self.actions = ActionsPanel()
        self.history_panel = HistoryPanel()
        self._areas = [self.question, self.answer, self.actions, self.history_panel]

        central = QWidget()
        layout = QVBoxLayout(central)
        for panel, stretch in zip(self._areas, (0, 6, 1, 2)):
            layout.addWidget(panel, stretch)
        self.setCentralWidget(central)
        self.resize(900, 900)

        self._build_menus()
        self._build_shortcuts()
        self._set_tab_order()
        self._connect()
        announcer.target = self
        self._project_file_notes = self._sync_project_files()
        self._apply_font()
        self._update_actions()
        self._update_title()

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _action(self, menu: QMenu | None, text: str, slot, *shortcuts,
                checkable: bool = False) -> QAction:
        action = QAction(text, self)
        if shortcuts:
            action.setShortcuts([QKeySequence(s) for s in shortcuts])
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            self.addAction(action)                     # Kürzel gelten auch bei geschlossenem Menü
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        if menu is not None:
            menu.addAction(action)
        return action

    def _context_menu(self, title: str) -> ContextMenu:
        menu = ContextMenu(title, self)
        menu.contextRequested.connect(self._show_context_menu)
        return menu

    def _build_menus(self) -> None:
        bar = self.menuBar()

        # 1. Projekte: Neues Projekt, darunter die Projekte (Enter öffnet die Chatliste)
        self.projects_menu = self._context_menu("&Projekte")
        bar.addMenu(self.projects_menu)
        self.act_new_project = self._action(self.projects_menu, "&Neues Projekt …",
                                            self._new_project)
        self._projects_separator = self.projects_menu.addSeparator()
        self.projects_menu.aboutToShow.connect(self._fill_projects_menu)

        # 2. Chatliste: Neuer Chat, darunter alle Chats ohne Projekt
        self.chats_menu = self._context_menu("Cha&tliste")
        bar.addMenu(self.chats_menu)
        self.act_new_chat = self._action(self.chats_menu, "&Neuer Chat",
                                         lambda checked=False: self._new_chat(None), "Ctrl+N")
        self._chats_separator = self.chats_menu.addSeparator()
        self.chats_menu.aboutToShow.connect(self._fill_chats_menu)

        # 3. Einstellungen: Häkchen-Einträge
        m = bar.addMenu("&Einstellungen")
        self.setting_actions: dict[str, QAction] = {}
        for key, text in (("long_answers", "&Lange Antworten"), ("thinking", "&Nachdenken"),
                          ("web_search", "&Internetrecherche")):
            action = self._action(m, text, lambda checked=False: None, checkable=True)
            action.setChecked(bool(getattr(self.cfg, key)))
            action.toggled.connect(lambda state, k=key: self._on_setting(k, state))
            self.setting_actions[key] = action
        m.addSeparator()
        # Modell: genau eines ist gewählt (Häkchen). Ein eigener Name aus config.json steht mit dabei.
        model_menu = AccessibleMenu("&Modell", m)
        m.addMenu(model_menu)
        self.model_group = QActionGroup(self)
        self.model_actions: dict[str, QAction] = {}
        models = list(AVAILABLE_MODELS)
        if self.cfg.chat_model not in dict(models):
            models.insert(0, (self.cfg.chat_model, self.cfg.chat_model))
        for name, label in models:
            action = self._action(model_menu, label.replace("&", "&&"),
                                  lambda checked=False: None, checkable=True)
            action.setChecked(name == self.cfg.chat_model)
            action.triggered.connect(lambda checked=False, n=name: self._on_model(n))
            self.model_group.addAction(action)
            self.model_actions[name] = action
        self.act_tavily = self._action(m, "&Tavily-Schlüssel …", self._on_tavily_key)

        # 4. Datei
        m = bar.addMenu("&Datei")
        self.act_add_file = self._action(m, "&Datei hinzufügen …", self._on_add_file, "Ctrl+O")
        self.act_add_folder = self._action(m, "&Ordner hinzufügen …", self._on_add_folder,
                                           "Ctrl+Shift+O")
        self.act_word = self._action(m, "Text als &Word-Dokument speichern …", self._save_word,
                                     "Ctrl+S")
        self.act_check_pdf = self._action(m, "&PDF prüfen …", self._check_pdf)
        m.addSeparator()
        self._action(m, "&Beenden", self.close, "Ctrl+Q")

        m = bar.addMenu("A&nsicht")
        self._action(m, "Schrift &größer", lambda checked=False: self._change_font(+1),
                     QKeySequence.StandardKey.ZoomIn, "Ctrl+=")
        self._action(m, "Schrift &kleiner", lambda checked=False: self._change_font(-1),
                     QKeySequence.StandardKey.ZoomOut)

        m = bar.addMenu("&Hilfe")
        self._action(m, "&Tastenkürzel anzeigen", self._show_shortcuts, "F1")

        # Kürzel ohne Menüeintrag
        self.act_cancel = self._action(None, "Abbrechen", self._on_cancel, "Esc")
        self.act_cancel.setEnabled(False)
        self.act_send = self._action(None, "Frage senden", self._on_ask, "Ctrl+Return",
                                     "Ctrl+Enter")
        self._action(None, "Antwort kopieren", self._copy_answer, "Ctrl+Shift+C")
        self._action(None, "Text kopieren", self._copy_document, "Ctrl+Shift+T")

    def _build_shortcuts(self) -> None:
        targets = (self._focus_question, self._focus_answer, self._focus_actions,
                   self._focus_history)
        for number, target in enumerate(targets, start=1):
            QShortcut(QKeySequence(f"Ctrl+{number}"), self, activated=target)
        QShortcut(QKeySequence("F6"), self, activated=lambda: self._cycle_area(+1))
        QShortcut(QKeySequence("Shift+F6"), self, activated=lambda: self._cycle_area(-1))

    def _set_tab_order(self) -> None:
        chain = [self.question.edit, self.answer.edit, self.actions.list, self.history_panel.list]
        for first, second in zip(chain, chain[1:]):
            QWidget.setTabOrder(first, second)
        QWidget.setTabOrder(chain[-1], chain[0])       # nach dem Verlauf wieder zur Frage
        self.tab_chain = chain

    def _connect(self) -> None:
        self.history_panel.entryActivated.connect(self._load_exchange)
        self.question.askRequested.connect(self._on_ask)
        self.actions.actionRequested.connect(self._run_action)
        self.actions.removeAttachmentRequested.connect(self._remove_attachment)

    def _run_action(self, key: str) -> None:
        handler = {ap.COPY_ANSWER: self._copy_answer, ap.COPY_TEXT: self._copy_document,
                   ap.WORD: self._save_word, ap.ADD_FILE: self._on_add_file,
                   ap.ADD_FOLDER: self._on_add_folder}.get(key)
        if handler is not None:
            handler()

    # ------------------------------------------------------------------
    # Start des Sprachmodells
    # ------------------------------------------------------------------
    def start_engine(self, unload: str | None = None) -> None:
        """Server starten, Modell laden und aufwärmen (im Hintergrund).
        unload: ein früher gewähltes Modell, das aus dem Arbeitsspeicher genommen wird."""
        self.engine_ready = False
        self.question.set_status("Modell wird geladen")
        self._update_actions()
        self._update_title()

        def startup(task: Task):
            self.backend.start()
            if unload:
                self.backend.unload(unload)
            missing = self.backend.missing_models()
            if missing:
                raise LLMError("Dieses Modell fehlt: " + ", ".join(missing) +
                               f". Bitte im Terminal ausführen: ollama pull {missing[0]}")
            self.backend.warmup()
            return self.backend.device_status()

        task = Task(startup, self)
        task.result.connect(self._engine_started)
        task.error.connect(self._engine_failed)
        task.finished.connect(task.deleteLater)
        self._startup_task = task
        task.start()

    def _engine_started(self, status) -> None:
        self._startup_task = None
        self.engine_ready = True
        message = f"Bereit. {status.text}."
        limits = self.session.limits_note()
        if limits:
            message += " " + limits
        if not status.on_gpu:
            message += " Antworten dauern im CPU-Modus länger."
        battery = psutil.sensors_battery()
        if battery is not None and not battery.power_plugged:
            message += (" Hinweis: Der Rechner läuft im Akkubetrieb. Mit Netzteil und dem "
                        "Windows-Energiemodus Höchstleistung geht es schneller.")
        self.question.set_status(message)
        announce(message, dringend=not status.on_gpu and self.cfg.use_gpu)
        self._update_actions()
        self._update_title()

    def _engine_failed(self, message: str) -> None:
        self._startup_task = None
        self.question.set_status(f"Fehler: {message}")
        announce(f"Fehler: {message}", dringend=True)
        previous = QApplication.focusWidget()
        show_error(self, "Sprachmodell nicht bereit", message)
        if previous is not None:
            previous.setFocus()

    # ------------------------------------------------------------------
    # Einstellungen
    # ------------------------------------------------------------------
    def _on_setting(self, key: str, state: bool) -> None:
        setattr(self.cfg, key, state)
        self.cfg.save()
        announce(f"{SETTING_LABELS[key]} {'eingeschaltet' if state else 'ausgeschaltet'}.")

    def _model_label(self, name: str) -> str:
        return dict(AVAILABLE_MODELS).get(name, name)

    def _check_model(self, name: str) -> None:
        """Häkchen im Menü auf das Modell setzen, ohne eine Auswahl auszulösen."""
        action = self.model_actions.get(name)
        if action is not None:
            action.blockSignals(True)
            action.setChecked(True)
            action.blockSignals(False)

    def _on_model(self, name: str) -> None:
        """Anderes Modell wählen: prüfen, speichern, altes entladen, neues laden und aufwärmen."""
        old = self.cfg.chat_model
        if name == old:
            return
        if self._ask_task is not None or self._startup_task is not None:
            self._check_model(old)
            announce("Modellwechsel jetzt nicht möglich. Bitte warten, bis die Anfrage fertig ist.")
            return
        try:
            installed = {m.removesuffix(":latest") for m in self.backend.installed_models()}
        except LLMError as exc:
            self._check_model(old)
            announce(f"Modellwechsel nicht möglich: {exc}", dringend=True)
            return
        if name not in installed:
            self._check_model(old)
            announce(f"{self._model_label(name)} ist nicht installiert. Im Terminal: "
                     f"ollama pull {name}. Es bleibt bei {self._model_label(old)}.", dringend=True)
            return
        self.cfg.chat_model = name
        self.cfg.save()
        announce(f"Modell {self._model_label(name)} gewählt. Es wird geladen.")
        self.start_engine(unload=old)

    def _on_tavily_key(self, checked: bool = False) -> None:
        """Schlüssel für die Tavily-Suche eintragen. Leer lassen: DuckDuckGo ohne Schlüssel."""
        key, ok = QInputDialog.getText(
            self, "Tavily-Schlüssel", "Schlüssel für die Internetsuche (leer: DuckDuckGo):",
            QLineEdit.EchoMode.Normal, self.cfg.tavily_key)
        if not ok:
            return
        self.cfg.tavily_key = key.strip()
        self.cfg.save()
        announce("Tavily-Schlüssel gespeichert. Die Suche nutzt Tavily." if self.cfg.tavily_key
                 else "Tavily-Schlüssel entfernt. Die Suche nutzt DuckDuckGo.")

    # ------------------------------------------------------------------
    # Fragen und Antworten
    # ------------------------------------------------------------------
    def _on_ask(self) -> None:
        if self._ask_task is not None or not self.engine_ready:
            return
        text = self.question.edit.toPlainText().strip()
        if not text:
            announce("Bitte eine Frage eingeben.")
            self.question.edit.setFocus()
            return
        context = self.answer.context_text()      # vor dem Speichern lesen: es löscht "geändert"
        self._persist_answer_edits()
        session = self.session

        def work(task: Task):
            return session.ask(text, context, task.cancel_event,
                               on_status=lambda s: task.progress.emit(0.0, s))

        task = Task(work, self)
        task.progress.connect(lambda _fraction, status: self._on_status(status))
        task.result.connect(lambda result, q=text: self._on_answer(q, result))
        task.cancelled.connect(self._ask_cancelled)
        task.error.connect(self._ask_failed)
        task.finished.connect(task.deleteLater)
        self._ask_task = task
        self._last_status = ""
        self._pending_question = text
        self.question.edit.clear()                 # die Frage ist gesendet: das Feld ist wieder frei
        self.question.set_status("Anfrage wird bearbeitet")
        self._update_actions()
        self._update_title()
        announce("Anfrage wird bearbeitet.")
        task.start()

    def _restore_question(self) -> None:
        """Bei Abbruch oder Fehler die Frage zurückgeben, damit nichts verloren geht."""
        if not self.question.edit.toPlainText().strip():
            self.question.edit.setPlainText(self._pending_question)
        self._pending_question = ""

    def _on_status(self, status: str) -> None:
        if status != self._last_status:
            self._last_status = status
            self.question.set_status(status)
            announce(status)

    def _end_ask(self) -> None:
        self._ask_task = None
        self.question.set_status("Bereit")
        self._update_actions()
        self._update_title()

    def _on_answer(self, question: str, result: TurnResult) -> None:
        self._end_ask()
        self._pending_question = ""
        notes = []
        was_doc = self.answer.is_doc
        if self.chat_id is None:
            chat = self.store.create_chat(title_from_question(question), self.new_chat_project)
            self.chat_id = chat.id
            if self._meta:
                self.store.set_attachments(chat.id, self._meta)
            project = self._project_of(chat)
            if project is not None:
                notes.append(f"Der Chat gehört zum Projekt {project.name}.")
        field = self.answer.set_result(result.answer, result.doc_text)
        if result.doc_text is not None:
            self._doc_title = result.doc_title or self._doc_title
            notes.insert(0, "Text geändert." if was_doc else "Text erstellt.")
        else:
            self._doc_title = ""
        self._word_filename = result.word_filename or ""
        self.actions.set_state(has_text=self.answer.is_doc, word_filename=result.word_filename)
        if result.word_filename is not None:
            notes.append("Word-Dokument bereit.")
        exchange = self.store.add_exchange(self.chat_id, question, field, result.answer,
                                           self.answer.is_doc, self._doc_title,
                                           self._word_filename)
        self._current_exchange = exchange
        self.history_panel.add_on_top(exchange)            # neue Frage = neuer Verlaufspunkt
        notes.append("Neuer Eintrag im Verlauf.")
        self.answer.edit.setFocus()
        if self.cfg.beep_on_answer:
            QApplication.beep()
        announce(" ".join(["Antwort fertig.", *notes]))
        self._update_actions()
        self._update_title()

    def _check_pdf(self, checked: bool = False) -> None:
        """PDF technisch prüfen (ohne Sprachmodell, dauert Sekunden). Der Bericht steht in der Antwort."""
        if self._busy_warning() or not self.engine_ready:
            return
        path, _ = QFileDialog.getOpenFileName(self, "PDF prüfen", str(Path.home() / "Documents"),
                                              "PDF-Dateien (*.pdf);;Alle Dateien (*)")
        if not path:
            self.answer.edit.setFocus()
            return
        name = Path(path).name
        question = f"PDF prüfen: {name}"

        def work(task: Task):
            try:
                pages, findings = pdfcheck.check_pdf(path)
            except FileReadError as exc:
                return f"Prüfung von {name} nicht möglich: {exc}"
            return pdfcheck.format_report(name, pages, findings)

        def done(report: str) -> None:
            self.session.turns.append((question, report))          # Rückfragen zum Bericht möglich
            self._on_answer(question, TurnResult(report))

        task = Task(work, self)
        task.result.connect(done)
        task.cancelled.connect(self._ask_cancelled)
        task.error.connect(self._ask_failed)
        task.finished.connect(task.deleteLater)
        self._ask_task = task
        self._pending_question = ""
        self.question.set_status("PDF wird geprüft")
        self._update_actions()
        self._update_title()
        announce(f"PDF {name} wird geprüft.")
        task.start()

    def _ask_cancelled(self) -> None:
        self._end_ask()
        self._restore_question()
        self.question.edit.setFocus()
        announce("Abgebrochen.")

    def _ask_failed(self, message: str) -> None:
        self._end_ask()
        self._restore_question()
        self.question.set_status(f"Fehler: {message}")
        announce(f"Fehler: {message}", dringend=True)
        show_error(self, "Fehler bei der Antwort", message)
        self.question.edit.setFocus()

    def _on_cancel(self) -> None:
        if self._ask_task is not None:
            self._ask_task.cancel()
            self.question.edit.setFocus()

    def _persist_answer_edits(self) -> None:
        """Ihre Änderungen im Antwortfeld gehen nicht verloren: Sie werden im Verlaufseintrag
        gespeichert, bevor eine neue Antwort oder ein anderer Chat das Feld ersetzt."""
        if self.answer.is_modified() and self._current_exchange is not None:
            text = self.answer.text()
            self.store.update_exchange_answer(self._current_exchange.id, text)
            self._current_exchange = dataclasses.replace(self._current_exchange, answer=text)
            self.history_panel.update_entry(self._current_exchange)
        self.answer.mark_saved()

    # ------------------------------------------------------------------
    # Antwort: kopieren, Word
    # ------------------------------------------------------------------
    def _copy_answer(self) -> None:
        if not self.answer.text().strip():
            announce("Es gibt noch keine Antwort zum Kopieren.")
            return
        QGuiApplication.clipboard().setText(self.answer.text())
        announce("Antwort kopiert.")

    def _copy_document(self) -> None:
        if not self.answer.is_doc:
            announce("Es gibt noch keinen Text.")
            return
        QGuiApplication.clipboard().setText(self.answer.document_text())
        announce("Text kopiert.")

    def _save_word(self) -> None:
        text = self.answer.document_text().strip()
        if not text:
            announce("Es gibt noch keinen Text zum Speichern.")
            return
        previous = QApplication.focusWidget()
        docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        base = safe_filename(self._word_filename or self._doc_title)
        path, _ = QFileDialog.getSaveFileName(self, "Word-Dokument speichern",
                                              str(Path(docs) / f"{base}.docx"),
                                              "Word-Dokument (*.docx)")
        if previous is not None:
            previous.setFocus()
        if not path:
            return
        try:
            saved = save_docx(path, self._doc_title or base, text)
        except OSError as exc:
            announce(f"Speichern nicht möglich: {exc}", dringend=True)
            show_error(self, "Speichern nicht möglich",
                       f"Die Datei konnte nicht gespeichert werden. Ist sie in Word geöffnet?\n{exc}")
            return
        announce(f"Word-Dokument gespeichert: {saved.name}.")

    # ------------------------------------------------------------------
    # Dateien und Ordner
    # ------------------------------------------------------------------
    def _save_meta(self) -> None:
        if self.chat_id is not None:
            self.store.set_attachments(self.chat_id, self._meta)

    def _refresh_attachment_list(self) -> None:
        labels = [f"Hinzugefügter Ordner: {m['path']}" if m["type"] == "folder"
                  else f"Hinzugefügte Datei: {Path(m['path']).name}" for m in self._meta]
        self.actions.set_state(attachments=labels)

    def _on_add_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Dateien hinzufügen", str(Path.home() / "Documents"), FILE_FILTER)
        if not paths:
            self.actions.list.setFocus()
            return
        added = 0
        for path in paths:
            if self._attach_file(path, announce_result=True):
                added += 1
        self._save_meta()
        self._refresh_attachment_list()
        self.actions.list.setFocus()
        if len(paths) > 1:
            announce(f"{added} von {len(paths)} Dateien hinzugefügt.")

    def _attach_file(self, path: str, announce_result: bool) -> bool:
        try:
            # Schon geladen, zum Beispiel als Projektdatei: dann nicht noch einmal.
            added = None if self.session.has_file(path) else self.session.add_file(path)
        except FileReadError as exc:
            if announce_result:
                announce(f"{Path(path).name}: {exc}", dringend=True)
            return False
        if not any(m["path"] == str(path) for m in self._meta):
            self._meta.append({"type": "file", "path": str(path)})
        if announce_result:
            announce(added.message() if added else f"{Path(path).name} hinzugefügt.",
                     dringend=bool(added and added.truncated))
        return True

    def _on_add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Ordner hinzufügen",
                                                str(Path.home() / "Documents"))
        if not path:
            self.actions.list.setFocus()
            return
        try:
            root = self.session.folders.grant(path)
        except FolderError as exc:
            announce(str(exc), dringend=True)
            return
        if not any(m["path"] == str(root) for m in self._meta):
            self._meta.append({"type": "folder", "path": str(root)})
        self._save_meta()
        self._refresh_attachment_list()
        count = len(self.session.folders.files())
        self.actions.list.setFocus()
        announce(f"Ordner {root.name} freigegeben, {_plural(count, 'lesbare Datei', 'lesbare Dateien')}.")

    def _remove_attachment(self, index: int) -> None:
        if not 0 <= index < len(self._meta):
            return
        meta = self._meta.pop(index)
        name = Path(meta["path"]).name
        if meta["type"] == "folder":
            self.session.folders.revoke(meta["path"])
        elif meta["path"] not in self._loaded_project_paths:
            self.session.remove_file(meta["path"])                        # Projektdateien bleiben
        self._save_meta()
        self._refresh_attachment_list()
        self.actions.focus_attachments_or_actions(index if self._meta else None)
        announce(f"{name} entfernt. Die Datei selbst bleibt unverändert.")

    def _restore_attachments(self, meta: list[dict]) -> list[str]:
        """Dateien und Ordner eines gespeicherten Chats wieder freigeben. Gibt Fehlendes zurück."""
        missing = []
        for item in meta:
            if item["type"] == "folder":
                try:
                    root = self.session.folders.grant(item["path"])
                    self._meta.append({"type": "folder", "path": str(root)})
                except FolderError:
                    missing.append(item["path"])
            elif not self._attach_file(item["path"], announce_result=False):
                missing.append(item["path"])
        return missing

    # ------------------------------------------------------------------
    # Chats
    # ------------------------------------------------------------------
    def _project_of(self, chat: Chat) -> Project | None:
        return self.store.get_project(chat.project_id) if chat.project_id is not None else None

    def _reset_view(self) -> None:
        self.chat_id = None
        self.new_chat_project = None
        self._current_exchange = None
        self._meta = []
        self._doc_title = ""
        self._word_filename = ""
        self.session.reset()
        self._loaded_project_paths = set()
        self._project_file_notes = []
        self.history_panel.set_entries([])
        self.question.edit.clear()
        self.answer.clear()
        self.actions.set_state(has_text=False, word_filename=None, attachments=[])

    def _busy_warning(self) -> bool:
        if self._ask_task is not None:
            announce("Eine Anfrage läuft noch.")
            return True
        return False

    def _new_chat(self, project_id: int | None = None) -> None:
        if self._busy_warning():
            return
        self._persist_answer_edits()
        self._reset_view()
        self.new_chat_project = project_id
        self._project_file_notes = self._sync_project_files()     # die Dateien des Projekts
        self.question.edit.setFocus()
        project = self.store.get_project(project_id) if project_id is not None else None
        announce(" ".join(["Neuer Chat" + (f" im Projekt {project.name}." if project else "."),
                           *self._project_file_notes]), dringend=bool(self._project_file_notes))
        self._update_title()

    def _open_chat(self, chat_id: int) -> None:
        if self._busy_warning():
            return
        chat = self.store.get_chat(chat_id)
        if chat is None:
            announce("Dieser Chat existiert nicht mehr.", dringend=True)
            return
        self._persist_answer_edits()
        self._reset_view()
        self.chat_id = chat.id
        self._project_file_notes = self._sync_project_files()     # zuerst, sie zählen zum Limit
        exchanges = self.store.exchanges(chat.id)                     # neueste zuerst
        self.session.load([(e.question, e.comment or e.answer) for e in reversed(exchanges)])
        missing = self._restore_attachments(chat.attachments)
        self.history_panel.set_entries(exchanges)
        self._refresh_attachment_list()
        if exchanges:
            self._show_exchange(exchanges[0])
        self.answer.edit.setFocus()
        text = f"Chat geöffnet: {chat.title}, {_plural(len(exchanges), 'Eintrag', 'Einträge')}."
        if missing:
            text += " Nicht mehr vorhanden: " + ", ".join(Path(p).name for p in missing) + "."
        text = " ".join([text, *self._project_file_notes])
        announce(text, dringend=bool(missing or self._project_file_notes))
        self._update_title()

    def _chat_label(self, chat: Chat) -> str:
        return _menu_text(f"{chat.title}, {chat.updated:%d.%m.%Y}")

    def _add_chat_actions(self, menu: QMenu, chats: list[Chat], project_id: int | None) -> list[QAction]:
        """Chats als Einträge. Enter öffnet, die Menütaste zeigt das Kontextmenü."""
        added = []
        for chat in chats:
            action = menu.addAction(self._chat_label(chat))
            action.setData(("chat", chat.id))
            action.triggered.connect(lambda checked=False, cid=chat.id: self._open_chat(cid))
            added.append(action)
        return added

    def _clear_dynamic(self, menu: QMenu, actions: list[QAction]) -> None:
        for action in actions:
            menu.removeAction(action)
            if action.menu() is not None:
                action.menu().deleteLater()
            else:
                action.deleteLater()
        actions.clear()

    def _fill_chats_menu(self) -> None:
        """Chatliste: alle Chats, die in keinem Projekt sind."""
        self._clear_dynamic(self.chats_menu, self._dynamic_chat_actions)
        chats = self.store.chats_without_project(MAX_CHATS_IN_MENU)
        if not chats:
            empty = self.chats_menu.addAction("Noch keine Chats ohne Projekt")
            empty.setEnabled(False)
            self._dynamic_chat_actions.append(empty)
            return
        self._dynamic_chat_actions += self._add_chat_actions(self.chats_menu, chats, None)

    def _fill_projects_menu(self) -> None:
        """Projekte: Enter öffnet die Chatliste des Projekts, oben steht 'Neuer Chat'."""
        self._clear_dynamic(self.projects_menu, self._dynamic_project_actions)
        projects = self.store.projects()
        if not projects:
            empty = self.projects_menu.addAction("Noch keine Projekte vorhanden")
            empty.setEnabled(False)
            self._dynamic_project_actions.append(empty)
            return
        for project in projects:
            sub = self._context_menu(_menu_text(project.name))
            new = sub.addAction("Neuer Chat")
            new.triggered.connect(lambda checked=False, pid=project.id: self._new_chat(pid))
            # Projektdateien: eine Ebene unter dem Projekt, zwischen Neuer Chat und den Chats
            files = self._context_menu("Projekt&dateien")
            files.aboutToShow.connect(
                lambda menu=files, pid=project.id: self._fill_project_files_menu(menu, pid))
            sub.addMenu(files)
            self._add_chat_actions(sub, self.store.chats_in_project(project.id), project.id)
            action = self.projects_menu.addMenu(sub)
            action.setData(("project", project.id))
            self._dynamic_project_actions.append(action)

    # -- Kontextmenü -----------------------------------------------------------------
    def _picker(self, menu: QMenu, title: str, projects: list[Project], choose) -> None:
        """Untermenü mit der Projektliste. Enter wählt ein Projekt."""
        sub = AccessibleMenu(title, menu)
        menu.addMenu(sub)
        if not projects:
            sub.addAction("Kein passendes Projekt vorhanden").setEnabled(False)
            return
        for project in projects:
            sub.addAction(_menu_text(project.name),
                          lambda checked=False, pid=project.id: choose(pid))

    def _build_context_menu(self, data) -> QMenu | None:
        kind, ident = data
        menu = AccessibleMenu("Kontextmenü", self)
        if kind == "project":
            menu.addAction("Projekt entfernen", lambda checked=False: self._remove_project(ident))
            return menu
        if kind == "project_file":
            menu.addAction("Datei entfernen",
                           lambda checked=False: self._remove_project_file(ident))
            return menu
        chat = self.store.get_chat(ident) if kind == "chat" else None
        if chat is None:
            return None
        others = [p for p in self.store.projects() if p.id != chat.project_id]
        if chat.project_id is None:
            self._picker(menu, "In Projekt verschieben", others,
                         lambda pid: self._move_chat(chat.id, pid))
        else:
            self._picker(menu, "In anderes Projekt verschieben", others,
                         lambda pid: self._move_chat(chat.id, pid))
            self._picker(menu, "In anderes Projekt kopieren", others,
                         lambda pid: self._copy_chat(chat.id, pid))
            menu.addAction("Aus dem Projekt in die Chatliste",
                           lambda checked=False: self._move_chat(chat.id, None))
        menu.addAction("Chat entfernen", lambda checked=False: self._remove_chat(chat.id))
        return menu

    def _show_context_menu(self, action: QAction, position) -> None:
        log.info("Kontextmenü angefordert: %s", action.data())
        menu = self._build_context_menu(action.data())
        if menu is None:
            return
        self._exec_menu(menu, position)
        close_all_popups()                        # danach auch die darunterliegenden Menüs zu
        self._leave_menu_bar()

    def _remember_focus(self, old, new) -> None:
        """Merkt sich, was den Fokus hatte, bevor die Menüleiste ihn bekam (Alt oder Alt+Buchstabe)."""
        if isinstance(new, QMenuBar) and old is not None and not isinstance(old, QMenuBar):
            self._focus_before_menu_bar = old

    def _leave_menu_bar(self) -> None:
        """Nach dem Schließen der Menüs steht der Fokus sonst weiter in der Menüleiste."""
        if not isinstance(QApplication.focusWidget(), QMenuBar):
            return
        target = self._focus_before_menu_bar
        if target is None or not target.isVisible():
            target = self.question.edit
        target.setFocus()

    def _exec_menu(self, menu: QMenu, position) -> None:
        # Der erste Eintrag ist sofort markiert: Ein Screenreader liest ihn vor, sonst wirkt das
        # geöffnete Menü stumm.
        menu.aboutToShow.connect(lambda: QTimer.singleShot(0, lambda: _select_first(menu)))
        menu.exec(position)

    def _move_chat(self, chat_id: int, project_id: int | None) -> None:
        chat = self.store.get_chat(chat_id)
        if chat is None:
            return
        self.store.set_chat_project(chat_id, project_id)
        if project_id is None:
            text = f"Chat {chat.title} ist jetzt in der Chatliste."
        else:
            text = (f"Chat {chat.title} in das Projekt {self.store.get_project(project_id).name} "
                    "verschoben.")
        if chat_id == self.chat_id:                 # der offene Chat bekommt die Dateien des neuen Projekts
            notes = self._sync_project_files()
            self._project_file_notes = notes
            text = " ".join([text, *notes])
        announce(text, dringend=bool(chat_id == self.chat_id and self._project_file_notes))
        self._update_title()

    def _copy_chat(self, chat_id: int, project_id: int) -> None:
        chat = self.store.get_chat(chat_id)
        if chat is None:
            return
        self.store.copy_chat(chat_id, project_id)
        announce(f"Chat {chat.title} in das Projekt {self.store.get_project(project_id).name} "
                 "kopiert.")

    def _remove_chat(self, chat_id: int) -> None:
        chat = self.store.get_chat(chat_id)
        if chat is None or self._busy_warning():
            return
        if not confirm(self, "Chat entfernen", f"Den Chat \"{chat.title}\" mit allen Einträgen "
                       "entfernen? Hinzugefügte Dateien bleiben unverändert.",
                       yes="Entfernen", no="Abbrechen", default_yes=True):
            return
        self.store.delete_chat(chat_id)
        if chat_id == self.chat_id:
            self._reset_view()
            self.question.edit.setFocus()
        announce(f"Chat {chat.title} entfernt.")
        self._update_title()

    # ------------------------------------------------------------------
    # Verlauf
    # ------------------------------------------------------------------
    def _show_exchange(self, entry: Exchange) -> None:
        self.answer.load(entry.answer, entry.comment, entry.is_doc)
        self._current_exchange = entry
        self._doc_title = entry.doc_title
        self._word_filename = entry.word_filename
        self.actions.set_state(has_text=entry.is_doc,
                               word_filename=entry.word_filename if entry.word_filename else None)

    def _load_exchange(self, entry: Exchange) -> None:
        self._persist_answer_edits()
        fresh = next((e for e in self.history_panel.entries() if e.id == entry.id), entry)
        self._show_exchange(fresh)
        self.answer.edit.setFocus()
        question = " ".join(fresh.question.split())
        if len(question) > 100:
            question = question[:100] + " …"
        announce(f"Verlauf geladen: {question}, vom {fresh.created:%d.%m.%Y, %H:%M}.")

    # ------------------------------------------------------------------
    # Projekte
    # ------------------------------------------------------------------
    def _new_project(self) -> None:
        name, ok = QInputDialog.getText(self, "Neues Projekt", "Name des Projekts:")
        if not ok or not name.strip():
            self.question.edit.setFocus()
            return
        project = self.store.add_project(name)
        self.question.edit.setFocus()
        announce(f"Projekt {project.name} erstellt.")

    def _remove_project(self, project_id: int) -> None:
        project = self.store.get_project(project_id)
        if project is None:
            return
        count = len(self.store.chats_in_project(project_id))
        if not confirm(self, "Projekt entfernen",
                       f"Das Projekt \"{project.name}\" entfernen? Die {_plural(count, 'Chat', 'Chats')} "
                       "darin bleiben erhalten und stehen danach in der Chatliste.",
                       yes="Entfernen", no="Abbrechen", default_yes=True):
            return
        self.store.delete_project(project_id)              # mit den Projektdateien (nur die Einträge)
        if self.new_chat_project == project_id:
            self.new_chat_project = None
        self._project_file_notes = self._sync_project_files()
        announce(f"Projekt {project.name} entfernt. Die Chats stehen jetzt in der Chatliste.")
        self._update_title()

    # ------------------------------------------------------------------
    # Projektdateien: gehören zu einem Projekt, alle Chats darin können sie lesen
    # ------------------------------------------------------------------
    def _current_project_id(self) -> int | None:
        """Projekt des offenen Chats, oder des neuen Chats. None: Chat ohne Projekt."""
        if self.chat_id is not None:
            chat = self.store.get_chat(self.chat_id)
            return chat.project_id if chat else None
        return self.new_chat_project

    def _fill_project_files_menu(self, menu: QMenu, project_id: int) -> None:
        """Oben 'Datei hochladen', darunter die Dateien. Menütaste auf einer Datei: Entfernen."""
        menu.clear()
        upload = menu.addAction("Datei hochladen …")
        upload.triggered.connect(lambda checked=False: self._upload_project_files(project_id))
        files = self.store.project_files(project_id)
        if not files:
            menu.addAction("Noch keine Projektdateien").setEnabled(False)
            return
        for file in files:
            action = menu.addAction(_menu_text(file.name))
            action.setData(("project_file", file.id))
            action.triggered.connect(
                lambda checked=False, f=file: announce(f"Projektdatei {f.name}, Ordner {Path(f.path).parent}."))

    def _sync_project_files(self) -> list[str]:
        """Die Projektdateien des aktuellen Chats laden, die des früheren Standes entfernen.
        Gibt Hinweise zurück (nicht lesbar, gekürzt)."""
        own = {m["path"] for m in self._meta}                        # im Chat selbst hinzugefügt
        for path in self._loaded_project_paths - own:
            self.session.remove_file(path)
        self._loaded_project_paths = set()
        project_id = self._current_project_id()
        notes = []
        for file in self.store.project_files(project_id) if project_id is not None else []:
            if self.session.has_file(file.path):
                self._loaded_project_paths.add(file.path)             # schon da, zählt auch als Projektdatei
                continue
            try:
                added = self.session.add_file(file.path)
            except FileReadError:
                notes.append(f"Projektdatei {file.name} nicht lesbar.")
                continue
            self._loaded_project_paths.add(file.path)
            if added.truncated:
                notes.append(f"Projektdatei {file.name} wurde gekürzt.")
        return notes

    def _upload_project_files(self, project_id: int) -> None:
        project = self.store.get_project(project_id)
        if project is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, f"Projektdateien für {project.name} hochladen", str(Path.home() / "Documents"),
            FILE_FILTER)
        added = []
        for path in paths:
            try:
                name = pdfs.check_readable(path)
            except FileReadError as exc:
                announce(f"{Path(path).name}: {exc}", dringend=True)
                continue
            self.store.add_project_file(project_id, str(path))
            added.append(name)
        if added:
            notes = []
            if project_id == self._current_project_id():        # der offene Chat gehört dazu
                notes = self._project_file_notes = self._sync_project_files()
            text = (f"{added[0]} zu den Projektdateien von {project.name} hinzugefügt."
                    if len(added) == 1 else
                    f"{len(added)} Dateien zu den Projektdateien von {project.name} hinzugefügt.")
            announce(" ".join([text, "Alle Chats im Projekt können sie lesen.", *notes]),
                     dringend=bool(notes))
        self.question.edit.setFocus()

    def _remove_project_file(self, file_id: int) -> None:
        file = self.store.get_project_file(file_id)
        if file is None:
            return
        if not confirm(self, "Datei entfernen",
                       f"Die Datei \"{file.name}\" aus den Projektdateien entfernen? Die Datei "
                       "selbst bleibt unverändert.",
                       yes="Entfernen", no="Abbrechen", default_yes=True):
            return
        self.store.remove_project_file(file_id)
        if file.project_id == self._current_project_id():
            self._project_file_notes = self._sync_project_files()
        announce(f"{file.name} aus den Projektdateien entfernt. Die Datei selbst bleibt unverändert.")

    # ------------------------------------------------------------------
    # Fokus und Navigation
    # ------------------------------------------------------------------
    def initial_focus(self) -> None:
        self.question.edit.setFocus()

    def _focus_question(self) -> None:
        self.question.edit.setFocus()

    def _focus_answer(self) -> None:
        self.answer.edit.setFocus()

    def _focus_actions(self) -> None:
        self.actions.list.setFocus()

    def _focus_history(self) -> None:
        self.history_panel.list.setFocus()      # auch leer: der Screenreader sagt "leer"

    def _current_area(self) -> int:
        widget = QApplication.focusWidget()
        for i, panel in enumerate(self._areas):
            if widget is not None and (widget is panel or panel.isAncestorOf(widget)):
                return i
        return -1

    def _cycle_area(self, step: int) -> None:
        focus = (self._focus_question, self._focus_answer, self._focus_actions,
                 self._focus_history)
        current = self._current_area()
        focus[(max(current, 0) + step) % len(focus)]()

    # ------------------------------------------------------------------
    # Schrift, Titel, Hilfe
    # ------------------------------------------------------------------
    def _apply_font(self) -> None:
        font = QApplication.font()
        font.setPointSize(self.cfg.font_size)
        QApplication.setFont(font)
        self.question.update_height()
        self.answer.update_height()

    def _change_font(self, step: int) -> None:
        size = max(MIN_FONT, min(MAX_FONT, self.cfg.font_size + step))
        if size == self.cfg.font_size:
            announce(f"Schriftgröße {size} Punkt ist die Grenze.")
            return
        self.cfg.font_size = size
        self.cfg.save()
        self._apply_font()
        announce(f"Schriftgröße {size} Punkt.")

    def _show_shortcuts(self) -> None:
        previous = QApplication.focusWidget()
        ShortcutsDialog(self).exec()
        if previous is not None:
            previous.setFocus()

    def _update_actions(self) -> None:
        self.act_send.setEnabled(self.engine_ready and self._ask_task is None)
        self.act_cancel.setEnabled(self._ask_task is not None)
        for action in self.model_actions.values():
            action.setEnabled(self.engine_ready and self._ask_task is None)

    def _update_title(self) -> None:
        chat: Chat | None = self.store.get_chat(self.chat_id) if self.chat_id else None
        parts = [chat.title if chat else "Neuer Chat"]
        project_id = chat.project_id if chat else self.new_chat_project
        project = self.store.get_project(project_id) if project_id is not None else None
        if project is not None:
            parts.append(f"Projekt {project.name}")
        if not self.engine_ready:
            parts.append("Modell wird geladen")
        elif self._ask_task is not None:
            parts.append("Anfrage läuft")
        else:
            parts.append("bereit")
        self.setWindowTitle(f"{TITLE}: " + ", ".join(parts))

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        self._persist_answer_edits()
        for task in (self._ask_task, self._startup_task):
            if task is not None:
                task.cancel()
                task.wait(5000)
        self.backend.stop()
        self.store.close()
        event.accept()
