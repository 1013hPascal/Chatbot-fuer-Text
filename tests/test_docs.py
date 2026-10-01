"""Tests für PDFs und Bilder: Bibliothek, Werkzeuge für das Modell, PDF-Prüfung, Zeitmessung."""
import base64
import threading

import pymupdf
import pytest

from core import pdfcheck, pdfs, websearch
from core.conversation import ChatSession, format_timing
from core.files import FileReadError
from core.llm import ChatChunk, ToolCall
from core.tools import ToolBox
from tests.conftest import FakeBackend, content, tool_call

CONTRACT = ("Der Mietvertrag beginnt am 1. Mai. Die Kaution beträgt drei Monatsmieten. "
            "Kündigung ist mit drei Monaten Frist möglich.")


def make_pdf(path, pages, size=(595, 842)):
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page(width=size[0], height=size[1])
        if text:
            page.insert_textbox(pymupdf.Rect(72, 72, size[0] - 72, size[1] - 72), text, fontsize=11)
    doc.save(str(path))
    return path


def make_scan(path, pages=1):
    """PDF, dessen Seiten nur aus einem Bild bestehen (Scan ohne Text)."""
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 300), False)
    pix.set_rect(pix.irect, (200, 200, 200))
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_image(page.rect, pixmap=pix)
    doc.save(str(path))
    return path


def make_image(path, width=80, height=60):
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
    pix.set_rect(pix.irect, (255, 0, 0))
    pix.save(str(path))
    return path


@pytest.fixture
def contract_pdf(tmp_path):
    return make_pdf(tmp_path / "Mietvertrag.pdf", [CONTRACT, "Nebenkosten werden jährlich abgerechnet."])


# -- Bibliothek --------------------------------------------------------------------------------
def test_ranges_formats_page_lists():
    assert pdfs.ranges([1, 2, 3, 7]) == "1 bis 3, 7"
    assert pdfs.ranges([5]) == "5"
    assert pdfs.ranges([4, 5]) == "4, 5"
    assert pdfs.ranges([9, 3, 4, 5, 6, 12]) == "3 bis 6, 9, 12"


def test_load_pdf_reads_text_per_page_and_flags_sparse_pages(tmp_path):
    path = make_pdf(tmp_path / "a.pdf", ["Text " * 100, "", "Kurz"])
    doc = pdfs.load(path)
    assert doc.kind == "pdf" and [p.number for p in doc.pages] == [1, 2, 3]
    assert doc.pages[0].text.startswith("Text Text") and doc.sparse_pages == [2, 3]
    assert doc.chars > 0 and "[Seite 1]" in doc.inline_text() and "[Seite 2]" not in doc.inline_text()


def test_load_errors_are_file_read_errors(tmp_path):
    broken = tmp_path / "kaputt.pdf"
    broken.write_bytes(b"kein pdf")
    with pytest.raises(FileReadError):
        pdfs.load(broken)
    with pytest.raises(FileReadError):
        pdfs.load(tmp_path / "gibt-es-nicht.pdf")


def test_render_gives_png_for_pdf_pages_and_jpeg_for_images(tmp_path):
    pdf = pdfs.load(make_pdf(tmp_path / "a.pdf", ["Seite eins"]))
    assert pdf.render(1)[:8] == b"\x89PNG\r\n\x1a\n"
    image = pdfs.load(make_image(tmp_path / "b.png", 4000, 3000))
    data = image.render(1)
    assert data[:2] == b"\xff\xd8"
    pix = pymupdf.Pixmap(data)
    assert max(pix.width, pix.height) <= pdfs.MAX_IMAGE_SIDE + 1            # verkleinert
    with pytest.raises(FileReadError, match="keine Seite 5"):
        pdf.render(5)


def test_library_find_by_name_prefix_and_ambiguity(tmp_path):
    lib = pdfs.Library()
    for name in ("Mietvertrag.pdf", "Mietvertrag alt.pdf", "Anzeige.pdf"):
        lib.add(make_pdf(tmp_path / name, ["x"]))
    assert lib.find("anzeige.PDF").name == "Anzeige.pdf"
    assert lib.find("Anz").name == "Anzeige.pdf"                             # eindeutiger Anfang
    with pytest.raises(FileReadError, match="nicht eindeutig"):
        lib.find("Miet")
    with pytest.raises(FileReadError, match="Vorhanden: "):
        lib.find("gibt es nicht")


