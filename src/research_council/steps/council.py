"""Step 4: each council member answers the brief independently."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from research_council.prompts import render
from research_council.steps.context import RunContext
from research_council.steps.util import evidence_text, parse_json

MEMBERS = ["claude", "codex", "gemini"]


def load_evidence(ctx: RunContext) -> list[dict]:
    p = ctx.path("evidence.jsonl")
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def load_answers(ctx: RunContext) -> dict[str, dict]:
    answers = {p.name[len("answer."):-len(".json")]: json.loads(p.read_text())
               for p in sorted(ctx.run_dir.glob("answer.*.json"))}
    for p in sorted(ctx.run_dir.glob("deep.*.md")):  # app Deep Research reports, free text
        answers[p.name[len("deep."):-len(".md")]] = {"conclusion": p.read_text(), "claims": [], "repos": []}
    return answers


def run(ctx: RunContext) -> Path:
    brief = ctx.read_json("brief.json")
    extra = "This is a build topic: fill \"repos\" with the best candidate GitHub repos." if brief["kind"] == "build" else ""
    prompt = render("council", brief=json.dumps(brief, indent=1), evidence=evidence_text(load_evidence(ctx)), extra=extra)
    missing = {}

    def ask(name):
        res = ctx.call(name, prompt, "mid", step="council", web=True, timeout_s=1500)
        data = parse_json(res.text) if res.ok else None
        if not isinstance(data, dict) or "claims" not in data:
            return name, None, res.error or "reply was not valid JSON"
        return name, data, None

    with ThreadPoolExecutor(len(MEMBERS)) as pool:
        for name, data, err in pool.map(ask, MEMBERS):
            if data is None:
                missing[name] = err
            else:
                data.setdefault("repos", [])
                ctx.write_json(f"answer.{name}.json", data)
    return ctx.write_json("missing.json", missing)
