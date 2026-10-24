"""High-depth runs: drive Gemini Deep Research, ChatGPT Deep Research and Muse in Yash's Chrome via `claude --chrome`."""

import json
import time
from pathlib import Path

from research_council.prompts import render
from research_council.steps.context import RunContext
from research_council.steps.util import parse_json

WAIT_S = 30 * 60
SLEEP = time.sleep
RUNNER = "chrome"  # a ClaudeRunner(chrome=True) registered in ctx.runners


def submit(ctx: RunContext) -> Path:
    if ctx.depth != "High":
        return ctx.write_json("deep_submit.json", {"skipped": True, "reason": "depth below High"})
    if ctx.dry_run or not (ctx.notifier and hasattr(ctx.notifier, "ask")):
        return ctx.write_json("deep_submit.json", {"skipped": True, "reason": "no approval channel / dry run"})
    title = ctx.topic.title
    if ctx.notifier.ask(f"Send '{title}' to Gemini Deep Research, ChatGPT Deep Research and Muse in Chrome? "
                        "Chrome must be open on the Mac.") != "yes":
        return ctx.write_json("deep_submit.json", {"skipped": True, "reason": "not approved"})
    brief = ctx.read_json("brief.json")
    text = f"{brief['question']}\n\nWhat a good answer covers: " + "; ".join(brief.get("success_criteria", []))
    res = ctx.call(RUNNER, render("chrome_submit", brief=text), "mid", step="deep_submit", timeout_s=900)
    tabs = parse_json(res.text) if res.ok else None
    if not isinstance(tabs, dict):
        return ctx.write_json("deep_submit.json", {"skipped": True, "reason": res.error or "no tab list returned"})
    return ctx.write_json("deep_submit.json", {"skipped": False, "submitted_at": ctx.clock(), "tabs": tabs})


def collect(ctx: RunContext) -> list[Path]:
    p = ctx.path("deep_submit.json")
    if not p.exists():
        return []
    sub = json.loads(p.read_text())
    if sub.get("skipped"):
        return []
    live = {app: url for app, url in sub["tabs"].items() if not str(url).startswith("blocked")}
    missing = {app: url for app, url in sub["tabs"].items() if app not in live}
    wait = sub["submitted_at"] + WAIT_S - ctx.clock()
    if wait > 0:
        SLEEP(wait)
    paths = []
    if live:
        res = ctx.call(RUNNER, render("chrome_collect", tabs=json.dumps(live, indent=1)), "mid", step="deep_collect",
                       timeout_s=900)
        reports = parse_json(res.text) if res.ok else None
        reports = reports if isinstance(reports, dict) else {}
        for app in live:
            text = str(reports.get(app) or "unfinished: no report returned")
            if text.startswith(("unfinished", "blocked")) or len(text) < 200 and not text.startswith("Gemini"):
                missing[app] = text
                continue
            out = ctx.path(f"deep.{app}.md")
            out.write_text(text)
            paths.append(out)
    ctx.write_json("deep_missing.json", missing)
    return paths