def test_library_read_limits_size_and_says_where_to_continue(tmp_path):
    lib = pdfs.Library()
    lib.add(make_pdf(tmp_path / "lang.pdf", [("Wort " * 300).strip()] * 8))   # je Seite etwa 1500 Zeichen
    doc, text, first, last = lib.read("lang.pdf", 1, 8)
    assert first == 1 and 1 < last < 8 and len(text) < pdfs.MAX_READ_CHARS + 400
    assert f"Weiter ab Seite {last + 1}" in text
    _, more, first2, last2 = lib.read("lang.pdf", last + 1, 8)
    assert first2 == last + 1 and last2 > last
    _, page, a, b = lib.read("lang.pdf", 99, 99)                              # außerhalb: letzte Seite
    assert a == b == 8 and "Seite 8 von 8" in page


def test_library_read_marks_empty_and_sparse_pages(tmp_path):
    lib = pdfs.Library()
    lib.add(make_pdf(tmp_path / "a.pdf", ["", "Nur ein Satz."]))
    _, text, _, _ = lib.read("a.pdf", 1, 2)
    assert "kein Text auf dieser Seite" in text and "seite_ansehen" in text
    assert "wenig Text" in text


def test_library_search_ranks_pages_and_ignores_umlauts_and_endings(tmp_path):
    lib = pdfs.Library()
    lib.add(make_pdf(tmp_path / "v.pdf", ["Irgendwas anderes.", CONTRACT, "Kaution Kaution und Kündigung."]))
    hits = lib.search("Kaution Kuendigung")
    assert [h.page for h in hits][:2] == [3, 2]                              # beide Wörter, Seite 3 öfter
    assert "Kaution" in hits[0].excerpt
    assert [h.page for h in lib.search("Monatsmiete")] == [2]                # Endung -n egal
    assert lib.search("zzzzzz") == [] and lib.search("a") == []
    assert lib.search("Kaution", "v.pdf")[0].doc == "v.pdf"


def test_outline_lists_scans_sparse_pages_and_page_heads(tmp_path):
    lib = pdfs.Library()
    lib.add(make_pdf(tmp_path / "lang.pdf", [f"Kapitel {i}\n" + "Text " * 200 for i in range(1, 4)]))
    lib.add(make_scan(tmp_path / "scan.pdf", 2))
    lib.add(make_image(tmp_path / "foto.png"))
    outline = lib.outline()
    assert "lang.pdf: PDF, 3 Seiten, nur über Werkzeuge lesbar" in outline
    assert "Seite 2: Kapitel 2" in outline
    assert "scan.pdf: PDF, 2 Seiten" in outline and "Seiten mit wenig oder ohne Text" in outline
    assert "foto.png: Bild" in outline
    lib.inline.add(str(tmp_path / "lang.pdf"))
    assert "Text steht schon in dieser Nachricht" in lib.outline()


# -- Dateien im Chat: Modus je nach Art und Länge ------------------------------------------------
def test_add_file_modes_and_messages(cfg, tmp_path, contract_pdf):
    session = ChatSession(cfg, FakeBackend(cfg))
    note = tmp_path / "notiz.txt"
    note.write_text("Ein kurzer Text.", encoding="utf-8")
    assert session.add_file(str(note)).message() == "notiz.txt hinzugefügt, 3 Wörter."
    added = session.add_file(str(contract_pdf))
    assert added.mode == "pdf_inline" and added.pages == 2
    assert "Mietvertrag.pdf hinzugefügt, 2 Seiten, " in added.message()
    assert "Seiten mit wenig Text" in added.message()                         # Seite 2 ist kurz
    scan = session.add_file(str(make_scan(tmp_path / "scan.pdf", 3)))
    assert scan.mode == "pdf_scan" and "3 Seiten ohne Text (Scan)" in scan.message()
    image = session.add_file(str(make_image(tmp_path / "foto.png")))
    assert image.mode == "image" and "sieht es sich an" in image.message()
    cfg.max_attachment_chars = 500
    big = session.add_file(str(make_pdf(tmp_path / "gross.pdf", ["Wort " * 400])))
    assert big.mode == "pdf_tools" and "gezielt Seiten" in big.message()


