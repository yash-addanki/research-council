"""Reddit, X and YouTube search through the Agent-Reach CLI (logins live in its own browser profile)."""

import json
import logging
import subprocess
from functools import partial

from research_council.evidence import EvidenceItem, now_iso

log = logging.getLogger(__name__)
URL_KEYS = ("url", "link", "permalink", "webpage_url")
TITLE_KEYS = ("title", "text", "name")
DATE_KEYS = ("created_utc", "created_at", "date", "published_at", "upload_date", "timestamp")
TEXT_KEYS = ("selftext", "text", "description", "snippet", "content")
STAT_KEYS = ("score", "num_comments", "likes", "retweets", "view_count", "replies")


def _first(d: dict, keys) -> str | None:
    for k in keys:
        if d.get(k) not in (None, ""):
            return str(d[k])
    return None


def _rows(result) -> list[dict]:
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    if isinstance(result, dict):
        for key in ("items", "results", "posts", "videos", "tweets", "data"):
            if isinstance(result.get(key), list):
                return _rows(result[key])
    return []


def search_channel(channel: str, query: str, limit: int, timeout_s: int = 120) -> list[EvidenceItem]:
    try:
        proc = subprocess.run(["agent-reach", channel, "search", query, "--limit", str(limit)],
                              capture_output=True, text=True, timeout=timeout_s, stdin=subprocess.DEVNULL)
        env = json.loads(proc.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        log.warning("agent-reach %s failed: %s", channel, exc)
        return []
    if not env.get("ok"):
        log.warning("agent-reach %s: %s", channel, (env.get("error") or {}).get("message"))
        return []
    items = []
    for r in _rows(env.get("result"))[:limit]:
        url = _first(r, URL_KEYS)
        if not url:
            continue
        stats = ", ".join(f"{k}={r[k]}" for k in STAT_KEYS if k in r)
        text = (_first(r, TEXT_KEYS) or "")[:500]
        items.append(EvidenceItem(url=url, title=(_first(r, TITLE_KEYS) or "")[:200], platform=channel,
                                  excerpt=f"{stats}. {text}".strip(". "), published_at=_first(r, DATE_KEYS),
                                  fetched_at=now_iso()))
    return items


SOURCES = {name: partial(search_channel, name) for name in ("reddit", "twitter", "youtube")}
