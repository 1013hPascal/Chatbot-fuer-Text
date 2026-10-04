"""Chatbot für Text: lokaler, barrierefreier Schreibassistent. Start: python app.py"""
import logging
import multiprocessing
import sys

from PySide6.QtWidgets import QApplication

from core.config import Config, app_dir
from core.store import Store
from core.llm import create_backend
from ui.main_window import MainWindow


def main() -> int:
    logs = app_dir() / "logs"
    logs.mkdir(exist_ok=True)
    logging.basicConfig(filename=logs / "app.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = QApplication(sys.argv)
    app.setApplicationName("Chatbot für Text")
    cfg = Config.load()
    window = MainWindow(cfg, create_backend(cfg), Store())
    window.showMaximized()
    window.initial_focus()
    window.start_engine()
    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())


