# Entscheidungen und Messwerte: Chatbot für Text

Stand: 19.09.2026. Gemessen auf dem Zielrechner (ThinkPad E14 Gen 7, Intel Core Ultra 7 258V, Arc 140V, 32 GB).

## Modellvergleich (scripts/try_chat.py, alles auf der GPU über Vulkan)

Gleiche sieben Aufgaben für beide Modelle: Anschreiben, Änderungswunsch, Word-Wunsch, kurze Erklärung, lange Erklärung, Rechenrätsel mit Nachdenken, Internetfrage.

| Aufgabe | qwen3:8b (5,2 GB) | gemma4:12b (7,6 GB) |
|---|---|---|
| Anschreiben | 9 s, Tippfehler im Text ("bewerke"), keine Antwortzeile | 17 bis 20 s, fehlerfreier Text, eigene Antwortzeile |
| Änderung | 8 s, Modell schrieb die interne Gedächtnisnotiz in die Antwort | 15 s, sauber |
| Lange Antwort | keine erkennbare Wirkung (gleich lang wie kurz) | wirkt (47 s statt 9 s) |
| Nachdenken (Rechenrätsel) | 45 s, richtig | 76 bis 78 s, richtig |
| Internetfrage | 6 s, keine Suche, falsche Antwort aus dem Gedächtnis (Olaf Scholz) | 27 s, sucht, richtig (Friedrich Merz) mit Quellen |
| Anrede | neutral | duzte ("für dich"), jetzt per Prompt auf "Sie" gestellt |

Entscheidung: gemma4:12b als Standard. Es schreibt das bessere Deutsch, nutzt die Werkzeuge zuverlässig und befolgt die Schalter. Der Preis ist etwa doppelte Dauer. qwen3:8b ist schneller, hat aber im Test die Internetrecherche ausgelassen und falsch geantwortet.

### Nachtest 20.09.2026: qwen3.5:9b und qwen3.8:27b

Gleiche sieben Aufgaben, gleiche Einstellungen, Internetfrage über DuckDuckGo (kein Tavily-Schlüssel).

| Aufgabe | qwen3.5:9b (6,6 GB) | gemma4:12b (7,6 GB, Vergleichslauf am selben Tag) |
|---|---|---|
| Anschreiben | 10 s, gut, aber Dateiname mit Fehler ("Ana_Weiss") | 16 s, sauber |
| Änderung | 7 s, gut | 12 s, gut |
| Word-Wunsch | 3 s | 14 s |
| Kurze Erklärung (das/dass) | 6 s, falsch ("Kasus", "Konjunktion ohne Subjekt") | 7 s, teils ungenau |
| Lange Antwort | 12 s, kaum länger, fachlich falsch | 48 s, wirkt |
| Nachdenken | 22 s, richtig | 127 s, richtig |
| Internetfrage | 10 s, **keine Suche**, keine Antwort auf die Frage, Anweisungstext des Systems in der Antwort | 29 s, sucht, richtig (Friedrich Merz) mit Quellen |

Ergebnis: qwen3.5:9b ist zwei- bis viermal so schnell, hat aber die Werkzeuge nicht benutzt und die Frage nicht beantwortet. Das war der Grund für gemma4:12b. Es bleibt der Standard. qwen3.8:27b konnte nicht getestet werden: Es verlangt eine neuere Ollama-Version als die installierte 0.31.1. Außerdem wäre es mit 18 GB gut doppelt so groß wie gemma4, auf der Arc 140V also deutlich langsamer. Ein Ollama-Update habe ich nicht ohne Rückfrage gemacht, weil der PDF-Assistent dieselbe Installation nutzt. qwen3.5:9b wurde wieder gelöscht.

### Modellwahl im Menü und Probelauf mit qwen2.5vl:7b (20.09.2026)

Im Menü Einstellungen, Modell kann zwischen gemma4:12b und qwen2.5vl:7b gewählt werden (Häkchen, gespeichert in config.json). Der Wechsel lädt das neue Modell (etwa 15 s) und entlädt das alte, damit nicht beide im Speicher liegen. Ein nicht installiertes Modell wird abgelehnt, das alte bleibt.

