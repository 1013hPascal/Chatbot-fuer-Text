"""Probelauf mit dem echten Modell: Anschreiben, Änderung, Word-Wunsch, Internetfrage, Nachdenken.

Aufruf:  python scripts/try_chat.py [--model NAME] [--no-web]
Zeigt je Szenario die Zeit, die Antwort und den Textentwurf. Zum Vergleichen von Modellen.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import Config  # noqa: E402
from core.conversation import ChatSession, format_timing  # noqa: E402
from core.llm import create_backend  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model")
    parser.add_argument("--no-web", action="store_true")
    args = parser.parse_args()

    cfg = Config.load()
    if args.model:
        cfg.chat_model = args.model
    backend = create_backend(cfg)
    backend.start()
    try:
        print("Fehlende Modelle:", backend.missing_models() or "keine")
        t = time.perf_counter()
        backend.warmup()
        print(f"Modell: {cfg.chat_model} | Aufwärmen {time.perf_counter() - t:.1f} s | "
              f"{backend.device_status().text}")

        session = ChatSession(cfg, backend)
        document = ""

        def step(title: str, question: str, **settings) -> None:
            nonlocal document
            for key, value in settings.items():
                setattr(cfg, key, value)
            statuses: list[str] = []
            t = time.perf_counter()
            result = session.ask(question, document, on_status=statuses.append)
            seconds = time.perf_counter() - t
            if result.doc_text is not None:
                document = result.doc_text
            print(f"\n=== {title} ({seconds:.1f} s; think={cfg.thinking}, web={cfg.web_search}, "
                  f"lang={cfg.long_answers}) ===")
            print("Status:", " > ".join(dict.fromkeys(statuses)) or "-")
            print("Zeiten:", format_timing(result.timing))
            print("ANTWORT:", result.answer)
            if result.doc_text is not None:
                print(f"TEXTENTWURF [{result.doc_title}]:\n{result.doc_text}")
            if result.word_filename is not None:
                print("WORD-DOWNLOAD angeboten:", result.word_filename)

        cfg.web_search, cfg.thinking, cfg.long_answers = False, False, False
        step("1 Anschreiben", "Schreibe ein kurzes Anschreiben für eine Bewerbung als "
             "Buchhalterin bei der Firma Müller GmbH in Freiburg. Ich heiße Anna Weiß.")
        step("2 Änderung", "Mach es kürzer und formeller.")
        step("3 Word-Wunsch", "Gib mir das bitte als Word-Datei zum Herunterladen.")
        step("4 Einfache Frage kurz", "Was ist der Unterschied zwischen dass und das?")
        step("5 Lange Antwort", "Was ist der Unterschied zwischen dass und das?", long_answers=True)
        step("6 Nachdenken", "Ein Zug fährt um 9:15 Uhr ab und braucht 2 Stunden und 50 Minuten. "
             "Wann kommt er an, und wie lange ist er unterwegs in Minuten?",
             long_answers=False, thinking=True)
        if not args.no_web:
            step("7 Internet", "Wer ist aktuell Bundeskanzler von Deutschland? Bitte recherchiere.",
                 thinking=False, web_search=True)
    finally:
        backend.stop()


if __name__ == "__main__":
    main()
