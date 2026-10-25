import json

import httpx
import pytest

from research_council.notion import NotionClient, chunk_text, markdown_to_blocks

DS = "584e4526-ff39-4614-96d7-f1c0e2b051dd"


def _page(pid, title, priority, created, depth=None, notes=""):
    props = {
        "Idea / Question": {"type": "title", "title": [{"plain_text": title}]},
        "Notes": {"type": "rich_text", "rich_text": [{"plain_text": notes}] if notes else []},
        "Priority": {"type": "select", "select": {"name": priority} if priority else None},
        "Tags": {"type": "multi_select", "multi_select": [{"name": "Tech"}]},
        "Depth": {"type": "select", "select": {"name": depth} if depth else None},
    }
    return {"id": pid, "created_time": created, "properties": props}


class Recorder:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, req):
        self.requests.append(req)
        status, body, headers = self.responses.pop(0)
        return httpx.Response(status, json=body, headers=headers or {})


def _client(responses):
    rec = Recorder(responses)
    nc = NotionClient("tok", DS, rate_per_s=1000, client=httpx.Client(transport=httpx.MockTransport(rec)), sleep=lambda s: None)
    return nc, rec


def test_next_topic_orders_by_priority():
    pages = [_page("a", "low one", "Low", "2026-01-01"), _page("b", "high new", "High", "2026-03-01"),
             _page("c", "high old", "High", "2026-02-01"), _page("d", "medium", "Medium", "2026-01-01")]
    nc, rec = _client([(200, {"results": pages, "has_more": False}, None)])
    topic = nc.next_topic()
    assert topic.page_id == "c" and topic.title == "high old"
    body = json.loads(rec.requests[0].content)
    assert body["filter"] == {"property": "Status", "status": {"equals": "To Research"}}
    assert rec.requests[0].url.path == f"/v1/data_sources/{DS}/query"
    assert rec.requests[0].headers["Notion-Version"] == "2025-09-03"


def test_next_topic_none_when_empty():
    nc, _ = _client([(200, {"results": [], "has_more": False}, None)])
    assert nc.next_topic() is None


def test_depth_defaults_from_priority():
    pages = [_page("a", "t", "Medium", "2026-01-01")]
    nc, _ = _client([(200, {"results": pages, "has_more": False}, None)])
    assert nc.next_topic().depth == "Medium"
    pages = [_page("a", "t", None, "2026-01-01")]
    nc, _ = _client([(200, {"results": pages, "has_more": False}, None)])
    assert nc.next_topic().depth == "Low"
    pages = [_page("a", "t", "Low", "2026-01-01", depth="High")]
    nc, _ = _client([(200, {"results": pages, "has_more": False}, None)])
    assert nc.next_topic().depth == "High"


def test_chunk_text_never_exceeds_limit():
    s = "x" * 5000
    chunks = chunk_text(s, 2000)
    assert all(len(c) <= 2000 for c in chunks)
    assert "".join(chunks) == s


def test_chunk_text_prefers_paragraph_breaks():
    s = "a" * 1500 + "\n\n" + "b" * 1500
    assert chunk_text(s, 2000) == ["a" * 1500, "b" * 1500]


def test_429_retries_after_header():
    nc, rec = _client([(429, {}, {"Retry-After": "1"}), (200, {"results": [], "has_more": False}, None)])
    assert nc.next_topic() is None
    assert len(rec.requests) == 2


def test_set_props_sends_typed_values():
    nc, rec = _client([(200, {}, None)])
    nc.set_props("p1", run_id="r1", tokens_used=1234, report_url="https://x")
    props = json.loads(rec.requests[0].content)["properties"]
    assert props["Run ID"] == {"rich_text": [{"text": {"content": "r1"}}]}
    assert props["Tokens used"] == {"number": 1234}
    assert props["Report"] == {"url": "https://x"}


def test_set_status():
    nc, rec = _client([(200, {}, None)])
    nc.set_status("p1", "Resolved")
    assert json.loads(rec.requests[0].content)["properties"]["Status"] == {"status": {"name": "Resolved"}}


def test_append_markdown_batches_100_blocks():
    md = "\n\n".join(f"para {i}" for i in range(150))
    nc, rec = _client([(200, {}, None), (200, {}, None)])
    nc.append_markdown("p1", md)
    sizes = [len(json.loads(r.content)["children"]) for r in rec.requests]
    assert sizes == [100, 50]


def test_markdown_to_blocks_headings_bullets():
    blocks = markdown_to_blocks("## Answer\n\nYes.\n\n- one\n- two")
    assert [b["type"] for b in blocks] == ["heading_2", "paragraph", "bulleted_list_item", "bulleted_list_item"]


def test_ensure_schema_idempotent():
    have = {"properties": {"Depth": {}, "Run ID": {}, "Tokens used": {}, "Report": {}}}
    nc, rec = _client([(200, have, None)])
    nc.ensure_schema()
    assert [r.method for r in rec.requests] == ["GET"]


def test_ensure_schema_adds_missing():
    nc, rec = _client([(200, {"properties": {"Depth": {}}}, None), (200, {}, None)])
    nc.ensure_schema()
    added = json.loads(rec.requests[1].content)["properties"]
    assert set(added) == {"Run ID", "Tokens used", "Report"}
