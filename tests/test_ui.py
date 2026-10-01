"""Tests der Oberfläche nach der Beschreibung: Frage, Antwort, Aktionen, Verlauf, Menüs für
Projekte, Chatliste, Einstellungen und Datei, Kontextmenüs."""
import re

import pytest
from docx import Document
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QContextMenuEvent, QGuiApplication
from PySide6.QtWidgets import (QApplication, QFileDialog, QGroupBox, QInputDialog, QLabel,
                               QListWidget, QMenu, QMenuBar, QMessageBox, QPlainTextEdit, QPushButton,
                               QWidget)

from tests.conftest import FakeBackend, content, tool_call
from tests.test_docs import defective_pdf, make_image, make_pdf, make_scan
from ui import actions_panel as ap
from ui.announcer import announcer
from ui.main_window import MainWindow, _select_first
from ui.menus import ContextMenu

LETTER = ('Ich habe das Anschreiben erstellt.\n<dokument titel="Bewerbung">\nSehr geehrte Damen '
          'und Herren,\n\nhiermit bewerbe ich mich.\n</dokument>')
LETTER_TEXT = "Sehr geehrte Damen und Herren,\n\nhiermit bewerbe ich mich."
COMMENT = "Ich habe das Anschreiben erstellt."


@pytest.fixture
def make_window(qtbot, cfg, store, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)     # nie blockieren
    cfg.beep_on_answer = False
    cfg.web_search = False

    def factory(script=None, delay: float = 0.0, start: bool = True) -> MainWindow:
        announcer.history.clear()
        window = MainWindow(cfg, FakeBackend(cfg, script, delay), store)
        qtbot.addWidget(window)
        window.show()
        qtbot.waitExposed(window)
        window.activateWindow()
        window.initial_focus()
        if start:
            window.start_engine()
            qtbot.waitUntil(lambda: window.engine_ready, timeout=5000)
        return window

    return factory


def said(text_part: str) -> bool:
    return any(text_part in text for text, _ in announcer.history)


def ask(window, qtbot, text="Eine Frage"):
    window.question.edit.setFocus()
    window.question.edit.setPlainText(text)
    count = window.history_panel.count()
    qtbot.keyClick(window.question.edit, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.history_panel.count() == count + 1, timeout=5000)


def edit_answer(window, text):
    """Wie eine Person: alles markieren und neuen Text einfügen (das gilt als Änderung)."""
    window.answer.edit.selectAll()
    window.answer.edit.insertPlainText(text)


def focus_now():
    return QApplication.focusWidget()


def top_menu(window, title) -> QMenu:
    return next(a.menu() for a in window.menuBar().actions() if a.text().replace("&", "") == title)


def texts(menu) -> list[str]:
    return [a.text().replace("&", "") for a in menu.actions() if not a.isSeparator()]


def find(menu, part) -> QAction:
    for action in menu.actions():
        if part in action.text().replace("&", ""):
            return action
    raise AssertionError(f"kein Eintrag {part!r} in {texts(menu)}")


def projects_menu(window):
    window._fill_projects_menu()
    return window.projects_menu


def chats_menu(window):
    window._fill_chats_menu()
    return window.chats_menu


def project_chat_list(window, project_name) -> QMenu:
    return find(projects_menu(window), project_name).menu()


def create_project(window, monkeypatch, name="Bewerbungen"):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: (name, True))
    window._new_project()


def context_menu(window, action) -> QMenu:
    return window._build_context_menu(action.data())


def choose(menu, *path):
    """Durch Untermenüs gehen und den letzten Eintrag auslösen (wie Enter)."""
    for part in path[:-1]:
        menu = find(menu, part).menu()
    find(menu, path[-1]).trigger()


def action_row(window, key_text):
    lst = window.actions.list
    for r in range(lst.count()):
        if lst.item(r).text().startswith(key_text):
            return r
    raise AssertionError(f"kein Aktionseintrag {key_text!r}: {window.actions.texts()}")


def press_enter_on_action(window, qtbot, key_text):
    lst = window.actions.list
    lst.setFocus()
    lst.setCurrentRow(action_row(window, key_text))
    qtbot.keyClick(lst, Qt.Key.Key_Return)


# -- Reihenfolge: Frage, Antwort, Aktionen, Verlauf, wieder Frage -------------------------------
def test_tab_goes_question_answer_actions_history_and_back_to_question(make_window):
    window = make_window()
    window.question.edit.setFocus()
    visited = []
    for _ in range(5):
        visited.append(focus_now())
        window.focusNextChild()
    assert visited == [window.question.edit, window.answer.edit, window.actions.list,
                       window.history_panel.list, window.question.edit]


def test_shift_tab_goes_backwards_and_from_question_to_history(make_window):
    window = make_window()
    window.question.edit.setFocus()
    window.focusPreviousChild()
    assert focus_now() is window.history_panel.list
    window.focusPreviousChild()
    assert focus_now() is window.actions.list


def test_tab_from_history_lands_in_question(make_window):
    window = make_window()
    window.history_panel.list.setFocus()
    window.focusNextChild()
    assert focus_now() is window.question.edit


def test_layout_has_exactly_four_tab_stops(make_window):
    window = make_window()
    stops = [w for w in window.findChildren(QWidget)
             if w.focusPolicy() & Qt.FocusPolicy.TabFocus and w.isVisible() and w.isEnabled()
             and isinstance(w, (QPlainTextEdit, QListWidget, QPushButton))]
    assert set(stops) == {window.question.edit, window.answer.edit, window.actions.list,
                          window.history_panel.list}


def test_answer_field_is_tall_multiline_editable_and_navigable(make_window, qtbot):
    window = make_window()
    edit = window.answer.edit
    assert not edit.isReadOnly()
    line = edit.fontMetrics().lineSpacing()
    assert edit.minimumHeight() >= line * 10 and edit.height() >= line * 10
    edit.setFocus()
    qtbot.keyClicks(edit, "Zeile eins")
    qtbot.keyClick(edit, Qt.Key.Key_Return)
    qtbot.keyClicks(edit, "Zeile zwei")
    qtbot.keyClick(edit, Qt.Key.Key_Up)
    assert edit.toPlainText() == "Zeile eins\nZeile zwei"
    assert edit.textCursor().blockNumber() == 0                       # Pfeiltasten bewegen den Cursor


def test_answer_field_shows_reply_all_at_once_with_cursor_at_start(make_window, qtbot):
    window = make_window([content("Zeile eins.\nZeile zwei.\nZeile drei.")])
    ask(window, qtbot)
    assert window.answer.text() == "Zeile eins.\nZeile zwei.\nZeile drei."
    assert window.answer.edit.textCursor().position() == 0
    assert focus_now() is window.answer.edit


# -- Namen, Kürzel, Menüleiste ---------------------------------------------------------------
def test_every_control_has_accessible_name(make_window):
    window = make_window()
    controls = [w for kind in (QListWidget, QPlainTextEdit) for w in window.findChildren(kind)]
    controls.append(window.question.status)
    assert len(controls) == 5
    for widget in controls:
        assert widget.accessibleName(), f"{type(widget).__name__} ohne Namen: {widget}"
    assert window.findChildren(QGroupBox) == []          # keine Gruppen mehr


def test_no_widget_has_an_accessible_description(make_window):
    """Braillezeile: nur Name und Rolle, keine Beschreibung und keine Tastenkürzel an Feldern.
    Die Tastenkürzel stehen in den Menüs."""
    window = make_window()
    for widget in window.findChildren(QWidget):
        assert widget.accessibleDescription() == "", \
            f"{widget.accessibleName()}: {widget.accessibleDescription()!r}"
    names = {w.accessibleName() for w in window.findChildren(QWidget) if w.accessibleName()}
    assert {"Ihre Frage", "Antwort", "Aktionen", "Verlauf"} <= names


def test_menu_entries_keep_their_shortcuts(make_window):
    window = make_window()
    file_menu = top_menu(window, "Datei")
    assert find(file_menu, "Datei hinzufügen").shortcut().toString() == "Ctrl+O"
    assert find(file_menu, "Ordner hinzufügen").shortcut().toString() == "Ctrl+Shift+O"
    assert find(file_menu, "Word-Dokument").shortcut().toString() == "Ctrl+S"
    assert find(top_menu(window, "Chatliste"), "Neuer Chat").shortcut().toString() == "Ctrl+N"


