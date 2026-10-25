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


def test_best_passage_picks_window_with_query_words():
    text = "nav menu sign in pricing " * 200 + " Beam lets you send one prompt to many models and merge answers. " + "footer " * 200
    out = crawl.best_passage(text, "Beam sends one prompt to many models", size=200)
    assert "Beam lets you send one prompt" in out and len(out) <= 200


def test_best_passage_short_text_returned_whole():
    assert crawl.best_passage("short page", "anything", size=200) == "short page"


def test_page_url_maps_github_repo_to_raw_readme():
    assert crawl.page_url("https://github.com/enricoros/big-AGI") == "https://raw.githubusercontent.com/enricoros/big-AGI/HEAD/README.md"
    assert crawl.page_url("https://github.com/a/b/issues/3") == "https://github.com/a/b/issues/3"
    assert crawl.page_url("https://example.com/x") == "https://example.com/x"


def test_fetch_text_skips_pdf_and_binary():
    pdf = httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, content=b"%PDF-1.7\x00\x00<![CDATA[", headers={"content-type": "application/pdf"})))
    assert crawl.fetch_text("https://x.org/paper.pdf", client=pdf, use_crawl4ai=False) is None


def test_fetch_text_removes_null_and_control_chars():
    text = crawl.fetch_text("https://x.com", client=_client(200, "<p>a\x00b\x07c\nd</p>"), use_crawl4ai=False)
    assert text == "abc d"
