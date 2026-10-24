"""Minimal Notion REST client for the ResearchTopics queue."""

import re
import time
from dataclasses import dataclass, field

import httpx

API = "https://api.notion.com/v1"
VERSION = "2025-09-03"
PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
NEW_PROPERTIES = {
    "Depth": {"select": {"options": [{"name": "Low"}, {"name": "Medium"}, {"name": "High"}]}},
    "Run ID": {"rich_text": {}},
    "Tokens used": {"number": {}},
    "Report": {"url": {}},
}


@dataclass
class Topic:
    page_id: str
    title: str
    notes: str
    priority: str | None
    tags: list[str] = field(default_factory=list)
    depth: str = "Low"


def _plain(prop: dict) -> str:
    items = prop.get("title") or prop.get("rich_text") or []
    return "".join(i.get("plain_text", "") for i in items)


def _select(prop: dict | None) -> str | None:
    return ((prop or {}).get("select") or {}).get("name")


def chunk_text(s: str, limit: int = 2000) -> list[str]:
    """Split on paragraph breaks where possible, hard-split anything longer than limit."""
    chunks: list[str] = []
    for para in s.split("\n\n"):
        while len(para) > limit:
            chunks.append(para[:limit])
            para = para[limit:]
        if para:
            chunks.append(para)
    return chunks


def _rt(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": c}} for c in chunk_text(text, 2000)] or [
        {"type": "text", "text": {"content": ""}}]


def markdown_to_blocks(md: str) -> list[dict]:
    blocks = []
    for para in md.split("\n\n"):
        lines = para.strip().split("\n")
        if not lines[0]:
            continue
        if all(re.match(r"^[-*] ", ln) for ln in lines):
            for ln in lines:
                blocks.append({"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rt(ln[2:])}})
            continue
        m = re.match(r"^(#{1,3}) (.*)", lines[0])
        if m and len(lines) == 1:
            kind = f"heading_{len(m.group(1))}"
            blocks.append({"type": kind, kind: {"rich_text": _rt(m.group(2))}})
            continue
        for piece in chunk_text("\n".join(lines), 2000 * 50):
            blocks.append({"type": "paragraph", "paragraph": {"rich_text": _rt(piece)}})
    return blocks


class NotionClient:
    def __init__(self, token: str, data_source_id: str, rate_per_s: float = 2.5,
                 client: httpx.Client | None = None, sleep=time.sleep):
        self.ds = data_source_id
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"Authorization": f"Bearer {token}", "Notion-Version": VERSION}
        self.min_gap = 1.0 / rate_per_s
        self.sleep = sleep
        self._last = 0.0

    def _req(self, method: str, path: str, json: dict | None = None, attempts: int = 4) -> dict:
        for _ in range(attempts):
            gap = self.min_gap - (time.monotonic() - self._last)
            if gap > 0:
                self.sleep(gap)
            self._last = time.monotonic()
            resp = self.client.request(method, API + path, json=json, headers=self.headers)
            if resp.status_code in (429, 529) or resp.status_code >= 500 and method == "GET":
                self.sleep(float(resp.headers.get("Retry-After", 2)))
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()
        return resp.json()

    def next_topic(self) -> Topic | None:
        pages, cursor = [], None
        while True:
            body = {"filter": {"property": "Status", "status": {"equals": "To Research"}}, "page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            data = self._req("POST", f"/data_sources/{self.ds}/query", body)
            pages += data["results"]
            if not data.get("has_more"):
                break
            cursor = data["next_cursor"]
        if not pages:
            return None
        pages.sort(key=lambda p: (PRIORITY_ORDER.get(_select(p["properties"].get("Priority")), 3), p["created_time"]))
        return self._topic(pages[0])

    def get_topic(self, page_id: str) -> Topic:
        return self._topic(self._req("GET", f"/pages/{page_id}"))

    def _topic(self, page: dict) -> Topic:
        props = page["properties"]
        priority = _select(props.get("Priority"))
        depth = _select(props.get("Depth")) or (priority if priority in ("High", "Medium") else "Low")
        return Topic(
            page_id=page["id"], title=_plain(props["Idea / Question"]), notes=_plain(props.get("Notes", {})),
            priority=priority, tags=[t["name"] for t in props.get("Tags", {}).get("multi_select", [])], depth=depth,
        )

    def set_status(self, page_id: str, status: str) -> None:
        self._req("PATCH", f"/pages/{page_id}", {"properties": {"Status": {"status": {"name": status}}}})

    def set_props(self, page_id: str, *, run_id=None, tokens_used=None, report_url=None, notes=None) -> None:
        props = {}
        if run_id is not None:
            props["Run ID"] = {"rich_text": [{"text": {"content": run_id}}]}
        if tokens_used is not None:
            props["Tokens used"] = {"number": tokens_used}
        if report_url is not None:
            props["Report"] = {"url": report_url}
        if notes is not None:
            props["Notes"] = {"rich_text": [{"text": {"content": c}} for c in chunk_text(notes)]}
        self._req("PATCH", f"/pages/{page_id}", {"properties": props})

    def append_markdown(self, page_id: str, md: str) -> None:
        blocks = markdown_to_blocks(md)
        for i in range(0, len(blocks), 100):
            self._req("PATCH", f"/blocks/{page_id}/children", {"children": blocks[i:i + 100]})

    def ensure_schema(self) -> None:
        have = self._req("GET", f"/data_sources/{self.ds}")["properties"]
        missing = {k: v for k, v in NEW_PROPERTIES.items() if k not in have}
        if missing:
            self._req("PATCH", f"/data_sources/{self.ds}", {"properties": missing})