qwen2.5vl:7b hat laut Ollama nur "completion" und "vision", keine Werkzeuge und kein Denken. Die App fragt die Fähigkeiten je Modell ab (core/ollama_backend.py, capabilities). Ohne Werkzeuge gibt es keine Internetsuche und keinen Ordnerzugriff, und das Modell bekommt keine Suchanweisung im Prompt. Die App sagt das beim Wechsel und bei jeder Frage an ("Dieses Modell kann nicht im Internet suchen.").

Probelauf mit den sieben Aufgaben (gleiche Bedingungen):

| Aufgabe | qwen2.5vl:7b | gemma4:12b |
|---|---|---|
| Anschreiben | 10 s, schreibt in die Antwort statt in den Textentwurf, **erfindet** Masterabschluss und selbstständige Tätigkeit, Sprachfehler ("auf das Gelegenheit", "Wissensvorrat") | 16 s, sauber |
| Änderung, Word-Wunsch | 8 bis 10 s, Word-Datei wird angeboten | 12 bis 14 s |
| Kurze und lange Erklärung | 10 und 15 s, fachlich falsch ("Artikel ... im Dativ") | 7 und 48 s, teils ungenau |
| Nachdenken | 18 s, falsch (11:25 Uhr statt 12:05 Uhr) | 127 s, richtig |
| Internetfrage | 7 s, keine Suche, veraltete falsche Antwort (Merkel/Scholz) | 29 s, richtig mit Quellen |

Für reine Schreibaufgaben ist qwen2.5vl:7b etwas schneller, aber inhaltlich unzuverlässiger. Vorsicht bei Anschreiben: es erfindet Angaben. Bilder liest es (Stärke für den PDF-Assistenten), das nutzt diese App nicht.

Grenzen von gemma4:12b: Inhaltliche Erklärungen (zum Beispiel Grammatikregeln zu "das" und "dass") enthalten Fehler. Wichtige Fakten sollte man prüfen, auch bei Recherche (Quellen stehen unter der Antwort).

Zeiten (ungefähre Größenordnung, Gerät im Modus "Ausbalanciert"): Modellstart bis bereit etwa 12 bis 17 s. Kurze Antwort etwa 10 s, Anschreiben etwa 15 bis 20 s, Antwort mit Internetrecherche etwa 30 s, mit Nachdenken etwa 75 s.

## Version 3 (Oberfläche neu, nach der Beschreibung der Person)

Die Version-2-Oberfläche (Bereiche Verlauf, Frage, Antwort, Aktionen mit Schaltflächen, Projekt-Panel) wurde durch diese Umsetzung ersetzt.

