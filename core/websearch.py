"""Internetrecherche: Suche (Tavily mit Schlüssel, sonst DuckDuckGo) und Lesen von Webseiten.

Nur hier verlassen Daten den Rechner, und nur wenn "Internetrecherche" eingeschaltet ist:
die Suchanfrage an Tavily oder DuckDuckGo und die Abrufe der Webseiten.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TextChat/1.0"
MAX_DOWNLOAD = 3_000_000
MAX_REDIRECTS = 4
TAVILY_URL = "https://api.tavily.com/search"


class WebError(Exception):
    """Suche oder Abruf nicht möglich. Der Text ist für das Modell und die Person gedacht."""


# --------------------------------------------------------------------------
# Suche
# --------------------------------------------------------------------------
def search(query: str, max_results: int = 5, region: str = "de-de") -> list[dict]:
    """Liefert Treffer als {'title', 'url', 'snippet'}."""
    query = query.strip()
    if not query:
        raise WebError("Die Suchanfrage ist leer.")
    try:
        from ddgs import DDGS
        raw = DDGS().text(query, region=region, safesearch="moderate", max_results=max_results)
    except Exception as exc:
        raise WebError(f"Die Internetsuche ist gerade nicht möglich ({type(exc).__name__}). "
                       "Vermutlich fehlt die Internetverbindung.") from exc
    return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in raw or [] if r.get("href")]


class TavilyError(Exception):
    """Tavily ist nicht nutzbar. Der Text ist für die Person gedacht (Ansage)."""


def search_tavily(query: str, key: str, max_results: int = 5, depth: str = "basic") -> list[dict]:
    """Suche über Tavily. Liefert dieselben Treffer wie search(), aber mit längeren Auszügen."""
    body = {"query": query.strip(), "max_results": max_results, "search_depth": depth,
            "topic": "general", "country": "germany", "include_answer": False}
    try:
        resp = httpx.post(TAVILY_URL, json=body, headers={"Authorization": f"Bearer {key}"},
                          timeout=httpx.Timeout(15, connect=8))
    except httpx.HTTPError as exc:
        raise TavilyError(f"Tavily ist nicht erreichbar ({type(exc).__name__})") from exc
    if resp.status_code == 401:
        raise TavilyError("Der Tavily-Schlüssel wurde abgelehnt")
    if resp.status_code in (429, 432, 433):
        raise TavilyError("Das Tavily-Kontingent ist aufgebraucht oder die Anfragen kommen zu schnell")
    if resp.status_code >= 400:
        raise TavilyError(f"Tavily meldet Fehler {resp.status_code}")
    try:
        raw = resp.json().get("results") or []
    except (ValueError, AttributeError) as exc:
        raise TavilyError("Tavily hat eine unlesbare Antwort geschickt") from exc
    return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in raw if isinstance(r, dict) and r.get("url")]


class Searcher:
    """Die Suche der App: Tavily, wenn ein Schlüssel eingetragen ist, sonst DuckDuckGo.

    Fällt Tavily aus (Schlüssel abgelehnt, Kontingent leer, keine Verbindung), wird DuckDuckGo
    genutzt. Der Grund landet einmal je Programmlauf in den Hinweisen, die die Oberfläche ansagt.
    """

    def __init__(self, cfg=None, tavily_fn=search_tavily, ddg_fn=search):
        self.cfg = cfg
        self._tavily = tavily_fn
        self._ddg = ddg_fn
        self.notices: list[str] = []
        self._told: set[str] = set()

    def key(self) -> str:
        key = getattr(self.cfg, "tavily_key", "") or os.environ.get("TAVILY_API_KEY", "")
        return key.strip()

    def __call__(self, query: str) -> list[dict]:
        key = self.key()
        if key:
            depth = getattr(self.cfg, "tavily_depth", "basic")
            try:
                results = self._tavily(query, key, depth=depth if depth in ("basic", "advanced")
                                       else "basic")
                if results:
                    return results
            except TavilyError as exc:
                self._notify(f"{exc}. Es wird DuckDuckGo genutzt.")
        return self._ddg(query)

    def _notify(self, text: str) -> None:
        if text not in self._told:
            self._told.add(text)
            self.notices.append(text)

    def take_notices(self) -> list[str]:
        notices, self.notices = self.notices, []
        return notices


# --------------------------------------------------------------------------
# Seiten lesen
# --------------------------------------------------------------------------
def is_public_address(host: str) -> bool:
    """False für lokale und private Adressen, damit das Modell keine internen Dienste abruft."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False
    return bool(infos)


def check_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise WebError("Nur Adressen mit http oder https werden gelesen.")
    if not is_public_address(parsed.hostname):
        raise WebError("Diese Adresse ist nicht öffentlich erreichbar und wird nicht gelesen.")
    return parsed.geturl()


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg",
            "iframe", "template"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section",
             "article", "ul", "ol", "table", "blockquote", "pre"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    """(Titel, Fließtext) aus HTML."""
    parser = _TextExtractor()
    parser.feed(html)
    lines = (re.sub(r"[ \t ]+", " ", line).strip() for line in "".join(parser.parts).splitlines())
    text = "\n".join(line for line in lines if len(line) > 2)
    return parser.title.strip(), text


def _download(url: str) -> tuple[str, bytes]:
    """Lädt eine Seite. Umleitungen werden einzeln geprüft. Gibt (Content-Type, Bytes) zurück."""
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "de,en;q=0.7"}
    with httpx.Client(timeout=httpx.Timeout(15, connect=8), headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            url = check_url(url)
            try:
                with client.stream("GET", url) as resp:
                    if resp.is_redirect:
                        url = urljoin(url, resp.headers.get("location", ""))
                        continue
                    if resp.status_code >= 400:
                        raise WebError(f"Die Seite antwortet mit Fehler {resp.status_code}.")
                    data = b""
                    for block in resp.iter_bytes():
                        data += block
                        if len(data) > MAX_DOWNLOAD:
                            break
                    return resp.headers.get("content-type", "").lower(), data
            except httpx.HTTPError as exc:
                raise WebError(f"Die Seite ist nicht erreichbar ({type(exc).__name__}).") from exc
    raise WebError("Zu viele Weiterleitungen.")


def read_page(url: str, max_chars: int = 6000) -> tuple[str, str]:
    """(Titel, Text) einer Webseite oder PDF, auf max_chars gekürzt."""
    content_type, data = _download(url)
    if "pdf" in content_type:
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            text = "\n\n".join(page.get_text() for page in doc)
        title = ""
    elif "html" in content_type or "text/plain" in content_type or not content_type:
        html = data.decode("utf-8", errors="replace")
        title, text = (html_to_text(html) if "plain" not in content_type else ("", html))
    else:
        raise WebError(f"Dieser Inhaltstyp wird nicht gelesen: {content_type}")
    text = text.strip()
    if not text:
        raise WebError("Auf der Seite wurde kein lesbarer Text gefunden.")
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + " … [gekürzt]"
    return title, text