def test_inline_pdf_is_in_the_prompt_with_page_marks_but_big_pdf_only_in_the_outline(cfg, tmp_path):
    cfg.max_attachment_chars = 3000
    session = ChatSession(cfg, FakeBackend(cfg))
    session.add_file(str(make_pdf(tmp_path / "klein.pdf", [CONTRACT])))
    session.add_file(str(make_pdf(tmp_path / "gross.pdf", [f"Seite {i} " + "Inhalt " * 150 for i in range(1, 6)])))
    system = session.build_messages("Frage", "")[0]["content"]
    assert "[Seite 1]" in system and "Kaution" in system                       # klein: ganzer Text
    assert "gross.pdf: PDF, 5 Seiten, nur über Werkzeuge lesbar" in system
    assert "Seite 3: Seite 3 Inhalt" in system and "Inhalt " * 30 not in system   # nur Seitenanfänge
    assert "dokument_lesen" in system and "seite_ansehen" in system


def test_remove_and_has_file_ignore_slash_style(cfg, tmp_path, contract_pdf):
    session = ChatSession(cfg, FakeBackend(cfg))
    session.add_file(str(contract_pdf))
    assert session.has_file(str(contract_pdf).replace("\\", "/"))
    session.remove_file(str(contract_pdf).replace("\\", "/"))
    assert not session.has_file(str(contract_pdf)) and session.attachments == [] and not session.docs
    session.add_file(str(contract_pdf))
    session.reset()
    assert not session.docs and session.attachments == []


def test_broken_and_password_files_raise_file_read_error(cfg, tmp_path):
    session = ChatSession(cfg, FakeBackend(cfg))
    bad = tmp_path / "kaputt.pdf"
    bad.write_bytes(b"nichts")
    with pytest.raises(FileReadError):
        session.add_file(str(bad))
    assert not session.docs


def test_model_without_tools_gets_the_start_of_long_pdfs_and_no_tool_specs(cfg, tmp_path):
    cfg.max_attachment_chars = 2000
    backend = FakeBackend(cfg, [content("Antwort.")])
    backend.caps = {"completion", "vision"}
    session = ChatSession(cfg, backend)
    session.add_file(str(make_pdf(tmp_path / "gross.pdf", ["Anfang " + "Inhalt " * 200] * 3)))
    system = session.build_messages("Frage", "")[0]["content"]
    assert "Anfang Inhalt" in system and "[gekürzt]" in system and "dokument_lesen" not in system
    assert "lange PDFs" in session.limits_note()
    session.ask("Frage", "")
    assert backend.calls[0]["tools"] is None


# -- Werkzeuge im Gespräch -----------------------------------------------------------------------
def big_pdf_session(cfg, tmp_path, script):
    cfg.max_attachment_chars = 300
    backend = FakeBackend(cfg, script)
    session = ChatSession(cfg, backend)
    session.add_file(str(make_pdf(tmp_path / "gross.pdf",
                                  ["Einleitung. " * 60, "Hier steht die Kaution: drei Monatsmieten. " * 5,
                                   "Schluss. " * 60])))
    return session, backend


def test_model_searches_then_reads_a_page_of_a_long_pdf(cfg, tmp_path):
    cfg.web_search = False
    session, backend = big_pdf_session(cfg, tmp_path, [
        tool_call("dokument_suchen", begriff="Kaution"),
        tool_call("dokument_lesen", datei="gross.pdf", von=2),
        content("Die Kaution beträgt drei Monatsmieten (Seite 2).")])
    statuses = []
    result = session.ask("Wie hoch ist die Kaution?", "", on_status=statuses.append)
    assert [t["function"]["name"] for t in backend.calls[0]["tools"]] == [
        "dokument_lesen", "dokument_suchen", "pdf_pruefen", "seite_ansehen"]
    found = backend.calls[1]["messages"][-1]["content"]
    assert "gross.pdf, Seite 2" in found and "Kaution" in found
    read = backend.calls[2]["messages"][-1]["content"]
    assert "--- Seite 2 von 3 ---" in read and "drei Monatsmieten" in read
    assert "Dokumente werden durchsucht: Kaution" in statuses
    assert "Seiten werden gelesen: gross.pdf" in statuses
    assert result.answer.endswith("Gelesene Dateien: gross.pdf, Seite 2")
    assert [name for name, _ in result.timing["tools"]] == ["dokument_suchen", "dokument_lesen"]