def test_announcements_do_not_explain_keys(make_window, qtbot):
    window = make_window([content("A1")])
    window.question.edit.setPlainText("Frage")
    window._on_ask()
    window._new_chat(None)                            # während der Anfrage: gesperrt
    window._copy_document()
    qtbot.waitUntil(lambda: said("Antwort fertig."), timeout=5000)
    for text, _ in announcer.history:
        assert not re.search(r"\b(Tab|Enter|Escape|Esc|Strg|Menü)\b", text), text


def test_fields_report_no_shortcut_to_screen_readers(make_window):
    """Auf der Braillezeile soll bei Feldern und Listen kein Tastenkürzel stehen (auch nicht das
    Alt-Kürzel einer Beschriftung). Die Kürzel stehen nur in den Menüs."""
    from PySide6.QtGui import QAccessible
    window = make_window()
    for widget in (window.question.edit, window.answer.edit, window.actions.list,
                   window.history_panel.list):
        interface = QAccessible.queryAccessibleInterface(widget)
        assert interface.text(QAccessible.Text.Accelerator) == "", widget.accessibleName()
        assert interface.text(QAccessible.Text.Description) == "", widget.accessibleName()
    for label in window.findChildren(QLabel):
        assert "&" not in label.text(), label.text()


def test_menu_bar_mnemonics_are_unique(make_window):
    window = make_window()
    seen: dict[str, str] = {}
    for action in window.menuBar().actions():
        match = re.search(r"&(\w)", action.text())
        assert match, f"Menü ohne Alt-Kürzel: {action.text()}"
        key = match.group(1).lower()
        assert key not in seen, f"Alt+{key} doppelt: {action.text()} und {seen[key]}"
        seen[key] = action.text()


def test_menu_bar_order_matches_the_description(make_window):
    titles = [a.text().replace("&", "") for a in make_window().menuBar().actions()]
    assert titles == ["Projekte", "Chatliste", "Einstellungen", "Datei", "Ansicht", "Hilfe"]


def test_static_menu_mnemonics_are_unique_within_each_menu(make_window):
    window = make_window()
    for top in window.menuBar().actions():
        keys = [re.search(r"&(\w)", a.text()).group(1).lower()
                for a in top.menu().actions() if not a.isSeparator() and "&" in a.text()]
        assert len(keys) == len(set(keys)), top.text()


def test_projects_menu_starts_with_new_project_and_chat_list_with_new_chat(make_window):
    window = make_window()
    assert texts(top_menu(window, "Projekte"))[0] == "Neues Projekt …"
    assert texts(top_menu(window, "Chatliste"))[0] == "Neuer Chat"


def test_file_menu_keeps_files_and_word(make_window):
    entries = texts(top_menu(make_window(), "Datei"))
    assert entries == ["Datei hinzufügen …", "Ordner hinzufügen …",
                       "Text als Word-Dokument speichern …", "PDF prüfen …", "Beenden"]


# -- Einstellungen mit Häkchen ------------------------------------------------------------------
def test_settings_menu_has_three_checkable_entries_with_state(make_window, cfg):
    cfg.thinking = True
    window = make_window()
    entries = {a.text().replace("&", ""): a for a in top_menu(window, "Einstellungen").actions()
               if not a.isSeparator()}
    assert list(entries) == ["Lange Antworten", "Nachdenken", "Internetrecherche", "Modell",
                             "Tavily-Schlüssel …"]
    assert [a.isCheckable() for a in entries.values()] == [True, True, True, False, False]
    assert entries["Nachdenken"].isChecked()
    assert not entries["Lange Antworten"].isChecked() and not entries["Internetrecherche"].isChecked()


# -- Modellwahl ----------------------------------------------------------------------------------
def test_model_menu_offers_both_models_with_the_current_one_checked(make_window):
    window = make_window()
    menu = find(top_menu(window, "Einstellungen"), "Modell").menu()
    assert texts(menu) == ["Gemma 4 (12b)", "Qwen 2.5 VL (7b)"]
    assert [a.isChecked() for a in menu.actions()] == [True, False]
    assert menu.accessibleName() == "Modell"


def test_custom_model_from_config_is_listed_and_checked(make_window, cfg):
    cfg.chat_model = "eigenes:1b"
    window = make_window()
    menu = find(top_menu(window, "Einstellungen"), "Modell").menu()
    assert texts(menu)[0] == "eigenes:1b" and menu.actions()[0].isChecked()


def test_switching_model_saves_unloads_old_and_warms_new(make_window, cfg, qtbot):
    from core.config import Config
    window = make_window()
    window.backend.installed = ["gemma4:12b", "qwen2.5vl:7b"]
    window.model_actions["qwen2.5vl:7b"].trigger()
    qtbot.waitUntil(lambda: window.engine_ready, timeout=5000)
    assert cfg.chat_model == "qwen2.5vl:7b" and Config.load().chat_model == "qwen2.5vl:7b"
    assert window.backend.unloaded == ["gemma4:12b"]
    assert window.backend.warmed[-1] == "qwen2.5vl:7b"
    assert said("Modell Qwen 2.5 VL (7b) gewählt") and said("Bereit.")
    assert window.model_actions["qwen2.5vl:7b"].isChecked()
    assert not window.model_actions["gemma4:12b"].isChecked()


def test_switching_to_missing_model_is_refused_and_keeps_the_old_one(make_window, cfg):
    window = make_window()
    window.backend.installed = ["gemma4:12b"]
    window.model_actions["qwen2.5vl:7b"].trigger()
    assert cfg.chat_model == "gemma4:12b" and window.engine_ready
    assert said("nicht installiert") and said("ollama pull qwen2.5vl:7b")
    assert window.model_actions["gemma4:12b"].isChecked()
    assert window.backend.unloaded == []


def test_model_cannot_be_switched_while_a_question_runs(make_window, cfg, qtbot):
    window = make_window([content("Langsam.")], delay=0.4)
    window.backend.installed = ["gemma4:12b", "qwen2.5vl:7b"]
    window.question.edit.setPlainText("Frage")
    qtbot.keyClick(window.question.edit, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window._ask_task is not None, timeout=2000)
    assert not any(a.isEnabled() for a in window.model_actions.values())
    window._on_model("qwen2.5vl:7b")                    # trotzdem aufgerufen: wird abgewiesen
    assert cfg.chat_model == "gemma4:12b" and said("jetzt nicht möglich")
    qtbot.waitUntil(lambda: window._ask_task is None, timeout=5000)
    assert all(a.isEnabled() for a in window.model_actions.values())


def test_model_without_tools_says_so_and_gets_no_tools_or_search_instruction(make_window, cfg,
                                                                            qtbot):
    cfg.web_search, cfg.thinking = True, True
    window = make_window([content("Aus dem Gedächtnis.")])
    window.backend.caps = {"completion", "vision"}
    ask(window, qtbot, "Wer ist Bundeskanzler?")
    call = window.backend.calls[0]
    assert call["tools"] is None and call["think"] is False
    assert "IMMER zuerst suchen" not in call["messages"][0]["content"]
    assert said("Dieses Modell kann nicht im Internet suchen und nicht nachdenken.")


def test_ready_message_after_switch_names_the_limits(make_window, cfg, qtbot):
    cfg.web_search = True
    window = make_window()
    window.backend.installed = ["gemma4:12b", "qwen2.5vl:7b"]
    window.backend.caps = {"completion", "vision"}
    window.model_actions["qwen2.5vl:7b"].trigger()
    qtbot.waitUntil(lambda: window.engine_ready, timeout=5000)
    assert said("Dieses Modell kann nicht im Internet suchen.")


def test_tavily_key_is_saved_announced_and_used_by_the_search(make_window, cfg, monkeypatch):
    from core.config import Config
    window = make_window()
    asked = {}

    def get_text(parent, title, label, echo, text):
        asked.update(title=title, text=text)
        return " tvly-abc ", True
    monkeypatch.setattr(QInputDialog, "getText", get_text)
    window.act_tavily.trigger()
    assert asked == {"title": "Tavily-Schlüssel", "text": ""}
    assert cfg.tavily_key == "tvly-abc" and Config.load().tavily_key == "tvly-abc"
    assert said("Tavily-Schlüssel gespeichert. Die Suche nutzt Tavily.")
    assert window.session.toolbox._search.key() == "tvly-abc"      # wirkt sofort

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", True))
    window.act_tavily.trigger()
    assert cfg.tavily_key == "" and said("Tavily-Schlüssel entfernt. Die Suche nutzt DuckDuckGo.")

    cfg.tavily_key = "bleibt"
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("anderer", False))
    window.act_tavily.trigger()
    assert cfg.tavily_key == "bleibt"                              # Abbrechen ändert nichts


