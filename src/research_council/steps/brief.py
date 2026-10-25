"""Step 1: turn a one-line Notion topic into a research brief."""

import json
from pathlib import Path

from research_council.prompts import render
from research_council.steps.context import RunContext
from research_council.steps.util import parse_json


def fallback(ctx: RunContext) -> dict:
    t = ctx.topic.title
    return {"question": t, "reading_chosen": "model brief unavailable; using the title as-is",
            "success_criteria": [f"A sourced answer to: {t}"], "kind": "knowledge",
            "angles": [t, f"{t} best practices 2026", f"{t} comparison"],
            "social_queries": [t], "repo_queries": []}


def run(ctx: RunContext) -> Path:
    t = ctx.topic
    prompt = render("brief", title=t.title, notes=t.notes or "(none)", tags=", ".join(t.tags) or "(none)")
    res = ctx.call("claude", prompt, "cheap", step="brief")
    data = parse_json(res.text) if res.ok else None
    if not isinstance(data, dict) or not data.get("question") or not data.get("angles"):
        data = fallback(ctx)
    data.setdefault("social_queries", [data["question"]])
    data.setdefault("repo_queries", [])
    if data.get("kind") not in ("build", "knowledge"):
        data["kind"] = "knowledge"
    return ctx.write_json("brief.json", data)
