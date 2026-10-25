"""Step 2: gather evidence from the web, social platforms and GitHub into evidence.jsonl."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from research_council.evidence import EvidenceItem, dedupe, now_iso
from research_council.prompts import render
from research_council.sources import agent_reach, github, hn, run_history
from research_council.sources.crawl import best_passage, fetch_text, page_url
from research_council.steps.context import RunContext
from research_council.steps.util import parse_json

log = logging.getLogger(__name__)
SCOUTS = ["codex", "claude"]  # need live web search (agy has none headless); Claude quota is the scarcest
SOCIAL_SOURCES = {"hn": hn.search, **agent_reach.SOURCES}
REPO_SOURCE = github.search
SOCIAL_SHARE = 0.35
EXCERPT_CHARS = 1500


def web_search(ctx: RunContext, queries: list[str], limit: int) -> list[EvidenceItem]:
    """One web-search call covers every angle; a call per angle re-pays the CLI's fixed overhead each time."""
    question = ctx.read_json("brief.json")["question"]
    prompt = render("scout", queries="\n".join(f"- {q}" for q in queries), question=question, limit=str(limit))
    for name in ctx.available(SCOUTS):
        res = ctx.call(name, prompt, "cheap", step="scout", web=True)
        rows = parse_json(res.text) if res.ok else None
        if isinstance(rows, list):
            return [EvidenceItem(r["url"], r.get("title", ""), "web", r.get("excerpt", ""), r.get("published_at"),
                                 now_iso()) for r in rows if isinstance(r, dict) and r.get("url")]
    return []


def with_page_text(item: EvidenceItem, question: str) -> EvidenceItem:
    """Swap a model-written summary for the page's own most relevant passage, so later checks see real text."""
    page = fetch_text(page_url(item.url), max_chars=60000)
    if page and len(page) > len(item.excerpt):
        item.excerpt = best_passage(page, f"{question} {item.title}", EXCERPT_CHARS)
    return item


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
        web = [pool.submit(_safe, web_search, ctx, brief["angles"], cap)]
        social = [pool.submit(_safe, fn, q, per) for q in brief["social_queries"] for fn in SOCIAL_SOURCES.values()]
        repos = [pool.submit(_safe, REPO_SOURCE, q, 10) for q in brief.get("repo_queries", [])]
        web_items = dedupe([i for f in web for i in f.result()])
        social_items = dedupe([i for f in social for i in f.result()])
        repo_items = dedupe([i for f in repos for i in f.result()])
    # keep a guaranteed share for social and repo evidence, fill the rest with web
    n_social = min(len(social_items), int(cap * SOCIAL_SHARE))
    n_repo = min(len(repo_items), cap // 6)
    chosen = social_items[:n_social] + repo_items[:n_repo]
    chosen += web_items[: cap - len(chosen)]
    leftovers = social_items[n_social:] + repo_items[n_repo:]
    chosen = dedupe(chosen + leftovers)[:cap]
    with ThreadPoolExecutor(4) as pool:
        chosen = list(pool.map(lambda i: with_page_text(i, brief["question"]) if i.platform == "web" else i, chosen))
    if brief.get("about_this_tool"):  # the tool's own runs are the evidence the web can't have
        chosen = run_history.items(ctx.run_dir.parent, ctx.state, ctx.clock(), skip=ctx.run_dir.name) + chosen
    path = ctx.path("evidence.jsonl")
    path.write_text("".join(json.dumps(i.to_dict(), ensure_ascii=False) + "\n" for i in chosen))
    return path