def test_toggling_setting_saves_announces_and_reaches_model(make_window, cfg, qtbot):
    from core.config import Config
    window = make_window([content("Erste."), content("Zweite.")])
    ask(window, qtbot, "Eins")
    first = window.session.backend.calls[0]
    assert first["think"] is False and first["tools"] is None
    for key in ("thinking", "web_search", "long_answers"):
        window.setting_actions[key].trigger()
    assert said("Nachdenken eingeschaltet.") and said("Internetrecherche eingeschaltet.")
    assert Config.load().thinking is True and Config.load().long_answers is True
    ask(window, qtbot, "Zwei")
    second = window.session.backend.calls[1]
    assert second["think"] is True and second["tools"] and second["max_tokens"] > first["max_tokens"]
    window.setting_actions["thinking"].trigger()
    assert said("Nachdenken ausgeschaltet.") and cfg.thinking is False


# -- Frage: Enter sendet und leert -------------------------------------------------------------
def test_startup_focus_and_title(make_window):
    window = make_window()
    assert focus_now() is window.question.edit
    assert said("Bereit. GPU: Testgerät")
    assert window.windowTitle() == "Chatbot für Text: Neuer Chat, bereit"


def test_enter_sends_and_empties_the_question_field(make_window, qtbot):
    window = make_window([content("Antwort.")], delay=0.2)
    window.question.edit.setFocus()
    window.question.edit.setPlainText("Wie spät ist es?")
    qtbot.keyClick(window.question.edit, Qt.Key.Key_Return)
    assert window.question.edit.toPlainText() == ""              # sofort geleert
    assert said("Anfrage wird bearbeitet.")
    qtbot.waitUntil(lambda: said("Antwort fertig."), timeout=5000)
    assert window.question.edit.toPlainText() == ""
    assert focus_now() is window.answer.edit


def test_cancel_returns_the_question_and_creates_no_history(make_window, qtbot, store):
    window = make_window(delay=1.0)
    window.question.edit.setFocus()
    window.question.edit.setPlainText("Lange Frage")
    window._on_ask()
    assert window.question.edit.toPlainText() == ""
    qtbot.waitUntil(lambda: window.act_cancel.isEnabled(), timeout=2000)
    window.act_cancel.trigger()
    qtbot.waitUntil(lambda: said("Abgebrochen."), timeout=5000)
    assert window.question.edit.toPlainText() == "Lange Frage"
    assert focus_now() is window.question.edit
    assert window.history_panel.count() == 0 and store.chats() == []


def test_error_returns_the_question_and_is_urgent(make_window, qtbot, monkeypatch):
    window = make_window()

    def broken(*a, **k):
        from core.llm import LLMError
        raise LLMError("Der Modellserver (Ollama) ist nicht erreichbar.")
        yield
    monkeypatch.setattr(window.backend, "chat_stream", broken)
    window.question.edit.setPlainText("Frage")
    window._on_ask()
    qtbot.waitUntil(lambda: window._ask_task is None, timeout=5000)
    assert any(urgent and "nicht erreichbar" in text for text, urgent in announcer.history)
    assert window.question.edit.toPlainText() == "Frage" and focus_now() is window.question.edit


def test_shift_enter_makes_newline_and_does_not_send(make_window, qtbot):
    window = make_window()
    edit = window.question.edit
    edit.setFocus()
    qtbot.keyClicks(edit, "Zeile eins")
    qtbot.keyClick(edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    qtbot.keyClicks(edit, "Zeile zwei")
    assert edit.toPlainText() == "Zeile eins\nZeile zwei"
    assert not said("Anfrage wird bearbeitet.")


def test_empty_question_is_refused(make_window):
    window = make_window()
    window._on_ask()
    assert said("Bitte eine Frage eingeben.") and focus_now() is window.question.edit


def test_double_submit_is_ignored(make_window, qtbot):
    window = make_window([content("A")], delay=0.3)
    window.question.edit.setPlainText("Frage")
    window._on_ask()
    window.question.edit.setPlainText("Zweite")
    window._on_ask()
    assert sum(1 for t, _ in announcer.history if t == "Anfrage wird bearbeitet.") == 1
    qtbot.waitUntil(lambda: said("Antwort fertig."), timeout=5000)
    assert window.history_panel.count() == 1


def test_web_search_progress_is_announced(make_window, qtbot, cfg):
    cfg.web_search = True
    window = make_window([tool_call("internet_suche", anfrage="Wetter"), content("Sonnig.")])
    window.session.toolbox._search = lambda q: [{"title": "T", "url": "https://w.example/a",
                                                 "snippet": "s"}]
    ask(window, qtbot, "Wetter?")
    assert said("Internetrecherche: Wetter")
    assert "Quellen aus dem Internet:\n- https://w.example/a" in window.answer.text()


# -- Aktionen: Liste, Enter führt aus ------------------------------------------------------------
def test_actions_list_has_the_three_basic_entries(make_window):
    window = make_window()
    assert window.actions.texts() == ["Antwort kopieren", "Datei hinzufügen", "Ordner hinzufügen"]


def test_enter_on_copy_answer_copies(make_window, qtbot):
    window = make_window([content("Kopiere mich.")])
    ask(window, qtbot)
    press_enter_on_action(window, qtbot, "Antwort kopieren")
    assert QGuiApplication.clipboard().text() == "Kopiere mich." and said("Antwort kopiert.")


def test_text_entries_appear_only_after_a_text_and_word_only_on_request(make_window, qtbot,
                                                                        monkeypatch, tmp_path):
    window = make_window([content(LETTER), content(LETTER + '\n<word_dokument dateiname="Bewerbung"/>')])
    ask(window, qtbot, "Schreibe ein Anschreiben")
    assert window.answer.text() == COMMENT + "\n\n" + LETTER_TEXT and window.answer.is_doc
    assert window.actions.texts() == ["Antwort kopieren", "Text kopieren", "Datei hinzufügen",
                                      "Ordner hinzufügen"]
    assert said("Text erstellt.")
    press_enter_on_action(window, qtbot, "Text kopieren")
    assert QGuiApplication.clipboard().text() == LETTER_TEXT and said("Text kopiert.")

    ask(window, qtbot, "Gib mir das als Word-Datei")
    assert "Word-Dokument speichern: Bewerbung" in window.actions.texts()
    assert said("Word-Dokument bereit.") and said("Text geändert.")
    target = tmp_path / "Bewerbung.docx"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    press_enter_on_action(window, qtbot, "Word-Dokument speichern")
    assert [p.text for p in Document(str(target)).paragraphs] == \
        ["Sehr geehrte Damen und Herren,", "hiermit bewerbe ich mich."]
    assert said("Word-Dokument gespeichert: Bewerbung.docx.")


def test_edits_in_answer_field_go_to_model_and_are_saved_in_history(make_window, qtbot, store):
    window = make_window([content(LETTER), content("Kürzer gemacht.")])
    ask(window, qtbot, "Schreibe ein Anschreiben")
    edit_answer(window, COMMENT + "\n\nMEINE EIGENE FASSUNG")
    assert window.answer.document_text() == "MEINE EIGENE FASSUNG"
    ask(window, qtbot, "Mach es kürzer")
    sent = window.session.backend.calls[1]["messages"][-1]["content"]
    assert "MEINE EIGENE FASSUNG" in sent and COMMENT not in sent and "Mach es kürzer" in sent
    assert store.exchanges(window.chat_id)[1].answer.endswith("MEINE EIGENE FASSUNG")


def test_plain_answer_is_not_sent_back_but_edited_answer_is(make_window, qtbot):
    window = make_window([content("Erste Antwort."), content("Zweite."), content("Dritte.")])
    ask(window, qtbot, "Eins")
    ask(window, qtbot, "Zwei")
    assert window.session.backend.calls[1]["messages"][-1]["content"] == "Zwei"
    edit_answer(window, "Mein eigener Text zum Verbessern")
    ask(window, qtbot, "Drei")
    assert "Mein eigener Text zum Verbessern" in window.session.backend.calls[2]["messages"][-1]["content"]


def test_save_word_without_text(make_window):
    window = make_window()
    window._save_word()
    assert said("Es gibt noch keinen Text zum Speichern.")


def test_add_files_lists_them_in_actions_and_reaches_model(make_window, qtbot, monkeypatch, tmp_path):
    good = tmp_path / "notiz.txt"
    good.write_text("Der Vertrag beginnt am 1. Mai.", encoding="utf-8")
    bad = tmp_path / "programm.exe"
    bad.write_bytes(b"\x89PNG")
    window = make_window([content("Verstanden.")])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(good), str(bad)], ""))
    press_enter_on_action(window, qtbot, "Datei hinzufügen")
    assert said("notiz.txt hinzugefügt, 6 Wörter.")
    assert any(urgent and "programm.exe" in text for text, urgent in announcer.history)
    assert window.actions.texts()[-1] == "Hinzugefügte Datei: notiz.txt"
    assert focus_now() is window.actions.list
    ask(window, qtbot, "Wann beginnt der Vertrag?")
    assert "Der Vertrag beginnt am 1. Mai." in window.session.backend.calls[0]["messages"][0]["content"]