| Thema | Entscheidung | Grund |
|---|---|---|
| Tab-Kreis | Frage, Antwort, Aktionen, Verlauf, wieder Frage; genau vier Tab-Stopps | Vorgabe der Person. Schaltflächen sind zu Listen geworden, damit jeder Bereich nur einen Tab-Stopp braucht. |
| Frage | Nach Enter sofort geleert, bei Abbruch oder Fehler zurückgegeben | Vorgabe. Der Rückgabe-Teil ist meine Ergänzung, damit eine lange Frage bei einem Fehler nicht verloren geht. |
| Antwortfeld | mehrzeilig, groß, bearbeitbar, Kommentar plus Text | Vorgabe, dass man darin navigieren und arbeiten kann. |
| Aktionen | Liste statt Schaltflächen; Text kopieren und Word nur bei Bedarf | "Aktionen-Menü" der Vorgabe. Eine Liste hat einen Tab-Stopp und funktioniert mit Pfeiltasten und Enter. |
| Verlauf | nur ansehen, kein Löschen, kein Fragefeld-Überschreiben | Vorgabe. Chats lassen sich über die Chatliste entfernen. |
| Menü-Reihenfolge | Projekte, Chatliste, Einstellungen, Datei, Ansicht, Hilfe | Reihenfolge der Vorgabe. Das Datei-Menü steht dadurch nicht an erster Stelle. |
| Projekte und Chatlisten | als Untermenüs, Enter öffnet, oberster Eintrag "Neuer Chat" | Vorgabe. Das frühere Projekt-Panel im Hauptfenster entfällt. |
| Kontextmenü | eigene Menüklasse (ui/menus.py), Menütaste, Umschalt+F10 und rechte Maustaste | Qt-Menüs haben kein Kontextmenü auf Einträgen. Nur mit simulierten Tasten getestet, ein echter NVDA-Test steht aus. |
| Entfernen | Rückfrage mit Enter als Vorgabe ("Entfernen"), Esc bricht ab | "Alles mit Enter bestätigen" gegen versehentliches Löschen abgewogen. Ein Projekt zu entfernen löscht keine Chats. |
| Verschieben, Kopieren | Projektliste als Untermenü, Enter wählt. Kopieren legt eine unabhängige Kopie mit Verlauf und Anhängen an | Vorgabe. |
| Chatliste | nur Chats ohne Projekt | Vorgabe. |
| Kurze Beschreibungen | Bei Steuerelementen steht als Beschreibung nur das Tastenkürzel (Strg+1 bis Strg+4), keine Erklärung zu Tab, Enter oder Esc. Auch die Ansagen erklären keine Tasten mehr. | Rückmeldung: Die Texte sind auf der Braillezeile zu lang. Ein Test prüft das. Die Erklärungen stehen nur noch im Hilfefenster (F1). |
| Kontextmenü, Nachbesserung (19.09.2026) | Erster Eintrag beim Öffnen markiert (wie Pfeil runter, öffnet kein Untermenü). Danach Fokus zurück ins Fenster statt in der Menüleiste. Anfragen stehen im Log (app.log, "Kontextmenü angefordert"). | Mit echten Tasten (SendInput, echtes Windows, ohne NVDA) geprüft: Umschalt+F10 und Menütaste öffnen das Kontextmenü auf Projekten und Chats, auch in Projektlisten. Das Menü kam aber ohne Markierung (für Screenreader stumm), und der Fokus blieb danach in der Menüleiste. |
| NVDA und Menüs (19.09.2026) | Jedes Menü hat einen eigenen Namen ("Projekte", "Kontextmenü", ...). Die Fokusmeldung des ersten markierten Eintrags wird 200 ms nach dem Öffnen wiederholt (ui/menus.py, AccessibleMenu). | Rückmeldung: NVDA sagte beim Öffnen "Chatbot für Text Menü" statt des ersten Eintrags, bei Projekten (nur ein Eintrag) war er nie zu hören. Noch nicht mit NVDA bestätigt. |
| Projektdateien (geändert 20.09.2026) | Jedes Projekt hat einen Eintrag "Projektdateien" eine Ebene unter dem Projekt, zwischen "Neuer Chat" und den Chats. Oben "Datei hochladen …", darunter die Dateien, Menütaste: "Datei entfernen". Alle Chats des Projekts können die Dateien lesen (neue, gespeicherte und in das Projekt verschobene), Chats ohne Projekt nicht. Verschiebt man den offenen Chat in ein anderes Projekt, wechseln die Projektdateien mit. Sie zählen zum selben Text-Limit wie hinzugefügte Dateien (max_attachment_chars). Nur der Eintrag wird entfernt, nicht die Datei. Wird ein Projekt entfernt, gehen seine Dateieinträge mit. | Vorgabe der Person: Dateien in einem Chat sind nur dort lesbar, Projektdateien für alle Chats des Projekts. Die erste Fassung (19.09.2026) hatte gemeinsame Dateien für alle Chats im obersten Projekte-Menü, das war ein Missverständnis. Die Tabelle project_files hat jetzt eine Projektnummer. Alte Einträge ohne Projekt werden beim Start verworfen (im Datenbestand der Person gab es keine). |
| Endlosschleife behoben | Schließen der offenen Menüs nach einer Kontextmenü-Auswahl ist begrenzt | Ein Test deckte eine mögliche Endlosschleife auf, die das Programm eingefroren hätte. |

## PDFs, Bilder, PDF-Prüfung und Tempo (21.09.2026)

Code aus dem PDF-Assistenten (Einlesen der Seiten, Silbentrennung, Seite als Bild rendern mit 130 dpi) und aus dem Bildbeschreibungs-Projekt (Regeln: nur Sichtbares, nichts erfinden, Unlesbares benennen) ist übernommen, siehe core/pdfs.py und core/prompts.py.

