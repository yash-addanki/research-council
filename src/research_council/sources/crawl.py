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
        text = _html_to_text(resp.text)
    return text[:max_chars]