def test_enter_on_added_file_does_nothing_but_delete_removes_it(make_window, qtbot, monkeypatch,
                                                              tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("Inhalt", encoding="utf-8")
    window = make_window()
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(f)], ""))
    press_enter_on_action(window, qtbot, "Datei hinzufügen")
    lst = window.actions.list
    lst.setCurrentRow(action_row(window, "Hinzugefügte Datei"))
    announcer.history.clear()
    qtbot.keyClick(lst, Qt.Key.Key_Return)
    assert announcer.history == []
    qtbot.keyClick(lst, Qt.Key.Key_Delete)
    assert window.session.attachments == [] and window.actions.texts() == \
        ["Antwort kopieren", "Datei hinzufügen", "Ordner hinzufügen"]
    assert focus_now() is lst and lst.currentItem().text() == "Datei hinzufügen"
    assert said("a.txt entfernt.") and f.exists()


def test_delete_key_on_a_basic_action_does_nothing(make_window, qtbot):
    window = make_window()
    lst = window.actions.list
    lst.setFocus()
    lst.setCurrentRow(0)
    qtbot.keyClick(lst, Qt.Key.Key_Delete)
    assert len(window.actions.texts()) == 3


def test_add_folder_grants_access_and_model_gets_folder_tools(make_window, qtbot, monkeypatch,
                                                              tmp_path):
    root = tmp_path / "Unterlagen"
    root.mkdir()
    (root / "a.txt").write_text("Kaution 2550 Euro", encoding="utf-8")
    (root / "b.txt").write_text("Termin Montag", encoding="utf-8")
    window = make_window([tool_call("datei_lesen", datei="a.txt"),
                          content("Die Kaution beträgt 2550 Euro.")])
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(root))
    press_enter_on_action(window, qtbot, "Ordner hinzufügen")
    assert said("Ordner Unterlagen freigegeben, 2 lesbare Dateien.")
    assert window.actions.texts()[-1].startswith("Hinzugefügter Ordner: ")
    ask(window, qtbot, "Wie hoch ist die Kaution?")
    names = [t["function"]["name"] for t in window.session.backend.calls[0]["tools"]]
    assert names == ["ordner_auflisten", "in_dateien_suchen", "datei_lesen"]
    assert "Datei wird gelesen: a.txt" in [t for t, _ in announcer.history]
    assert window.answer.text().endswith("Gelesene Dateien:\n- a.txt")


def test_file_and_folder_menu_entries_work_like_the_actions(make_window, monkeypatch, tmp_path):
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    window = make_window()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    find(top_menu(window, "Datei"), "Ordner hinzufügen").trigger()
    assert window.session.folders.roots == [tmp_path.resolve()]
    window._remove_attachment(0)
    assert window.session.folders.roots == []


def test_attachments_are_saved_with_the_chat_and_restored(make_window, qtbot, monkeypatch, tmp_path,
                                                          store):
    f = tmp_path / "notiz.txt"
    f.write_text("Wichtiger Inhalt", encoding="utf-8")
    root = tmp_path / "Ordner"
    root.mkdir()
    (root / "x.txt").write_text("x", encoding="utf-8")
    window = make_window([content("A1"), content("A2")])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(f)], ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(root))
    press_enter_on_action(window, qtbot, "Datei hinzufügen")
    press_enter_on_action(window, qtbot, "Ordner hinzufügen")
    ask(window, qtbot, "Chat mit Anhängen")
    assert [a["type"] for a in store.get_chat(window.chat_id).attachments] == ["file", "folder"]

    chat_id = window.chat_id
    window.act_new_chat.trigger()
    assert window.actions.texts() == ["Antwort kopieren", "Datei hinzufügen", "Ordner hinzufügen"]
    assert window.session.folders.roots == []
    window._open_chat(chat_id)
    assert window.actions.texts()[-2:] == ["Hinzugefügte Datei: notiz.txt",
                                           f"Hinzugefügter Ordner: {root.resolve()}"]
    assert [a.name for a in window.session.attachments] == ["notiz.txt"]
    f.unlink()
    window.act_new_chat.trigger()
    window._open_chat(chat_id)
    assert any(urgent and "Nicht mehr vorhanden: notiz.txt" in text for text, urgent in announcer.history)


# -- Verlauf: nur ansehen -----------------------------------------------------------------
def test_every_new_question_creates_a_new_history_point(make_window, qtbot, store):
    window = make_window([content("A1"), content("A2"), content("A3")])
    for q in ("Frage eins", "Frage zwei", "Frage drei"):
        ask(window, qtbot, q)
    panel = window.history_panel
    assert panel.count() == 3 and said("Neuer Eintrag im Verlauf.")
    assert [panel.list.item(i).text().split(",")[0] for i in range(3)] == \
        ["Frage drei", "Frage zwei", "Frage eins"]                    # neueste oben, untereinander
    assert panel.list.currentRow() == 0
    assert re.search(r", \d\d\.\d\d\.\d{4}, \d\d:\d\d$", panel.list.item(0).text())
    assert len(store.chats()) == 1 and len(store.exchanges(window.chat_id)) == 3


def test_history_cannot_be_deleted(make_window, qtbot):
    window = make_window([content("A1"), content("A2")])
    ask(window, qtbot, "F1")
    ask(window, qtbot, "F2")
    panel = window.history_panel
    assert panel.findChildren(QPushButton) == []
    panel.list.setFocus()
    panel.list.setCurrentRow(0)
    qtbot.keyClick(panel.list, Qt.Key.Key_Delete)
    assert panel.count() == 2
    assert not hasattr(panel, "delete_current") and not hasattr(panel, "clearRequested")


def test_history_click_and_enter_land_in_the_answer_and_keep_the_question_field(make_window, qtbot):
    window = make_window([content(LETTER), content("Zweite Antwort.")])
    ask(window, qtbot, "Erste Frage")
    ask(window, qtbot, "Zweite Frage")
    window.question.edit.setPlainText("Noch nicht gesendet")
    panel = window.history_panel
    assert panel.list.item(1).text().endswith("mit Text")
    lst = panel.list
    lst.setFocus()
    lst.setCurrentRow(1)
    qtbot.keyClick(lst, Qt.Key.Key_Return)
    assert window.answer.text() == COMMENT + "\n\n" + LETTER_TEXT and window.answer.is_doc
    assert "Text kopieren" in window.actions.texts()
    assert focus_now() is window.answer.edit
    assert window.question.edit.toPlainText() == "Noch nicht gesendet"     # Eingabe bleibt frei
    assert said("Verlauf geladen: Erste Frage, vom")
    lst.setFocus()
    qtbot.mouseClick(lst.viewport(), Qt.MouseButton.LeftButton,
                     pos=lst.visualItemRect(lst.item(0)).center())
    assert window.answer.text() == "Zweite Antwort." and not window.answer.is_doc
    assert "Text kopieren" not in window.actions.texts() and focus_now() is window.answer.edit


def test_history_space_activates(make_window, qtbot):
    window = make_window([content("A1"), content("A2")])
    ask(window, qtbot, "F1")
    ask(window, qtbot, "F2")
    lst = window.history_panel.list
    lst.setFocus()
    lst.setCurrentRow(1)
    qtbot.keyClick(lst, Qt.Key.Key_Space)
    assert window.answer.text() == "A1"


# -- Menü Projekte -------------------------------------------------------------------------
def test_new_project_via_menu_creates_it_and_lists_it(make_window, monkeypatch, store):
    window = make_window()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Bewerbungen", True))
    find(top_menu(window, "Projekte"), "Neues Projekt").trigger()       # Enter: Namensdialog
    assert [p.name for p in store.projects()] == ["Bewerbungen"]
    assert said("Projekt Bewerbungen erstellt.")
    entries = texts(projects_menu(window))
    assert entries[:2] == ["Neues Projekt …", "Bewerbungen"]
    assert find(projects_menu(window), "Bewerbungen").menu() is not None    # Enter öffnet Chatliste