def test_model_asks_to_see_an_image_and_gets_it_in_the_next_message(cfg, tmp_path):
    cfg.max_attachment_chars = 0
    backend = FakeBackend(cfg, [tool_call("seite_ansehen", datei="foto.png"), content("Es ist ein rotes Bild.")])
    session = ChatSession(cfg, backend)
    session.add_file(str(make_image(tmp_path / "foto.png")))
    statuses = []
    result = session.ask("Welche Farbe hat das Foto?", "", on_status=statuses.append)
    assert len(backend.calls) == 2                                            # kein zweiter Bildaufruf
    messages = backend.calls[1]["messages"]
    assert messages[-2]["role"] == "tool" and "liegt als Bild in der nächsten Nachricht" in messages[-2]["content"]
    last = messages[-1]
    assert last["role"] == "user" and len(last["images"]) == 1
    assert "Hier ist: foto.png" in last["content"] and "Welche Farbe hat das Foto?" in last["content"]
    assert "Erfinde keine Namen" in last["content"]
    assert "Seite wird angesehen: foto.png, Seite 1" in statuses
    assert result.answer.endswith("Gelesene Dateien: foto.png")
    assert base64.b64decode(last["images"][0])[:2] == b"\xff\xd8"             # JPEG
    assert all("images" not in m for m in session.build_messages("Neu", "")) # nicht im Gedächtnis


def test_pdf_pages_come_as_png_and_several_pages_share_one_message(cfg, tmp_path):
    two = [ChatChunk("tool_call", tool=ToolCall("seite_ansehen", {"datei": "scan.pdf", "seite": 1})),
           ChatChunk("tool_call", tool=ToolCall("seite_ansehen", {"datei": "scan.pdf", "seite": 2})),
           ChatChunk("tool_call", tool=ToolCall("seite_ansehen", {"datei": "scan.pdf", "seite": 2}))]
    backend = FakeBackend(cfg, [two, content("Fertig.")])
    session = ChatSession(cfg, backend)
    session.add_file(str(make_scan(tmp_path / "scan.pdf", 2)))
    session.ask("Lies beide Seiten", "")
    last = backend.calls[1]["messages"][-1]
    assert len(last["images"]) == 2 and "sind: scan.pdf, Seite 1; scan.pdf, Seite 2" in last["content"]
    assert base64.b64decode(last["images"][0])[:8] == b"\x89PNG\r\n\x1a\n"
    tools = [m["content"] for m in backend.calls[1]["messages"] if m["role"] == "tool"]
    assert "schon als Bild" in tools[2]                                       # doppelt angefordert


def test_at_most_three_images_per_step(cfg, tmp_path):
    calls = [ChatChunk("tool_call", tool=ToolCall("seite_ansehen", {"datei": "scan.pdf", "seite": n}))
             for n in (1, 2, 3, 4)]
    backend = FakeBackend(cfg, [calls, content("Fertig.")])
    session = ChatSession(cfg, backend)
    session.add_file(str(make_scan(tmp_path / "scan.pdf", 4)))
    session.ask("Alles ansehen", "")
    assert len(backend.calls[1]["messages"][-1]["images"]) == 3
    assert "Höchstens 3" in [m for m in backend.calls[1]["messages"] if m["role"] == "tool"][3]["content"]


def test_model_without_vision_gets_no_look_tool(cfg, tmp_path):
    backend = FakeBackend(cfg, [content("Antwort.")])
    backend.caps = {"tools", "thinking"}
    session = ChatSession(cfg, backend)
    session.add_file(str(make_scan(tmp_path / "scan.pdf")))
    session.ask("Was steht da?", "")
    assert "seite_ansehen" not in [t["function"]["name"] for t in backend.calls[0]["tools"]]
    assert "seite_ansehen" not in backend.calls[0]["messages"][0]["content"]


def test_document_tool_errors_go_to_the_model(cfg, tmp_path, contract_pdf):
    backend = FakeBackend(cfg, [tool_call("dokument_lesen", datei="gibt-es-nicht.pdf", von=1),
                                tool_call("seite_ansehen", datei="Mietvertrag.pdf", seite=9),
                                tool_call("pdf_pruefen", datei="Mietvertrag.pdf"), content("Fertig.")])
    session = ChatSession(cfg, backend)
    session.add_file(str(contract_pdf))
    session.ask("Frage", "")
    assert "Fehler: Dokument nicht gefunden" in backend.calls[1]["messages"][-1]["content"]
    assert "Fehler: Mietvertrag.pdf hat keine Seite 9" in backend.calls[2]["messages"][-1]["content"]
    assert "Prüfung von Mietvertrag.pdf" in backend.calls[3]["messages"][-1]["content"]


