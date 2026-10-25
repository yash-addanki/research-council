"""Step 5: check that each cited source actually supports its claim."""

from pathlib import Path

from research_council.prompts import render
from research_council.sources.crawl import best_passage, fetch_text, page_url
from research_council.steps.context import RunContext
from research_council.steps.council import load_answers
from research_council.steps.util import parse_json

CHECKERS = ["gemini", "codex", "claude"]
BATCH = 8
PAGE_CHARS = 3000
MAX_PAIRS = 60


def run(ctx: RunContext) -> Path:
    pairs = []
    for member, ans in load_answers(ctx).items():
        for c in ans.get("claims", []):
            if ctx.depth == "Low" and c.get("confidence", 0) < 0.7:
                continue
            for url in c.get("source_urls", [])[:2]:
                pairs.append({"member": member, "id": c["id"], "claim": c["claim"], "url": url})
    pairs = pairs[:MAX_PAIRS]
    results, to_check = [], []
    for p in pairs:
        page = fetch_text(page_url(p["url"]), max_chars=60000)
        if page is not None:
            page = best_passage(page, p["claim"], PAGE_CHARS)  # the part of the page about this claim
        if page is None:
            results.append({"member": p["member"], "id": p["id"], "url": p["url"], "label": "unreachable"})
        else:
            to_check.append((p, page))
    for i in range(0, len(to_check), BATCH):
        batch = to_check[i:i + BATCH]
        body = "\n\n".join(f"### Pair {n}\nClaim: {p['claim']}\nSource {p['url']}:\n{page}" for n, (p, page) in enumerate(batch))
        labels = {}
        for name in ctx.available(CHECKERS):
            res = ctx.call(name, render("citation", count=str(len(batch)), evidence=body), "cheap", step="citations")  # mid tier thought ~17k tokens per batch
            data = parse_json(res.text) if res.ok else None
            if isinstance(data, dict) and isinstance(data.get("results"), list):
                labels = {r.get("n"): r.get("label") for r in data["results"] if isinstance(r, dict)}
                break
        for n, (p, _) in enumerate(batch):
            label = labels.get(n)
            results.append({"member": p["member"], "id": p["id"], "url": p["url"],
                            "label": label if label in ("supported", "partial", "unsupported") else "unchecked"})
    return ctx.write_json("citations.json", results)