def test_cancelled_name_dialog_creates_nothing(make_window, monkeypatch, store):
    window = make_window()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    window._new_project()
    assert store.projects() == []
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("   ", True))
    window._new_project()
    assert store.projects() == []


def test_projects_are_listed_alphabetically_and_empty_state_is_explained(make_window, monkeypatch):
    window = make_window()
    assert texts(projects_menu(window))[-1] == "Noch keine Projekte vorhanden"
    create_project(window, monkeypatch, "Zebra")
    create_project(window, monkeypatch, "Alpha")
    assert texts(projects_menu(window)) == ["Neues Projekt …", "Alpha", "Zebra"]


def test_project_chat_list_starts_with_new_chat_then_its_chats(make_window, qtbot, monkeypatch):
    window = make_window([content("A1")])
    create_project(window, monkeypatch)
    assert texts(project_chat_list(window, "Bewerbungen")) == ["Neuer Chat", "Projektdateien"]
    find(project_chat_list(window, "Bewerbungen"), "Neuer Chat").trigger()
    assert said("Neuer Chat im Projekt Bewerbungen.")
    assert window.windowTitle() == "Chatbot für Text: Neuer Chat, Projekt Bewerbungen, bereit"
    assert focus_now() is window.question.edit
    ask(window, qtbot, "Anschreiben für Firma X")
    assert said("Der Chat gehört zum Projekt Bewerbungen.")
    listed = texts(project_chat_list(window, "Bewerbungen"))
    assert listed[:2] == ["Neuer Chat", "Projektdateien"]
    assert listed[2].startswith("Anschreiben für Firma X")
    assert not any("Anschreiben" in t for t in texts(chats_menu(window)))    # nicht in der Chatliste


def test_enter_on_chat_in_project_opens_it_normally(make_window, qtbot, monkeypatch):
    window = make_window([content(LETTER), content("Zweite.")])
    create_project(window, monkeypatch)
    find(project_chat_list(window, "Bewerbungen"), "Neuer Chat").trigger()
    ask(window, qtbot, "Erste Frage")
    ask(window, qtbot, "Zweite Frage")
    window.act_new_chat.trigger()
    assert window.history_panel.count() == 0
    find(project_chat_list(window, "Bewerbungen"), "Erste Frage").trigger()
    assert said("Chat geöffnet: Erste Frage, 2 Einträge.")
    assert window.history_panel.count() == 2 and window.answer.text() == "Zweite."
    assert focus_now() is window.answer.edit
    assert [q for q, _ in window.session.turns] == ["Erste Frage", "Zweite Frage"]
    assert "Projekt Bewerbungen" in window.windowTitle()


# -- Menü Chatliste --------------------------------------------------------------------------
def test_new_chat_clears_everything_and_keeps_stored_chats(make_window, qtbot, store):
    window = make_window([content("A1"), content("A2")])
    ask(window, qtbot, "Erster Chat Frage")
    window.act_new_chat.trigger()
    assert window.chat_id is None and window.history_panel.count() == 0
    assert window.answer.text() == "" and window.question.edit.toPlainText() == ""
    assert focus_now() is window.question.edit and said("Neuer Chat.")
    ask(window, qtbot, "Zweiter Chat Frage")
    assert len(store.chats()) == 2
    assert len(window.session.backend.calls[1]["messages"]) == 2      # ohne Gedächtnis des ersten


def test_chat_list_shows_only_chats_without_project_and_enter_opens(make_window, qtbot, monkeypatch):
    window = make_window([content("A1"), content("A2"), content("A3")])
    create_project(window, monkeypatch)
    find(project_chat_list(window, "Bewerbungen"), "Neuer Chat").trigger()
    ask(window, qtbot, "Im Projekt")
    window.act_new_chat.trigger()
    ask(window, qtbot, "Lose Frage")
    window.act_new_chat.trigger()
    entries = texts(chats_menu(window))
    assert entries[0] == "Neuer Chat" and len(entries) == 2 and entries[1].startswith("Lose Frage")
    find(chats_menu(window), "Lose Frage").trigger()
    assert window.answer.text() == "A2" and focus_now() is window.answer.edit


def test_empty_chat_list_says_so(make_window):
    assert texts(chats_menu(make_window()))[-1] == "Noch keine Chats ohne Projekt"


def test_new_chat_shortcut_is_ctrl_n(make_window):
    assert make_window().act_new_chat.shortcut().toString() == "Ctrl+N"


# -- Kontextmenüs ---------------------------------------------------------------------------
def test_context_menu_of_a_project_offers_remove_and_keeps_chats(make_window, qtbot, monkeypatch, store):
    window = make_window([content("A1")])
    create_project(window, monkeypatch)
    find(project_chat_list(window, "Bewerbungen"), "Neuer Chat").trigger()
    ask(window, qtbot, "Bleibt erhalten")
    window.act_new_chat.trigger()
    project_action = find(projects_menu(window), "Bewerbungen")
    menu = context_menu(window, project_action)
    assert texts(menu) == ["Projekt entfernen"]
    asked = {}

    def fake_confirm(parent, title, text, **kwargs):
        asked.update(kwargs, text=text)
        return False
    monkeypatch.setattr("ui.main_window.confirm", fake_confirm)
    find(menu, "Projekt entfernen").trigger()
    assert len(store.projects()) == 1                                    # Rückfrage abgelehnt
    assert asked["default_yes"] is True and "1 Chat" in asked["text"]    # Enter bestätigt
    monkeypatch.setattr("ui.main_window.confirm", lambda *a, **k: True)
    find(menu, "Projekt entfernen").trigger()
    assert store.projects() == [] and len(store.chats()) == 1
    assert store.chats()[0].project_id is None
    assert said("Projekt Bewerbungen entfernt. Die Chats stehen jetzt in der Chatliste.")
    assert any("Bleibt erhalten" in t for t in texts(chats_menu(window)))


def test_context_menu_of_a_chat_in_the_chat_list(make_window, qtbot, monkeypatch, store):
    window = make_window([content("A1")])
    create_project(window, monkeypatch, "Alpha")
    create_project(window, monkeypatch, "Beta")
    ask(window, qtbot, "Lose Frage")
    action = find(chats_menu(window), "Lose Frage")
    menu = context_menu(window, action)
    assert texts(menu) == ["In Projekt verschieben", "Chat entfernen"]
    picker = find(menu, "In Projekt verschieben").menu()
    assert texts(picker) == ["Alpha", "Beta"]                            # die Projektliste
    find(picker, "Beta").trigger()                                       # Enter wählt
    chat = store.get_chat(window.chat_id)
    assert chat.project_id == next(p.id for p in store.projects() if p.name == "Beta")
    assert said("Chat Lose Frage in das Projekt Beta verschoben.")
    assert texts(chats_menu(window)) == ["Neuer Chat", "Noch keine Chats ohne Projekt"]
    assert "Lose Frage" in " ".join(texts(project_chat_list(window, "Beta")))
    assert "Projekt Beta" in window.windowTitle()


def test_context_menu_of_a_chat_in_a_project(make_window, qtbot, monkeypatch, store):
    window = make_window([content("A1")])
    create_project(window, monkeypatch, "Alpha")
    create_project(window, monkeypatch, "Beta")
    find(project_chat_list(window, "Alpha"), "Neuer Chat").trigger()
    ask(window, qtbot, "Im Projekt Alpha")
    alpha, beta = (next(p.id for p in store.projects() if p.name == n) for n in ("Alpha", "Beta"))
    action = find(project_chat_list(window, "Alpha"), "Im Projekt Alpha")
    menu = context_menu(window, action)
    assert texts(menu) == ["In anderes Projekt verschieben", "In anderes Projekt kopieren",
                           "Aus dem Projekt in die Chatliste", "Chat entfernen"]
    assert texts(find(menu, "anderes Projekt verschieben").menu()) == ["Beta"]   # nicht das eigene
    assert texts(find(menu, "anderes Projekt kopieren").menu()) == ["Beta"]

    choose(menu, "In anderes Projekt kopieren", "Beta")
    assert said("Chat Im Projekt Alpha in das Projekt Beta kopiert.")
    assert len(store.chats_in_project(alpha)) == 1 and len(store.chats_in_project(beta)) == 1
    copy = store.chats_in_project(beta)[0]
    assert [e.question for e in store.exchanges(copy.id)] == ["Im Projekt Alpha"]

    choose(context_menu(window, action), "In anderes Projekt verschieben", "Beta")
    assert store.chats_in_project(alpha) == [] and len(store.chats_in_project(beta)) == 2

    beta_action = find(project_chat_list(window, "Beta"), "Im Projekt Alpha")
    choose(context_menu(window, beta_action), "Aus dem Projekt in die Chatliste")
    assert said("ist jetzt in der Chatliste.") and len(store.chats_in_project(beta)) == 1
    assert len(store.chats_without_project()) == 1