| Thema | Entscheidung | Grund |
|---|---|---|
| PDFs und Bilder | Kurze PDFs stehen mit Seitenmarken im Prompt (wie Textdateien, Limit max_attachment_chars). Lange PDFs, Scans und Bilder liest das Modell über Werkzeuge: dokument_lesen, dokument_suchen, seite_ansehen, pdf_pruefen. Im Prompt steht nur eine Übersicht (höchstens 20 Seitenanfänge). | Vorher wurden lange PDFs stillschweigend nach 30.000 Zeichen abgeschnitten, Scans und Bilder gar nicht gesehen. Ein Buchkapitel (28 Seiten) hat 53.000 Zeichen. |
| Keine Vektorsuche | Stichwortsuche pro Seite (ohne Umlaute, Endungen egal) statt bge-m3-Vektoren | Kein Warten auf einen Index. Im Test fand sie die Stelle auf Seite 27 eines 40-Seiten-PDFs sofort. Vektoren bleiben eine mögliche Ergänzung, wenn die Stichwortsuche nicht reicht. |
| Seite oder Bild ansehen | Das Bild geht als Bild in dieselbe Unterhaltung (nächste Nachricht), das Hauptmodell sieht es selbst. Höchstens 3 Bilder je Schritt. | Erster Ansatz war ein zweiter Modellaufruf, der das Bild beschreibt. Der kostete 80 s (Karte) statt 30 s: langer Beschreibungstext (285 Token bei 8 Token/s) und der Zwischenspeicher ging verloren. |
| PDF prüfen | Menü Datei, "PDF prüfen …": technische Prüfung ohne Modell (core/pdfcheck.py), Bericht steht in der Antwort. Auch als Werkzeug pdf_pruefen. | Dauert unter einer Sekunde. Findet: Text über dem Seitenrand (abgeschnitten), überlappende Zeilen, winzige Schrift, unlesbare Zeichen, Bilder über dem Rand, leere Seiten, unterschiedliche Seitengrößen, nicht eingebettete Schriften, fehlende Angaben für Screenreader (Titel, Sprache, Tags). Scans mit unsichtbarer Texterkennung werden nicht auf Text geprüft (sonst Fehlalarme). |
| Optischer Blick | Nur zweite Meinung (seite_ansehen). Abgeschnittener Text am Seitenrand ist im gerenderten Bild unsichtbar, den findet nur die technische Prüfung. Die optische Ansicht sah in einem Test Überlappung und kleine Schrift, aber nicht den abgeschnittenen Satz. | Prompt sagt dem Modell das. |
| Vorgezogene Suche | core/router.py: Bei eindeutigen Internetfragen (aktuell, Wetter, kostet, Öffnungszeiten, recherchiere, im Internet ...) läuft die Suche schon vor dem ersten Modellaufruf. Nicht bei Schreibaufgaben, Textentwurf im Antwortfeld oder hinzugefügten Dateien. Das Modell behält die Suchwerkzeuge. Abschaltbar: web_prefetch in config.json. | Spart die Runde, in der das Modell nur beschließt zu suchen. 4 Fragen im Mittel 17,7 s statt 9,4 s. Bei der NVDA-Version lag die vorgezogene Suche einmal daneben (2026.1 statt 2026.2), bei 3 anderen Fragen gleiche Antworten. Die Stichprobe ist klein. |
| Kürzere Suchauszüge | Auszüge auf 350 Zeichen gekürzt | Tavily liefert etwa 1.100 Zeichen je Treffer, das kostete etwa 15 s Einlesezeit mehr. Das erklärt, warum Tavily im Test langsamer war. |
| Parallele Werkzeuge | Mehrere unabhängige Werkzeugaufrufe eines Schritts laufen gleichzeitig (Suche, Seiten lesen, Dokument lesen). Ansehen nicht. | Kostet kein Modell, spart Wartezeit bei mehreren Seiten. |
| Zeitmessung | Ollama meldet je Aufruf Einlesen und Schreiben. Die App schreibt eine Zeile "Zeiten" ins Log (app.log) und scripts/try_chat.py zeigt sie. | Ohne Messung kein sinnvolles Beschleunigen. |
| Kein Mehr-Agenten-Aufbau | Bewusst nicht gebaut | Messung unten: Die Zeit geht ins Einlesen und Schreiben desselben Modells. Jeder zusätzliche Agent wäre ein weiterer Aufruf. |

