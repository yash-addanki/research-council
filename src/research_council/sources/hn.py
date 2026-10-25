"""Hacker News search via the free Algolia API."""

import logging

import httpx

from research_council.evidence import EvidenceItem, now_iso

log = logging.getLogger(__name__)
API = "https://hn.algolia.com/api/v1/search"


def search(query: str, limit: int, client: httpx.Client | None = None) -> list[EvidenceItem]:
    client = client or httpx.Client(timeout=20)
    try:
        resp = client.get(API, params={"query": query, "tags": "story", "hitsPerPage": limit})
        resp.raise_for_status()
        hits = resp.json()["hits"]
    except Exception as exc:  # source failures never stop a run
        log.warning("hn search failed: %s", exc)
        return []
    items = []
    for h in hits[:limit]:
        discussion = f"https://news.ycombinator.com/item?id={h['objectID']}"
        excerpt = f"{h.get('points', 0)} points, {h.get('num_comments', 0)} comments. {h.get('story_text') or ''}".strip()
        items.append(EvidenceItem(
            url=h.get("url") or discussion, title=h.get("title", ""), platform="hn",
            excerpt=f"{excerpt} Discussion: {discussion}", published_at=h.get("created_at"), fetched_at=now_iso(),
        ))
    return items