def test_pickers_explain_when_no_other_project_exists(make_window, qtbot, monkeypatch):
    window = make_window([content("A1")])
    create_project(window, monkeypatch, "Einziges")
    find(project_chat_list(window, "Einziges"), "Neuer Chat").trigger()
    ask(window, qtbot, "Frage")
    menu = context_menu(window, find(project_chat_list(window, "Einziges"), "Frage"))
    picker = find(menu, "anderes Projekt verschieben").menu()
    assert texts(picker) == ["Kein passendes Projekt vorhanden"] and not picker.actions()[0].isEnabled()


def test_removing_a_chat_asks_with_enter_as_default_and_resets_view(make_window, qtbot, monkeypatch,
                                                                    store):
    window = make_window([content("A1")])
    ask(window, qtbot, "Zu entfernen")
    menu = context_menu(window, find(chats_menu(window), "Zu entfernen"))
    asked = {}

    def fake_confirm(parent, title, text, **kwargs):
        asked.update(kwargs)
        return asked.setdefault("calls", 0) or asked.update(calls=1) or False
    monkeypatch.setattr("ui.main_window.confirm", fake_confirm)
    find(menu, "Chat entfernen").trigger()
    assert len(store.chats()) == 1 and asked["default_yes"] is True
    monkeypatch.setattr("ui.main_window.confirm", lambda *a, **k: True)
    find(menu, "Chat entfernen").trigger()
    assert store.chats() == [] and window.chat_id is None and window.history_panel.count() == 0
    assert said("Chat Zu entfernen entfernt.") and focus_now() is window.question.edit


# -- Kontextmenü per Tastatur ------------------------------------------------------------------
def test_menu_key_and_shift_f10_request_context_menu_only_on_entries_with_data(qtbot):
    menu = ContextMenu("Test")
    with_data = menu.addAction("Mit Kontext")
    with_data.setData(("chat", 1))
    menu.addAction("Ohne Kontext")
    qtbot.addWidget(menu)
    menu.popup(menu.pos())
    seen = []
    menu.contextRequested.connect(lambda action, pos: seen.append(action.text()))
    menu.setActiveAction(with_data)
    qtbot.keyClick(menu, Qt.Key.Key_Menu)
    qtbot.keyClick(menu, Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier)
    assert seen == ["Mit Kontext", "Mit Kontext"]
    menu.setActiveAction(menu.actions()[1])
    qtbot.keyClick(menu, Qt.Key.Key_Menu)
    assert seen == ["Mit Kontext", "Mit Kontext"]


def test_keyboard_context_menu_event_uses_the_active_entry_and_opens_only_once(qtbot):
    """Windows meldet Umschalt+F10 oft nur als Kontextmenü-Ereignis (Position bedeutungslos), die
    Menütaste als Taste und als Ereignis. Beides zusammen darf nur ein Kontextmenü ergeben."""
    import ui.menus as menus
    menu = ContextMenu("Test")
    with_data = menu.addAction("Mit Kontext")
    with_data.setData(("chat", 1))
    menu.addAction("Ohne Kontext")
    qtbot.addWidget(menu)
    menu.popup(menu.pos())
    seen = []
    menu.contextRequested.connect(lambda action, pos: seen.append(action.text()))
    menu.setActiveAction(with_data)

    def keyboard_event():
        event = QContextMenuEvent(QContextMenuEvent.Reason.Keyboard, QPoint(0, 0), QPoint(0, 0))
        QApplication.sendEvent(menu, event)

    menus._last_key_request = 0.0
    keyboard_event()                                             # nur Ereignis, keine Taste
    assert seen == ["Mit Kontext"]
    menus._last_key_request = 0.0
    qtbot.keyClick(menu, Qt.Key.Key_Menu)                        # Taste ...
    keyboard_event()                                             # ... und gleich danach Ereignis
    assert seen == ["Mit Kontext"] * 2
    menu.setActiveAction(menu.actions()[1])
    menus._last_key_request = 0.0
    keyboard_event()                                             # Eintrag ohne Kontextmenü
    assert seen == ["Mit Kontext"] * 2


def test_window_menus_route_the_menu_key_to_the_context_menu(make_window, qtbot, monkeypatch):
    window = make_window()
    create_project(window, monkeypatch)
    shown = []
    monkeypatch.setattr(window, "_exec_menu", lambda menu, position: shown.append(texts(menu)))
    menu = projects_menu(window)
    menu.popup(menu.pos())
    menu.setActiveAction(find(menu, "Bewerbungen"))
    qtbot.keyClick(menu, Qt.Key.Key_Menu)
    assert shown == [["Projekt entfernen"]]
    menu.close()


def test_context_menu_opens_with_first_entry_marked_but_submenu_closed(make_window, qtbot):
    """Ein Screenreader liest den markierten Eintrag vor. Ohne Markierung wirkt das Menü stumm.
    Ein Untermenü darf dabei nicht von selbst aufgehen."""
    window = make_window([content("A1")])
    ask(window, qtbot, "Lose Frage")
    menu = context_menu(window, find(chats_menu(window), "Lose Frage"))
    qtbot.addWidget(menu)
    menu.popup(window.pos())
    _select_first(menu)
    assert menu.activeAction().text() == "In Projekt verschieben"
    assert not menu.activeAction().menu().isVisible()
    menu.close()


# -- Projektdateien (gehören zu einem Projekt) --------------------------------------------------
def project_id(window, name="Bewerbungen"):
    return next(p.id for p in window.store.projects() if p.name == name)


def project_files_menu(window, name="Bewerbungen"):
    menu = find(project_chat_list(window, name), "Projektdateien").menu()
    window._fill_project_files_menu(menu, project_id(window, name))    # wie beim Öffnen des Untermenüs
    return menu


@pytest.fixture
def two_files(tmp_path):
    a, b = tmp_path / "Lebenslauf.txt", tmp_path / "Anzeige.txt"
    a.write_text("Ich heiße Max Muster und wohne in Köln.", encoding="utf-8")
    b.write_text("Stelle als Buchhalter in Hamburg.", encoding="utf-8")
    return a, b


def upload(window, monkeypatch, *paths, project="Bewerbungen"):
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(p) for p in paths], ""))
    find(project_files_menu(window, project), "Datei hochladen").trigger()


def test_project_files_sit_one_level_below_the_project_between_new_chat_and_chats(
        make_window, qtbot, monkeypatch):
    window = make_window([content("A1")])
    create_project(window, monkeypatch)
    assert "Projektdateien" not in texts(projects_menu(window))            # nicht mehr auf oberster Ebene
    window._new_chat(project_id(window))
    ask(window, qtbot, "Anschreiben")
    listed = texts(project_chat_list(window, "Bewerbungen"))
    assert listed[:2] == ["Neuer Chat", "Projektdateien"] and listed[2].startswith("Anschreiben")
    assert texts(project_files_menu(window)) == ["Datei hochladen …", "Noch keine Projektdateien"]


def test_uploading_lists_files_below_the_upload_entry_per_project(make_window, monkeypatch, store,
                                                                   two_files):
    window = make_window()
    create_project(window, monkeypatch, "Bewerbungen")
    create_project(window, monkeypatch, "Steuer")
    window._new_chat(project_id(window))
    upload(window, monkeypatch, *two_files)
    assert texts(project_files_menu(window)) == ["Datei hochladen …", "Anzeige.txt", "Lebenslauf.txt"]
    assert [f.path for f in store.project_files(project_id(window))] == [str(two_files[1]),
                                                                          str(two_files[0])]
    assert texts(project_files_menu(window, "Steuer")) == ["Datei hochladen …",
                                                           "Noch keine Projektdateien"]
    assert said("2 Dateien zu den Projektdateien von Bewerbungen hinzugefügt. "
                "Alle Chats im Projekt können sie lesen.")
    upload(window, monkeypatch, two_files[0])                                # doppelt: bleibt einmal
    assert len(store.project_files(project_id(window))) == 2
    assert len(window.session.attachments) == 2                              # der offene Chat gehört dazu


