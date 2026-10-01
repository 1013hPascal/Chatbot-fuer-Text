# Benutzte Tools: Chatbot für Text

Stand: 21.09.2026. Zwei Abschnitte: KI Tools (Modelle und Dienste, die etwas "verstehen") und Algorithmen (feste Regeln im Programmcode, ohne KI).

# KI Tools

## Sprachmodelle (im Menü Einstellungen, Modell wählbar)

| Modell | Größe | Kann | Wo eingestellt |
|---|---|---|---|
| gemma4:12b (über Ollama), Standard | 7,6 GB | Alles: Antworten, Texte schreiben, Internetsuche, Seiten lesen, Ordner und PDFs lesen, Bilder ansehen, Nachdenken | `core/config.py`: `DEFAULT_CHAT_MODEL`, Auswahlliste `AVAILABLE_MODELS` |
| qwen2.5vl:7b (über Ollama), wählbar | 6,0 GB | Antworten und Texte schreiben. Keine Werkzeuge (kein Internet, keine Ordner, keine PDF-Suche), kein Nachdenken. Sieht Bilder, aber ohne Werkzeuge kann es sie nicht anfordern. Die App sagt das an. | dieselbe Liste |

Die App braucht immer nur das gewählte Modell. Beim Wechsel wird das alte aus dem Arbeitsspeicher genommen. Weitere Modelle: in `AVAILABLE_MODELS` eintragen.

Herunterladen: `ollama pull gemma4:12b` und `ollama pull qwen2.5vl:7b`

## Laufzeit für die Modelle

| Tool | Version | Wofür |
|---|---|---|
| Ollama | 0.31.1 | Startet und betreibt die Modelle lokal, über Vulkan auf der Intel Arc 140V. Die App startet es selbst (`core/engine.py`). |

## Suchdienste (liefern nur Treffer, die Antwort schreibt das Sprachmodell)

| Dienst | Wofür | Bemerkung |
|---|---|---|
| Tavily | Internetsuche, wenn ein Schlüssel eingetragen ist (Einstellungen, Tavily-Schlüssel) | 1.000 Credits im Monat gratis. Längere Auszüge, im Test nicht besser und nicht schneller als DuckDuckGo. |
| DuckDuckGo (Paket ddgs) | Internetsuche ohne Schlüssel, und Rückfall, wenn Tavily nicht geht | Kostenlos, inoffiziell ausgelesen. |

## Getestet und nicht benutzt

| Modell | Ergebnis | Datum |
|---|---|---|
| qwen3:8b | schnell, aber ohne Internetsuche und mit falscher Antwort aus dem Gedächtnis | Sept. 2026 |
| qwen3.5:9b | schnell (10 s statt 16 s), aber Internetsuche nicht benutzt, Frage nicht beantwortet, Grammatik falsch | 20.09.2026 |
| qwen3.8:27b | nicht getestet: braucht eine neuere Ollama-Version als 0.31.1 und wäre mit 18 GB deutlich langsamer | 20.09.2026 |

Zahlen und Begründung stehen in `DECISIONS.md`.

## Auf dem Rechner, aber nicht von dieser App

Gehört zum PDF-Assistenten (Suche mit Vektoren) und bleibt unberührt: bge-m3 (1,2 GB). Diese App nutzt keine Vektorsuche.

# Algorithmen

Feste Regeln im Code. Sie brauchen kein Sprachmodell, sind deshalb schnell und liefern immer dasselbe Ergebnis. Die Zahlen sind Schwellen, die man im Code ändern kann.

## PDF prüfen (Menü Datei, "PDF prüfen …" und Werkzeug `pdf_pruefen`), `core/pdfcheck.py`

Grundlage: PyMuPDF liefert je Seite alle Textzeilen mit Rahmen, Schriftgröße und Grundlinie.

| Prüfung | Regel |
|---|---|
| Text über dem Seitenrand ("abgeschnitten") | Bei waagerechtem Text zählen rechts und links der Zeilenrahmen, unten die Grundlinie und oben die Kappenhöhe (0,7 mal Schriftgröße). Mehr als 1,5 Punkt außerhalb der Seite = Fehler. Gedrehter Text bekommt eine Toleranz von 0,4 mal Schriftgröße. |
| Überlappender Text | Zeilenrahmen (oben und unten je 15 Prozent gekürzt) überdecken sich zu mindestens 40 Prozent der kleineren Fläche. Gleiche Texte (doppelt gezeichnet) und Zeilen ohne mindestens zwei Buchstaben oder Ziffern zählen nicht. Höchstens 500 Zeilen je Seite. |
| Text nah am Rand | weniger als 5 mm bis zur Seitenkante = Warnung |
| Winzige Schrift | unter 6 Punkt = Warnung |
| Unlesbare Zeichen | Ersatzzeichen (U+FFFD) oder Zeichen aus dem Privatbereich (U+E000 bis U+F8FF) = Fehler |
| Bilder über dem Rand | Bildrahmen ragt mehr als 3 Punkt hinaus = Warnung |
| Leere Seite | kein Text, kein Bild, keine Zeichnung = Hinweis |
| Scan | Ein Bild deckt mindestens 80 Prozent der Seite. Der Text darüber ist unsichtbare Texterkennung und wird nicht geprüft (sonst Fehlalarme). |
| Seitengrößen | auf Millimeter gerundet, mehrere Größen im Dokument = Hinweis |
| Schriften | nicht eingebettet und keine Standardschrift = Hinweis |
| Für Screenreader | kein Titel, keine Dokumentsprache = Hinweis, keine Struktur (Tags) = Warnung |

