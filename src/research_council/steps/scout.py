"""Step 2: gather evidence from the web, social platforms and GitHub into evidence.jsonl."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from research_council.evidence import EvidenceItem, dedupe, now_iso
from research_council.prompts import render
from research_council.sources import agent_reach, github, hn
from research_council.steps.context import RunContext
from research_council.steps.util import parse_json

log = logging.getLogger(__name__)
SCOUTS = ["gemini", "codex", "claude"]  # cheapest-quota first; Claude quota is the scarcest
SOCIAL_SOURCES = {"hn": hn.search, **agent_reach.SOURCES}
REPO_SOURCE = github.search
SOCIAL_SHARE = 0.35


def web_search(ctx: RunContext, query: str, limit: int) -> list[EvidenceItem]:
    question = ctx.read_json("brief.json")["question"]
    for name in ctx.available(SCOUTS):
        res = ctx.call(name, render("scout", query=query, question=question, limit=str(limit)), "cheap",
                       step="scout", web=True)
        rows = parse_json(res.text) if res.ok else None
        if isinstance(rows, list):
            return [EvidenceItem(r["url"], r.get("title", ""), "web", r.get("excerpt", ""), r.get("published_at"),
                                 now_iso()) for r in rows if isinstance(r, dict) and r.get("url")]
    return []


def _safe(fn, *args) -> list[EvidenceItem]:
    try:
        return fn(*args)
    except Exception as exc:
        log.warning("source failed: %s", exc)
        return []


def run(ctx: RunContext) -> Path:
    brief = ctx.read_json("brief.json")
    cap = ctx.cfg.caps[f"evidence_{ctx.depth.lower()}"]
    per = max(3, cap // max(1, len(brief["angles"])))
    with ThreadPoolExecutor(4) as pool:
        web = pool.map(lambda q: _safe(web_search, ctx, q, per), brief["angles"])
        social = [pool.submit(_safe, fn, q, per) for q in brief["social_queries"] for fn in SOCIAL_SOURCES.values()]
        repos = [pool.submit(_safe, REPO_SOURCE, q, 10) for q in brief.get("repo_queries", [])]
        web_items = dedupe([i for chunk in web for i in chunk])
        social_items = dedupe([i for f in social for i in f.result()])
        repo_items = dedupe([i for f in repos for i in f.result()])
    # keep a guaranteed share for social and repo evidence, fill the rest with web
    n_social = min(len(social_items), int(cap * SOCIAL_SHARE))
    n_repo = min(len(repo_items), cap // 6)
    chosen = social_items[:n_social] + repo_items[:n_repo]
    chosen += web_items[: cap - len(chosen)]
    leftovers = social_items[n_social:] + repo_items[n_repo:]
    chosen = dedupe(chosen + leftovers)[:cap]
    path = ctx.path("evidence.jsonl")
    path.write_text("".join(json.dumps(i.to_dict(), ensure_ascii=False) + "\n" for i in chosen))
    return path