def test_project_files_are_readable_only_in_chats_of_that_project(make_window, qtbot, monkeypatch,
                                                                   store, two_files):
    window = make_window([content("A1"), content("A2"), content("A3")])
    create_project(window, monkeypatch, "Bewerbungen")
    create_project(window, monkeypatch, "Steuer")
    upload(window, monkeypatch, two_files[0])                                # Chat ohne Projekt offen
    assert window.session.attachments == []                                  # gehört nicht dazu
    window._new_chat(project_id(window))
    assert [a.name for a in window.session.attachments] == ["Lebenslauf.txt"]
    assert window._meta == []                                                # gehört keinem Chat
    ask(window, qtbot, "Wer bin ich?")
    assert "Max Muster" in window.backend.calls[0]["messages"][0]["content"]
    window._new_chat(project_id(window, "Steuer"))                           # anderes Projekt
    assert window.session.attachments == []
    window.act_new_chat.trigger()                                            # Chatliste
    assert window.session.attachments == []
    find(project_chat_list(window, "Bewerbungen"), "Wer bin ich").trigger()  # gespeicherter Chat
    assert [a.name for a in window.session.attachments] == ["Lebenslauf.txt"]


def test_moving_the_open_chat_changes_its_project_files(make_window, qtbot, monkeypatch, store,
                                                         two_files):
    window = make_window([content("A1")])
    create_project(window, monkeypatch, "Bewerbungen")
    create_project(window, monkeypatch, "Steuer")
    upload(window, monkeypatch, two_files[0], project="Bewerbungen")
    upload(window, monkeypatch, two_files[1], project="Steuer")
    window._new_chat(project_id(window))
    ask(window, qtbot, "Frage")
    assert [a.name for a in window.session.attachments] == ["Lebenslauf.txt"]
    window._move_chat(window.chat_id, project_id(window, "Steuer"))
    assert [a.name for a in window.session.attachments] == ["Anzeige.txt"]
    window._move_chat(window.chat_id, None)
    assert window.session.attachments == []


def test_project_file_context_menu_removes_only_the_entry(make_window, monkeypatch, store, two_files):
    window = make_window()
    create_project(window, monkeypatch)
    window._new_chat(project_id(window))
    upload(window, monkeypatch, *two_files)
    action = find(project_files_menu(window), "Lebenslauf")
    menu = context_menu(window, action)
    assert texts(menu) == ["Datei entfernen"]
    asked = {}

    def fake_confirm(parent, title, text, **kwargs):
        asked.update(kwargs)
        return False
    monkeypatch.setattr("ui.main_window.confirm", fake_confirm)
    find(menu, "Datei entfernen").trigger()
    assert len(store.project_files(project_id(window))) == 2 and asked["default_yes"] is True
    monkeypatch.setattr("ui.main_window.confirm", lambda *a, **k: True)
    find(menu, "Datei entfernen").trigger()
    assert [f.name for f in store.project_files(project_id(window))] == ["Anzeige.txt"]
    assert [a.name for a in window.session.attachments] == ["Anzeige.txt"]
    assert two_files[0].exists() and said("Lebenslauf.txt aus den Projektdateien entfernt.")


def test_removing_a_chat_file_keeps_the_project_file_of_the_same_path(make_window, qtbot, monkeypatch,
                                                                       two_files):
    window = make_window()
    create_project(window, monkeypatch)
    window._new_chat(project_id(window))
    upload(window, monkeypatch, two_files[0])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(two_files[0])], ""))
    window._on_add_file()
    assert len(window.session.attachments) == 1 and len(window._meta) == 1     # nicht doppelt
    window._remove_attachment(0)
    assert [a.name for a in window.session.attachments] == ["Lebenslauf.txt"]


def test_unreadable_project_file_is_reported_in_new_chat_of_the_project(make_window, monkeypatch,
                                                                         two_files):
    window = make_window()
    create_project(window, monkeypatch)
    upload(window, monkeypatch, two_files[0])
    two_files[0].unlink()
    window._new_chat(project_id(window))
    assert said("Projektdatei Lebenslauf.txt nicht lesbar.") and window.session.attachments == []


def test_removing_the_project_removes_its_file_entries_but_not_the_files(
        make_window, monkeypatch, store, two_files, tmp_path):
    window = make_window()
    create_project(window, monkeypatch)
    pid = project_id(window)
    window._new_chat(pid)
    upload(window, monkeypatch, two_files[0])
    assert len(window.session.attachments) == 1
    monkeypatch.setattr("ui.main_window.confirm", lambda *a, **k: True)
    window._remove_project(pid)
    assert store.project_files(pid) == [] and two_files[0].exists()
    assert window.session.attachments == []                                  # der offene Chat hat sie nicht mehr


def test_menus_have_own_names_and_repeat_the_focus_event_for_the_first_entry(make_window, qtbot,
                                                                          monkeypatch):
    """NVDA nannte sonst den Programmnamen und überging den ersten Eintrag."""
    import ui.menus as menus
    window = make_window([content("A1")])
    create_project(window, monkeypatch)
    assert projects_menu(window).accessibleName() == "Projekte"
    assert chats_menu(window).accessibleName() == "Chatliste"
    sent = []

    class FakeAccessible:
        Event = menus.QAccessible.Event
        updateAccessibility = staticmethod(lambda event: sent.append(event.child()))
    monkeypatch.setattr(menus, "QAccessible", FakeAccessible)
    menu = context_menu(window, find(projects_menu(window), "Bewerbungen"))
    assert menu.accessibleName() == "Kontextmenü" and texts(menu) == ["Projekt entfernen"]
    qtbot.addWidget(menu)
    menu.popup(window.pos())
    _select_first(menu)
    assert sent == []                                   # nicht sofort, sondern nach einer Pause
    qtbot.waitUntil(lambda: sent == [0], timeout=2000)
    menu.close()


def test_focus_returns_from_the_menu_bar_after_a_context_menu_action(make_window, qtbot, monkeypatch):
    window = make_window([content("A1")])
    ask(window, qtbot, "Lose Frage")
    action = find(chats_menu(window), "Lose Frage")
    monkeypatch.setattr(window, "_exec_menu", lambda menu, position: None)
    window.menuBar().setFocus()                        # so steht der Fokus nach Alt+Buchstabe
    assert isinstance(QApplication.focusWidget(), QMenuBar)
    window._show_context_menu(action, QPoint(0, 0))
    assert not isinstance(QApplication.focusWidget(), QMenuBar)


# -- Navigation, Schrift ---------------------------------------------------------------------
def test_f6_cycles_the_four_areas(make_window):
    window = make_window()
    window._focus_question()
    seen = []
    for _ in range(4):
        window._cycle_area(+1)
        seen.append(window._current_area())
    assert seen == [1, 2, 3, 0]
    window._cycle_area(-1)
    assert window._current_area() == 3


def test_ctrl_number_targets(make_window):
    window = make_window()
    window._focus_history()
    assert focus_now() is window.history_panel.list
    window._focus_answer()
    assert focus_now() is window.answer.edit
    window._focus_actions()
    assert focus_now() is window.actions.list
    window._focus_question()
    assert focus_now() is window.question.edit


def test_edits_are_kept_when_switching_chats(make_window, qtbot, store):
    window = make_window([content("A1"), content("A2")])
    ask(window, qtbot, "Chat eins")
    first_chat = window.chat_id
    edit_answer(window, "Von mir geänderte Antwort")
    window.act_new_chat.trigger()
    assert store.exchanges(first_chat)[0].answer == "Von mir geänderte Antwort"


def test_window_title_follows_chat_and_state(make_window, qtbot):
    window = make_window([content("A1")], delay=0.2)
    window.question.edit.setPlainText("Titel der Frage")
    window._on_ask()
    assert window.windowTitle().endswith("Anfrage läuft")
    qtbot.waitUntil(lambda: said("Antwort fertig."), timeout=5000)
    assert window.windowTitle() == "Chatbot für Text: Titel der Frage, bereit"


def test_font_size_change_is_saved_and_limited(make_window, cfg):
    window = make_window()
    start = cfg.font_size
    assert start >= 12
    window._change_font(+1)
    assert cfg.font_size == start + 1
    cfg.font_size = 10
    window._change_font(-1)
    assert cfg.font_size == 10 and said("ist die Grenze")


def test_no_fixed_colors(make_window):
    window = make_window()
    for widget in window.findChildren(QWidget):
        assert "color" not in widget.styleSheet().lower()

