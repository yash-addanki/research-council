from research_council.evidence import EvidenceItem, canonical_url, dedupe


def _item(url, title="t"):
    return EvidenceItem(url=url, title=title, platform="web", excerpt="", published_at=None, fetched_at="2026-10-24")


def test_canonical_url_strips_tracking():
    assert canonical_url("https://Example.com/a/?utm_source=x#h") == "https://example.com/a"


def test_canonical_url_keeps_meaningful_query():
    assert canonical_url("https://news.ycombinator.com/item?id=1&utm_medium=y") == "https://news.ycombinator.com/item?id=1"


def test_dedupe_keeps_first():
    items = [_item("https://a.com/x", "first"), _item("https://A.com/x/?utm_x=1", "second"), _item("https://b.com")]
    out = dedupe(items)
    assert [i.title for i in out] == ["first", "t"]
