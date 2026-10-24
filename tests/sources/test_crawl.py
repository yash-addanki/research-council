import httpx

from research_council.sources import crawl


def _client(status, body):
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, text=body)))


def test_fetch_text_strips_html_and_scripts():
    html = "<html><head><script>evil()</script><style>x{}</style></head><body><h1>Title</h1><p>Hello   world</p></body></html>"
    text = crawl.fetch_text("https://x.com", client=_client(200, html), use_crawl4ai=False)
    assert "Title" in text and "Hello world" in text
    assert "evil" not in text


def test_fetch_text_truncates():
    text = crawl.fetch_text("https://x.com", max_chars=10, client=_client(200, "<p>" + "a" * 100 + "</p>"), use_crawl4ai=False)
    assert len(text) == 10


def test_fetch_text_unreachable_returns_none():
    assert crawl.fetch_text("https://x.com", client=_client(404, "nope"), use_crawl4ai=False) is None
