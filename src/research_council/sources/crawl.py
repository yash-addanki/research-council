"""Read a page as text: Crawl4AI when installed (renders JS), plain HTTP otherwise."""

import asyncio
import logging
import re
from html.parser import HTMLParser

import httpx

log = logging.getLogger(__name__)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TEXT_TYPES = ("text/html", "text/plain", "text/markdown", "application/xhtml")


def clean_text(text: str) -> str:
    """Drop NUL and other control characters: a CLI argument can't hold a NUL byte."""
    return _CONTROL.sub("", text)


def _html_to_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def _crawl4ai(url: str) -> str | None:
    try:
        from crawl4ai import AsyncWebCrawler
    except ImportError:
        return None

    async def go():
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
            return str(result.markdown) if result.success else None

    try:
        return asyncio.run(go())
    except Exception as exc:
        log.warning("crawl4ai failed for %s: %s", url, exc)
        return None


def fetch_text(url: str, max_chars: int = 20000, client: httpx.Client | None = None,
               use_crawl4ai: bool = True) -> str | None:
    text = _crawl4ai(url) if use_crawl4ai else None
    if text is None:
        client = client or httpx.Client(timeout=30, follow_redirects=True)
        try:
            resp = client.get(url)
            resp.raise_for_status()
        except Exception as exc:
            log.warning("fetch failed for %s: %s", url, exc)
            return None
        kind = resp.headers.get("content-type", "text/html").lower()
        if not kind.startswith(TEXT_TYPES):
            log.warning("skipping %s: not a web page (%s)", url, kind)
            return None
        text = _html_to_text(resp.text)
    return clean_text(text)[:max_chars]


_GITHUB_REPO = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)/?$")


def page_url(url: str) -> str:
    """A GitHub repo page is mostly navigation; its README says what the repo is."""
    m = _GITHUB_REPO.match(url)
    return f"https://raw.githubusercontent.com/{m[1]}/{m[2]}/HEAD/README.md" if m else url


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def best_passage(text: str, query: str, size: int = 1500) -> str:
    """The window of the page sharing the most words with the query (pages open with menus, not facts)."""
    if len(text) <= size:
        return text
    want = _words(query)
    step = max(1, size // 3)
    starts = range(0, len(text) - size + step, step)
    best = max(starts, key=lambda i: len(want & _words(text[i:i + size])))
    return text[best:best + size]