Wohin die Zeit geht (gemma4:12b auf der Arc 140V, gemessen): Einlesen etwa 100 bis 150 Token je Sekunde, Schreiben etwa 11 Token je Sekunde. Das Einlesen macht rund zwei Drittel der Wartezeit aus, jede 1.000 Token Prompt kosten etwa 7 bis 10 Sekunden. Ein Systemtext mit Internetregeln hat etwa 730 Token, ohne 430. Ein Bild kostet etwa 380 bis 440 Token.

Getestet und verworfen: num_batch 128 bis 2048 (Standard 512 ist am schnellsten, 2048 ist langsamer: 113 statt 150 Token/s). Aufwärmen mit dem echten Systemtext bringt nichts: Der Zwischenspeicher greift bei gemma4 nur, wenn der neue Prompt den alten vollständig fortsetzt. Ein gemeinsamer Anfang mit anderer Frage wird neu eingelesen (4,1 s für 590 Token).

Messwerte vorher, nachher (Karte mit 8 Messwerten, Scan, 40-Seiten-PDF, Layout): Karte 81 s auf 30 s (8 von 8 Werten richtig), Scan-PDF 80 s auf 26 s, Layoutfrage 53 s auf 22 s, 40-Seiten-PDF 23 s auf 19 s (Zugangscode auf Seite 27 gefunden). Handschrift im Scan erkennt gemma4 als handschriftliche Formeln, Einzelheiten stimmen nicht sicher.

Offen: "Nachdenken" braucht etwa 127 s (rund 1.400 Denk-Token bei 11 Token/s). Ein Versuch, das Denken per Anweisung zu kürzen, steht aus. Beim Test des Zwischenspeichers gab es außerdem eine Anfrage, die 101 s ohne Ergebnis lief, kurz vor einem Beinahe-Absturz des Rechners. Ursache nicht geklärt, deshalb keine weiteren langen Modellläufe.

## Frage- und Antwortfeld für Braillezeile (21.09.2026)

Rückmeldung: Umschalt+Enter im Fragefeld ergab ein Unicode-Zeichen, der weitere Text blieb auf der Braillezeile in derselben Zeile. Im Antwortfeld zeigte jeder Pfeiltastendruck wieder den Anfang der Antwort in einer Zeile.

| Thema | Entscheidung | Grund |
|---|---|---|
| Umschalt+Enter | Fügt einen echten Absatzumbruch ein (ui/common.py, PlainEdit), gilt für Frage- und Antwortfeld. Eingefügter Text mit U+2028 oder U+2029 wird zu normalen Zeilenumbrüchen. Enter und Strg+Enter senden weiter. | Qt fügt bei Umschalt+Enter sonst den Zeilentrenner U+2028 ein. Das ist derselbe Absatz, ein Screenreader sieht keine neue Zeile. |
| Antwort in Zeilen | Antwort und Kommentar stehen mit einem Satz je Zeile, lange Sätze nach 70 Zeichen an Wortgrenzen umbrochen, Listenpunkte und Absätze bleiben, Quellen je Zeile (core/textlayout.py). | Ein Absatz mit mehreren Sätzen ist für den Screenreader eine Zeile. Mit echten Zeilenumbrüchen bewegen die Pfeiltasten zeilenweise. Abkürzungen (z. B., Dr., Nr.) und Zahlen mit Punkt (1. Mai) trennen nicht. |
| Dokumenttext | Der Text eines Anschreibens bleibt unverändert (Absätze wie geschrieben). | Er wird kopiert und als Word gespeichert. Feste Zeilenumbrüche mitten im Absatz wären dort falsch. Auf der Braillezeile ist ein langer Absatz weiter eine Zeile. Ein Schalter dafür wäre möglich. |
| Gespeicherte Antworten | Was im Feld steht, wird gespeichert. Alte Verläufe bleiben unverändert und zeigen weiter ihren alten Text. | Nichts wird nachträglich umgebaut. |

## Version 2 (frühere Rückmeldung, teilweise durch Version 3 ersetzt)