# -- PDFs, Scans und Bilder ---------------------------------------------------------------------
def test_file_dialog_offers_pdf_and_image_files():
    from ui.main_window import FILE_FILTER
    assert "*.pdf" in FILE_FILTER and "*.png" in FILE_FILTER and "*.jpg" in FILE_FILTER
    assert "*.txt" in FILE_FILTER and FILE_FILTER.endswith("Alle Dateien (*)")


def test_adding_pdf_scan_and_image_says_what_the_model_can_do(make_window, qtbot, monkeypatch, tmp_path):
    pdf = make_pdf(tmp_path / "Vertrag.pdf", ["Der Vertrag beginnt am 1. Mai. " * 20])
    scan = make_scan(tmp_path / "Scan.pdf", 2)
    image = make_image(tmp_path / "Foto.png")
    window = make_window([content("Verstanden.")])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([str(pdf), str(scan), str(image)], ""))
    press_enter_on_action(window, qtbot, "Datei hinzufügen")
    assert said("Vertrag.pdf hinzugefügt, 1 Seite, ")
    assert said("Scan.pdf hinzugefügt, 2 Seiten ohne Text (Scan)")
    assert said("Foto.png hinzugefügt. Das Modell sieht es sich an, wenn Sie danach fragen.")
    assert {d.name for d in window.session.docs.docs.values()} == {"Vertrag.pdf", "Scan.pdf", "Foto.png"}
    assert len(window._meta) == 3
    ask(window, qtbot, "Was ist in den Dateien?")
    system = window.backend.calls[0]["messages"][0]["content"]
    assert "Scan.pdf: PDF, 2 Seiten" in system and "Foto.png: Bild" in system
    window._remove_attachment(window._meta.index(next(m for m in window._meta if "Foto" in m["path"])))
    assert "Foto.png" not in {d.name for d in window.session.docs.docs.values()}


def test_project_pdf_is_available_in_the_chats_of_the_project(make_window, monkeypatch, tmp_path):
    pdf = make_pdf(tmp_path / "Handbuch.pdf", ["Kapitel eins. " * 30])
    window = make_window()
    create_project(window, monkeypatch)
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(pdf)], ""))
    find(project_files_menu(window), "Datei hochladen").trigger()
    window._new_chat(project_id(window))
    assert [d.name for d in window.session.docs.docs.values()] == ["Handbuch.pdf"]
    window.act_new_chat.trigger()                                            # Chat ohne Projekt
    assert not window.session.docs


def test_check_pdf_menu_puts_the_report_in_the_answer_and_history(make_window, qtbot, monkeypatch, tmp_path):
    window = make_window()
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **k: (str(defective_pdf(tmp_path / "fehler.pdf")), ""))
    window.act_check_pdf.trigger()
    qtbot.waitUntil(lambda: window.history_panel.count() == 1, timeout=5000)
    text = window.answer.text()
    assert text.startswith("Prüfung von fehler.pdf: 3 Seite(n)") and "rechts über die Seite hinaus" in text
    assert "Auffällige Seiten: 1" in text
    assert said("PDF fehler.pdf wird geprüft.") and said("Antwort fertig.")
    assert window.session.turns[-1][0] == "PDF prüfen: fehler.pdf"          # Rückfragen möglich
    assert window._ask_task is None and focus_now() is window.answer.edit


def test_check_pdf_menu_reports_broken_files_and_cancel_does_nothing(make_window, qtbot, monkeypatch, tmp_path):
    window = make_window()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    window.act_check_pdf.trigger()
    assert window.history_panel.count() == 0 and window._ask_task is None
    broken = tmp_path / "kaputt.pdf"
    broken.write_bytes(b"kein pdf")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(broken), ""))
    window.act_check_pdf.trigger()
    qtbot.waitUntil(lambda: window.history_panel.count() == 1, timeout=5000)
    assert window.answer.text().startswith("Prüfung von kaputt.pdf nicht möglich")

# -- Fragefeld und Antwortfeld: echte Zeilen für Screenreader und Braillezeile ------------------
def test_shift_enter_in_the_question_makes_a_real_new_line_not_a_unicode_separator(make_window, qtbot):
    window = make_window()
    edit = window.question.edit
    edit.setFocus()
    qtbot.keyClicks(edit, "Erste Zeile")
    qtbot.keyClick(edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    qtbot.keyClicks(edit, "Zweite Zeile")
    assert edit.toPlainText() == "Erste Zeile\nZweite Zeile"
    assert edit.document().blockCount() == 2                                  # zwei Absätze
    assert "\u2028" not in edit.document().toRawText()                        # kein Unicode-Trenner
    assert edit.textCursor().blockNumber() == 1                               # Cursor in der neuen Zeile
    assert window._ask_task is None                                           # nichts wurde gesendet


def test_enter_and_ctrl_enter_send_but_shift_enter_does_not(make_window, qtbot):
    window = make_window([content("Eins."), content("Zwei.")])
    edit = window.question.edit
    for modifier in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ControlModifier):
        edit.setFocus()
        edit.setPlainText("Eine Frage")
        count = window.history_panel.count()
        qtbot.keyClick(edit, Qt.Key.Key_Return, modifier)
        qtbot.waitUntil(lambda: window.history_panel.count() == count + 1, timeout=5000)
    edit.setFocus()
    edit.setPlainText("Eine Frage")
    qtbot.keyClick(edit, Qt.Key.Key_Enter, Qt.KeyboardModifier.ShiftModifier)  # Ziffernblock-Enter
    assert edit.toPlainText().count("\n") == 1 and window.history_panel.count() == 2


def test_pasted_unicode_separators_become_real_lines(make_window):
    from PySide6.QtCore import QMimeData
    window = make_window()
    for edit in (window.question.edit, window.answer.edit):
        mime = QMimeData()
        mime.setText("eins\u2028zwei\u2029drei")
        edit.clear()
        edit.insertFromMimeData(mime)
        assert edit.toPlainText() == "eins\nzwei\ndrei" and edit.document().blockCount() == 3


def test_answer_field_shift_enter_also_makes_a_real_line(make_window, qtbot):
    window = make_window()
    edit = window.answer.edit
    edit.setFocus()
    qtbot.keyClicks(edit, "oben")
    qtbot.keyClick(edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    qtbot.keyClicks(edit, "unten")
    assert edit.document().blockCount() == 2 and "\u2028" not in edit.document().toRawText()


def test_answer_is_shown_one_sentence_per_line(make_window, qtbot):
    reply = ("Das Deutschlandticket kostet 63 Euro im Monat, zum Beispiel für den Nahverkehr. Es gilt seit "
             "dem 1. Januar 2026. Dr. Müller sagt, dass z. B. Studierende weniger zahlen! Stimmt das?\n\n"
             "- Erster Punkt\n- Zweiter Punkt")
    window = make_window([content(reply)])
    ask(window, qtbot)
    lines = window.answer.text().split("\n")
    assert lines[0].startswith("Das Deutschlandticket kostet 63 Euro im Monat")
    assert "Es gilt seit dem 1. Januar 2026." in lines                        # ordinale Zahl bleibt zusammen
    assert any(line.startswith("Dr. Müller sagt, dass z. B. Studierende") for line in lines)
    assert "Stimmt das?" in lines and "- Erster Punkt" in lines and "- Zweiter Punkt" in lines
    assert window.answer.edit.document().blockCount() == len(lines) >= 7
    assert all(len(line) <= 72 for line in lines)
    assert window.answer.edit.textCursor().position() == 0


def test_document_text_keeps_its_paragraphs_and_comment_prefix_still_works(make_window, qtbot):
    letter = ('Ich habe das Anschreiben erstellt. Es ist kurz und formell.\n<dokument titel="Brief">\n'
              'Sehr geehrte Damen und Herren, hiermit bewerbe ich mich. Ich freue mich auf Ihre Antwort. '
              'Mit freundlichen Grüßen\n</dokument>')
    window = make_window([content(letter)])
    ask(window, qtbot)
    text = window.answer.text()
    assert text.startswith("Ich habe das Anschreiben erstellt.\nEs ist kurz und formell.\n\nSehr geehrte")
    doc = window.answer.document_text()
    assert doc == ("Sehr geehrte Damen und Herren, hiermit bewerbe ich mich. Ich freue mich auf Ihre "
                   "Antwort. Mit freundlichen Grüßen")                       # unverändert, ein Absatz
    window.answer.load(text, "Ich habe das Anschreiben erstellt. Es ist kurz und formell.", True)
    assert window.answer.document_text() == doc                              # Verlauf mit rohem Kommentar
    assert window.answer.context_text() == doc