Was sie nicht kann: beurteilen, ob eine Seite "schön" aussieht. Das ginge nur mit einem Blick auf die Seite (Werkzeug `seite_ansehen`, Sprachmodell). Abgeschnittener Text am Seitenrand ist im Bild unsichtbar und wird nur von dieser Prüfung gefunden.

## PDFs und Bilder für das Modell, `core/pdfs.py`, `core/conversation.py`

| Algorithmus | Regel |
|---|---|
| Ganz in den Prompt oder über Werkzeuge? | Passt der Text des PDFs in das Restlimit (30.000 Zeichen für alle Anhänge), steht er mit Seitenmarken im Prompt. Sonst nur eine Übersicht und Werkzeuge. |
| Seiten mit wenig Text | weniger als 300 Zeichen = vermutlich Bild, Grafik oder Scan, das Modell soll sie ansehen |
| Stichwortsuche in PDFs | Klein geschrieben, Umlaute vereinfacht (ä zu a, ue zu u). Ein Suchwort zählt mit seinem Stamm (Wort ohne die letzten 2 Buchstaben, mindestens 4). Punkte je Seite: 10 mal Zahl der gefundenen Suchwörter plus Zahl der Treffer (höchstens 10). Beste Seiten zuerst, dazu ein Auszug. |
| Übersicht langer PDFs | Bei mehr als 20 Seiten jede n-te Seite mit den ersten 45 Zeichen. Jedes Token im Prompt kostet Zeit. |
| Seite als Bild | PDF-Seiten mit 130 dpi als PNG, Fotos als JPEG mit höchstens 1600 Pixeln Kantenlänge. Höchstens 3 Bilder je Schritt. |
| Seiten lesen | höchstens 6.000 Zeichen je Aufruf, dann "Weiter ab Seite n" |

## Schneller antworten, `core/router.py`, `core/conversation.py`, `core/tools.py`

| Algorithmus | Regel |
|---|---|
| Planer für Internetfragen | Die Frage enthält ein eindeutiges Wort (aktuell, derzeit, Wetter, Nachrichten, Öffnungszeiten, recherchiere, kostet, Preis, im Internet ...), es ist keine Schreibaufgabe (schreibe, formuliere, übersetze ...), im Antwortfeld steht kein Textentwurf und es sind keine Dateien oder Ordner hinzugefügt. Dann läuft die Suche schon vor dem ersten Modellaufruf. Das spart eine Modellrunde (etwa 8 Sekunden). |
| Suchauszüge kürzen | auf 350 Zeichen an einer Wortgrenze |
| Mehrere Werkzeuge gleichzeitig | Unabhängige Aufrufe eines Schritts (Suche, Seiten lesen, Dokument lesen) laufen in bis zu 4 Threads. Bild ansehen nicht. |
| Suchdienst wählen | Tavily, wenn ein Schlüssel da ist. Bei abgelehntem Schlüssel, leerem Kontingent, Ausfall oder null Treffern übernimmt DuckDuckGo. Der Grund wird einmal je Programmlauf angesagt. |
| Kontext passt | Frühere Runden: neueste zuerst, die ältesten fallen weg, bis der Platz (Kontext minus Antwortlänge) reicht. Zu große Werkzeugergebnisse werden von alt nach neu durch einen Platzhalter ersetzt. |
| Modellfähigkeiten | Ollama meldet je Modell, ob es Werkzeuge, Denken und Bilder kann. Fehlt etwas, bekommt das Modell die Werkzeuge nicht, und die App sagt es an. |
| Zeitmessung | Ollama meldet je Aufruf Einlesen und Schreiben. Die App schreibt daraus eine Zeile "Zeiten" ins Log. |

## Frage- und Antwortfeld, `core/textlayout.py`, `ui/question_panel.py`

| Algorithmus | Regel |
|---|---|
| Antwort in Zeilen | Ein Satz je Zeile, lange Sätze bei Wortgrenzen nach höchstens 70 Zeichen umbrochen. Absätze (Leerzeile) und Listenpunkte bleiben. Kein Satzende nach Abkürzungen (z. B., Dr., Nr., usw.), Einzelbuchstaben oder Zahlen mit Punkt (1. Mai). Quellen stehen je eine Zeile. Der Text eines Dokuments (Anschreiben) bleibt unverändert. |
| Umschalt+Enter | fügt einen echten Zeilenumbruch ein (Absatz), kein Unicode-Zeilentrenner |