| Thema | Entscheidung | Grund |
|---|---|---|
| Antwortfeld | mehrzeilig, mindestens 10 Zeilen, bearbeitbar; das getrennte Textentwurf-Feld entfällt | Rückmeldung: Man soll im Antwortfeld selbst arbeiten können. Fenster startet maximiert. |
| Kommentar und Text | Kommentar, Leerzeile, Text im selben Feld. Kopieren und Word nehmen nur den Text | Ein Feld statt zwei, ohne dass der Kommentar im Brief landet. |
| Änderungen der Person | Vor dem Senden im Verlaufseintrag gespeichert | Sonst gingen sie verloren, wenn eine neue Antwort das Feld ersetzt. Jeder Verlaufseintrag ist eine Textversion. |
| Schalter | Menü "Einstellungen" mit Häkchen-Einträgen | Windows zeichnet Menühäkchen sichtbar, dazu bestätigt die App den Zustand per Ansage. |
| Ordner | Freigabe mit Lese-Werkzeugen statt Vollständig-Laden | Große Ordner passen nicht in den Kontext. Sicherheit: nur lesend, nur unterhalb des Ordners, keine versteckten Dateien. |
| Dateien und Ordner | gehören zum Chat, nicht zum Projekt | Einfacher Anfang. Projektweite Dateien wären eine mögliche Erweiterung. |

## Weitere Entscheidungen

| Thema | Entscheidung | Grund |
|---|---|---|
| Absenden-Knopf | nicht vorhanden | Enter genügt, und Tab vom Fragefeld führt direkt in die Antwort. |
| Text-Blöcke statt Werkzeug für Dokumente | `<dokument>`-Block | Robust bei langen Texten, kein Maskieren nötig. Die App gibt zusätzlich eine Standard-Antwortzeile aus, falls das Modell keine schreibt. |
| Gedächtnis-Notiz | keine | Ein Anhängsel wie "(Textentwurf geändert)" im Gedächtnis wurde von qwen3:8b nachgeahmt und landete in der Antwort. |
| Internetsuche | DuckDuckGo über das Paket ddgs (Grundausstattung, ohne Schlüssel), seit 20.09.2026 mit Tavily davor, siehe unten | Kein Schlüssel und kein Konto nötig. Google hat keine kostenlose Schnittstelle ohne Schlüssel. Die Suchmaschine kann sich ändern oder Anfragen begrenzen. |
| Tavily (20.09.2026) | Ist ein Schlüssel eingetragen (Einstellungen, "Tavily-Schlüssel …", oder Umgebungsvariable TAVILY_API_KEY), sucht die App über Tavily (core/websearch.py, Searcher). Bei abgelehntem Schlüssel, leerem Kontingent (1.000 Credits im Monat gratis, "basic" kostet 1 Credit), Ausfall oder null Treffern übernimmt DuckDuckGo. Der Grund wird einmal je Programmlauf angesagt. Der Schlüssel steht im Klartext in config.json. Tiefe "advanced" (2 Credits, genauer) nur über config.json (tavily_depth). | DuckDuckGo über ddgs ist nur ein inoffizielles Auslesen mit kurzen Auszügen. Tavily liefert längere, für KI aufbereitete Auszüge, das spart Seitenabrufe und Zeit. Noch nicht mit einem echten Schlüssel gemessen, nur mit simulierten Antworten getestet. Ein Vergleich mit denselben Internetfragen steht aus. |
| Prompt für Recherche | "IMMER zuerst suchen" bei Veränderlichem | Ohne diese Zeile hat qwen3:8b nicht gesucht. |
| Kontext | 16384 Tokens | Reicht für Anhänge, Text und Recherche, Speicherbedarf moderat. |
| Python-Umgebung | gemeinsam mit dem PDF-Assistenten (C:\venvs\pdfchat) | Spart einen zweiten PySide6-Download. Neue Pakete: ddgs, python-docx. |
| Datenordner | %APPDATA%\TextChat | Getrennt vom PDF-Assistenten (%APPDATA%\PDFChat). |

## Bekannte Grenzen

- Internetrecherche hängt von DuckDuckGo und den Webseiten ab. Manche Seiten sperren automatische Abrufe oder brauchen JavaScript, dann meldet das Modell, dass die Seite nicht lesbar war.
- Ein hart beendetes Programm (Task-Manager) lässt Ollama-Prozesse zurück, die Arbeitsspeicher belegen. Programm immer normal schließen.
- Das Antwortfeld enthält reinen Text. Fettdruck oder Überschriften gibt es nicht, im Word-Dokument sind Absätze und Aufzählungen enthalten.
- Läuft Ollama schon vor dem Programm (zum Beispiel über das Ollama-Symbol im Infobereich), gelten Flash Attention und die anderen Startvariablen des Programms nicht.