def test_independent_tool_calls_of_one_step_run_at_the_same_time(cfg):
    barrier = threading.Barrier(2)

    def search(query):
        barrier.wait(timeout=3)                    # klappt nur, wenn beide gleichzeitig laufen
        return [{"title": query, "url": f"https://a.example/{query}", "snippet": "s"}]
    two = [ChatChunk("tool_call", tool=ToolCall("internet_suche", {"anfrage": "eins"})),
           ChatChunk("tool_call", tool=ToolCall("internet_suche", {"anfrage": "zwei"}))]
    backend = FakeBackend(cfg, [two, content("Fertig.")])
    statuses = []
    result = ChatSession(cfg, backend, ToolBox(search_fn=search)).ask("Frage", "", on_status=statuses.append)
    tools = [m for m in backend.calls[1]["messages"] if m["role"] == "tool"]
    assert len(tools) == 2 and "eins" in tools[0]["content"] and "zwei" in tools[1]["content"]   # Reihenfolge bleibt
    assert "Internetrecherche: eins" in statuses and "Internetrecherche: zwei" in statuses
    assert result.answer.startswith("Fertig.")


def test_cancel_stops_before_the_next_sequential_tool(cfg, tmp_path):
    from core.llm import Cancelled
    cancel = threading.Event()
    cancel.set()
    backend = FakeBackend(cfg, [tool_call("seite_ansehen", datei="foto.png")])
    session = ChatSession(cfg, backend)
    session.add_file(str(make_image(tmp_path / "foto.png")))
    with pytest.raises(Cancelled):
        session.ask("Frage", "", cancel=cancel)


# -- Zeitmessung ---------------------------------------------------------------------------------
def test_format_timing_summarizes_calls_and_tools():
    text = format_timing({"total_s": 12.34, "calls": [
        {"prefill_tokens": 2000, "prefill_s": 3.0, "gen_tokens": 50, "gen_s": 4.5, "load_s": 0.0},
        {"prefill_tokens": 300, "prefill_s": 0.5, "gen_tokens": 40, "gen_s": 2.0, "load_s": 6.2}],
        "tools": [("internet_suche", 1.8)]})
    assert text.startswith("gesamt 12.3 s")
    assert "2000 Token einlesen 3.0 s, 50 Token schreiben 4.5 s" in text and "laden 6.2 s" in text
    assert "Werkzeuge internet_suche 1.8 s" in text


def test_ollama_backend_collects_call_times_and_passes_images_through(cfg):
    import json

    import httpx
    from core.ollama_backend import OllamaBackend
    seen = {}

    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion", "vision"]})
        seen["body"] = json.loads(request.content)
        line = {"message": {"content": "Ein Bild."}, "done": True, "load_duration": 2_000_000_000,
                "prompt_eval_count": 700, "prompt_eval_duration": 1_500_000_000,
                "eval_count": 30, "eval_duration": 3_000_000_000}
        return httpx.Response(200, content=(json.dumps(line) + "\n").encode())
    backend = OllamaBackend(cfg)
    backend._http = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))
    message = {"role": "user", "content": "Was ist das?", "images": ["QUJD"]}
    assert [c.text for c in backend.chat_stream([message])] == ["Ein Bild."]
    assert seen["body"]["messages"][0]["images"] == ["QUJD"] and "tools" not in seen["body"]
    assert backend.take_stats() == [{"load_s": 2.0, "prefill_tokens": 700, "prefill_s": 1.5,
                                     "gen_tokens": 30, "gen_s": 3.0}]
    assert backend.take_stats() == []


def test_search_results_are_shortened_to_save_reading_time(cfg):
    long = "Wort " * 200
    box = ToolBox(search_fn=lambda q: [{"title": "T", "url": "https://a.example", "snippet": long}])
    text = box.run(ToolCall("internet_suche", {"anfrage": "x"}))
    assert len(text) < 500 and text.rstrip().endswith("…")


