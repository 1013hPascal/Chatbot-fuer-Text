"""Echtes Modell (Ollama nötig): pytest -m integration. Mit Internet: pytest -m "integration or internet"."""
import pytest
from docx import Document
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog

from core.llm import create_backend
from ui.announcer import announcer
from ui.main_window import MainWindow

pytestmark = pytest.mark.integration


@pytest.fixture
def real_window(qtbot, cfg, store):
    backend = create_backend(cfg)
    try:
        backend.start()
        if backend.missing_models():
            pytest.skip("Modell nicht installiert")
    except Exception as exc:
        pytest.skip(f"Ollama nicht verfügbar: {exc}")
    announcer.history.clear()
    cfg.beep_on_answer = False
    window = MainWindow(cfg, backend, store)
    qtbot.addWidget(window)
    window.show()
    window.start_engine()
    qtbot.waitUntil(lambda: window.engine_ready, timeout=120000)
    yield window
    backend.stop()


def ask(window, qtbot, text, timeout=300000):
    window.question.edit.setFocus()
    window.question.edit.setPlainText(text)
    count = window.history_panel.count()
    qtbot.keyClick(window.question.edit, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.history_panel.count() == count + 1
                    or window._ask_task is None, timeout=timeout)


def test_gpu_is_used(real_window):
    assert any("GPU: " in t for t, _ in announcer.history), announcer.history


def test_letter_lands_in_answer_field_and_word_file(real_window, qtbot, monkeypatch, tmp_path):
    window = real_window
    window.cfg.web_search = False
    ask(window, qtbot, "Schreibe ein kurzes Anschreiben für eine Bewerbung als Gärtnerin. "
                       "Ich heiße Berta Klein. Gib mir es auch als Word-Datei.")
    assert window.answer.is_doc, window.answer.text()
    assert "Berta Klein" in window.answer.document_text()
    assert "<dokument" not in window.answer.text() and "*" not in window.answer.text()
    assert "Text kopieren" in window.actions.texts()
    assert any(x.startswith("Word-Dokument speichern") for x in window.actions.texts())
    assert QApplication.focusWidget() is window.answer.edit
    target = tmp_path / "Bewerbung.docx"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    window._save_word()
    body = "\n".join(p.text for p in Document(str(target)).paragraphs)
    assert "Berta Klein" in body and "Ich habe" not in body


def test_model_reads_files_in_a_granted_folder(real_window, qtbot, tmp_path):
    window = real_window
    window.cfg.web_search = False
    root = tmp_path / "Unterlagen"
    (root / "Verträge").mkdir(parents=True)
    (root / "Verträge" / "Mietvertrag.txt").write_text(
        "Mietvertrag. Die monatliche Kaltmiete beträgt 850 Euro. Die Kaution beträgt 2550 Euro. "
        "Die Kündigungsfrist beträgt drei Monate.", encoding="utf-8")
    (root / "Verträge" / "Handyvertrag.txt").write_text(
        "Handyvertrag. Der Tarif kostet 19,99 Euro im Monat. Laufzeit 24 Monate.", encoding="utf-8")
    (root / "Einkaufsliste.txt").write_text("Milch, Brot, Eier, Butter.", encoding="utf-8")
    window.session.folders.grant(root)
    window._meta.append({"type": "folder", "path": str(root)})
    ask(window, qtbot, "Wie hoch ist die Kaution laut meinem Mietvertrag?")
    assert "2550" in window.answer.text(), window.answer.text()
    assert "Gelesene Dateien:" in window.answer.text() and "Mietvertrag.txt" in window.answer.text()
    assert any("Datei" in t for t, _ in announcer.history)


@pytest.mark.internet
def test_current_question_is_researched_on_the_web(real_window, qtbot):
    window = real_window
    window.cfg.web_search = True
    ask(window, qtbot, "Wer ist aktuell Bundeskanzler von Deutschland? Bitte recherchiere.")
    assert "Merz" in window.answer.text(), window.answer.text()
    assert "Quellen aus dem Internet: http" in window.answer.text()
    assert any("Internetrecherche" in t for t, _ in announcer.history)