# -- PDF-Prüfung ---------------------------------------------------------------------------------
def defective_pdf(path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Normale Zeile im Rand.", fontsize=12)
    page.insert_text((450, 150), "Dieser Satz ist viel zu lang und ragt rechts über die Seite hinaus.", fontsize=12)
    page.insert_text((72, 200), "Überlappung eins", fontsize=14)
    page.insert_text((80, 205), "Überlappung zwei", fontsize=14)
    page.insert_text((72, 260), "Winzige Schrift hier", fontsize=4)
    page.insert_text((5, 300), "Am Rand links", fontsize=12)
    doc.new_page(width=400, height=500).insert_text((72, 100), "Andere Größe", fontsize=12)
    doc.new_page()
    doc.save(str(path))
    return path


def test_pdfcheck_finds_measurable_layout_defects(tmp_path):
    pages, findings = pdfcheck.check_pdf(defective_pdf(tmp_path / "fehler.pdf"))
    assert pages == 3
    by_page = {(f.page, f.severity): f.text for f in findings}
    assert "rechts über die Seite hinaus" in by_page[(1, "Fehler")] or any(
        "rechts über die Seite hinaus" in f.text for f in findings if f.page == 1)
    texts = " | ".join(f.text for f in findings if f.page == 1)
    assert "rechts über die Seite hinaus" in texts and "überlappt sich" in texts
    assert "weniger als 5 mm" in texts and "Sehr kleine Schrift" in texts
    assert any(f.page == 3 and "leer" in f.text for f in findings)
    assert any(f.page == 0 and "unterschiedliche Größen" in f.text for f in findings)
    assert any(f.page == 0 and "nicht getaggt" in f.text for f in findings)
    assert [f.page for f in findings] == sorted(f.page for f in findings)   # Dokument zuerst, dann Seiten


def test_pdfcheck_clean_page_has_only_accessibility_findings(tmp_path):
    pages, findings = pdfcheck.check_pdf(make_pdf(tmp_path / "sauber.pdf", [CONTRACT]))
    assert [f for f in findings if f.page] == []
    assert {f.severity for f in findings} <= {"Hinweis", "Warnung"}
    report = pdfcheck.format_report("sauber.pdf", pages, findings)
    assert "keine messbaren Layoutfehler" in report and "Prüfung von sauber.pdf: 1 Seite(n)" in report


def test_pdfcheck_scan_is_not_flagged_for_its_invisible_text_layer(tmp_path):
    path = tmp_path / "scan.pdf"
    make_scan(path)
    doc = pymupdf.open(str(path))
    doc[0].insert_text((5, 5), "Unsichtbarer OCR Text der ragt über den Rand hinaus ohne Ende", fontsize=12)
    doc.saveIncr()
    doc.close()
    pages, findings = pdfcheck.check_pdf(path)
    assert [f.severity for f in findings if f.page == 1] == ["Hinweis"]
    assert any("keinen Text" in f.text for f in pdfcheck.check_pdf(make_scan(tmp_path / "s2.pdf"))[1])


def test_pdfcheck_errors(tmp_path):
    bad = tmp_path / "kaputt.pdf"
    bad.write_bytes(b"kein pdf")
    with pytest.raises(FileReadError):
        pdfcheck.check_pdf(bad)
    with pytest.raises(FileReadError):
        pdfcheck.check_pdf(tmp_path / "gibt-es-nicht.pdf")


def test_pdfcheck_reads_metadata_for_screenreaders(tmp_path):
    path = tmp_path / "titel.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "Hallo Welt", fontsize=12)
    doc.set_metadata({"title": "Mein Titel"})
    doc.save(str(path))
    _, findings = pdfcheck.check_pdf(path)
    texts = " ".join(f.text for f in findings if f.page == 0)
    assert "keinen Titel" not in texts and "Dokumentsprache" in texts


def test_check_readable_accepts_scans_and_images_but_not_broken_files(tmp_path):
    assert pdfs.check_readable(make_scan(tmp_path / "s.pdf")) == "s.pdf"
    assert pdfs.check_readable(make_image(tmp_path / "b.png")) == "b.png"
    (tmp_path / "x.exe").write_bytes(b"x")
    with pytest.raises(FileReadError, match="nicht unterstützt"):
        pdfs.check_readable(tmp_path / "x.exe")


def test_default_search_still_uses_the_searcher(cfg):
    assert isinstance(ChatSession(cfg, FakeBackend(cfg)).toolbox._search, websearch.Searcher)

# -- Planer in Code: Suche vor dem ersten Modellaufruf ------------------------------------------
@pytest.mark.parametrize("question", [
    "Was kostet das Deutschlandticket aktuell?", "Wie wird das Wetter morgen in Freiburg?",
    "Wer ist aktuell Bundeskanzler?", "Recherchiere bitte zum Mindestlohn.",
    "Welche Öffnungszeiten hat das Bürgeramt?", "Gibt es Neuigkeiten im Internet zu NVDA?"])
def test_router_recognizes_clear_web_questions(question):
    from core import router
    assert router.wants_web_search(question)


@pytest.mark.parametrize("question", [
    "Schreibe ein Anschreiben für eine Bewerbung.", "Erkläre den Unterschied zwischen dass und das.",
    "Schreibe ein Gedicht über das Wetter.", "Was ist ein Sprachkurs?", "Hallo!",
    "Wie funktioniert ein Kurs im Bogen?"])
def test_router_leaves_other_questions_to_the_model(question):
    from core import router
    assert not router.wants_web_search(question)


def test_router_stays_out_when_text_or_material_is_there():
    from core import router
    assert not router.wants_web_search("Was kostet das aktuell?", has_text=True)
    assert not router.wants_web_search("Was kostet das aktuell?", has_material=True)
    assert router.search_query("  Was   kostet\nes?  ") == "Was kostet es?"
    assert len(router.search_query("x " * 500)) <= 200


def prefetch_session(cfg, script):
    cfg.web_search = True
    backend = FakeBackend(cfg, script)
    box = ToolBox(search_fn=lambda q: [{"title": "Ticket", "url": "https://t.example/preis",
                                        "snippet": f"63 Euro (Suche: {q})"}])
    return ChatSession(cfg, backend, box), backend


def test_clear_web_question_is_searched_before_the_first_model_call(cfg):
    session, backend = prefetch_session(cfg, [content("Das Ticket kostet 63 Euro.")])
    statuses = []
    result = session.ask("Was kostet das Deutschlandticket aktuell?", "", on_status=statuses.append)
    assert len(backend.calls) == 1                                            # eine Modellrunde gespart
    first = backend.calls[0]["messages"]
    assert first[-2]["role"] == "assistant" and first[-2]["tool_calls"][0]["function"]["name"] == "internet_suche"
    assert first[-1]["role"] == "tool" and "63 Euro (Suche: Was kostet das Deutschlandticket aktuell?)" in first[-1]["content"]
    assert backend.calls[0]["tools"]                                          # das Modell darf weiter suchen
    assert "Internetrecherche: Was kostet das Deutschlandticket aktuell?" in statuses
    assert result.web_sources == ["https://t.example/preis"]
    assert result.answer.endswith("Quellen aus dem Internet: https://t.example/preis")
    assert [name for name, _ in result.timing["tools"]] == ["internet_suche"]


def test_prefetch_can_be_switched_off_and_is_skipped_without_web_or_with_material(cfg, tmp_path):
    session, backend = prefetch_session(cfg, [tool_call("internet_suche", anfrage="x"), content("Ok.")])
    cfg.web_prefetch = False
    session.ask("Was kostet das Deutschlandticket aktuell?", "")
    assert len(backend.calls) == 2                                            # das Modell entscheidet selbst
    session, backend = prefetch_session(cfg, [content("Ok.")])
    cfg.web_prefetch = True
    session.ask("Schreibe ein Gedicht über das Wetter.", "")
    session.ask("Was kostet das aktuell?", "Ein Textentwurf im Antwortfeld.")
    session.add_file(str(make_pdf(tmp_path / "a.pdf", ["Text " * 50])))
    session.ask("Was kostet das aktuell?", "")
    assert all(m["role"] != "tool" for call in backend.calls for m in call["messages"])
    cfg.web_search = False
    session.docs.clear()
    session.attachments.clear()
    session.ask("Was kostet das Deutschlandticket aktuell?", "")
    assert all(m["role"] != "tool" for m in backend.calls[-1]["messages"])


def test_failed_prefetch_search_is_reported_to_the_model_not_raised(cfg):
    cfg.web_search = True

    def failing(_):
        raise websearch.WebError("Keine Verbindung")
    backend = FakeBackend(cfg, [content("Ich konnte nicht suchen.")])
    result = ChatSession(cfg, backend, ToolBox(search_fn=failing)).ask("Wetter in Freiburg?", "")
    assert "Fehler: Keine Verbindung" in backend.calls[0]["messages"][-1]["content"]
    assert result.answer.startswith("Ich konnte nicht suchen.")
