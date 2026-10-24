"""Steps 6-7: early-stop check, then one anonymous cross-review round on disputed claims only."""

import json
import random
from pathlib import Path

from research_council.prompts import render
from research_council.steps.context import RunContext
from research_council.steps.council import MEMBERS, load_answers
from research_council.steps.util import parse_json

SUPPORT_THRESHOLD = 0.9


def support_by_claim(citations: list[dict]) -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = {}
    for c in citations:
        out.setdefault((c["member"], c["id"]), set()).add(c["label"])
    return out


def is_supported(labels: set[str]) -> bool:
    return "supported" in labels


def should_skip_review(answers: dict, citations: list[dict], agree: bool) -> bool:
    if not agree:
        return False
    support = support_by_claim(citations)
    keys = [(m, c["id"]) for m, a in answers.items() for c in a.get("claims", []) if (m, c["id"]) in support]
    if not keys:
        return False
    return sum(is_supported(support[k]) for k in keys) / len(keys) >= SUPPORT_THRESHOLD


def _agreement(ctx: RunContext, answers: dict) -> dict:
    conclusions = "\n".join(f"- {a['conclusion']}" for a in answers.values())
    prompt = ("Do these research conclusions agree on the key points? Reply ONLY with JSON "
              '{"agree": true|false, "points": ["each point of disagreement"]}\n\n' + conclusions)
    for name in ctx.available(["gemini", "codex", "claude"]):
        res = ctx.call(name, prompt, "cheap", step="review")
        data = parse_json(res.text) if res.ok else None
        if isinstance(data, dict) and "agree" in data:
            return data
    return {"agree": False, "points": []}


def run(ctx: RunContext) -> Path:
    answers = {m: a for m, a in load_answers(ctx).items() if a.get("claims")}
    citations = ctx.read_json("citations.json")
    if ctx.depth == "Low" or len(answers) < 2:
        return ctx.write_json("review.json", {"skipped": True, "reason": "low depth or single member"})
    agreement = _agreement(ctx, answers)
    if should_skip_review(answers, citations, agreement.get("agree", False)):
        return ctx.write_json("review.json", {"skipped": True, "reason": "early stop: agreement and sources hold"})
    support = support_by_claim(citations)
    names = list(answers)
    random.shuffle(names)
    letters = {m: chr(ord("A") + i) for i, m in enumerate(names)}
    disputed = [
        {"id": f"{letters[m]}.{c['id']}", "claim": c["claim"], "source_urls": c.get("source_urls", [])}
        for m, a in answers.items() for c in a["claims"] if not is_supported(support.get((m, c["id"]), set()))
    ]
    anon_cits = [{"id": f"{letters[c['member']]}.{c['id']}", "url": c["url"], "label": c["label"]}
                 for c in citations if c["member"] in letters]
    prompt = render("review", question=ctx.read_json("brief.json")["question"],
                    disputed=json.dumps({"claims": disputed, "disagreements": agreement.get("points", [])}, indent=1),
                    citations=json.dumps(anon_cits, indent=1))
    verdicts = {}
    for name in ctx.available([m for m in MEMBERS if m in answers]):
        res = ctx.call(name, prompt, "mid", step="review", web=True)
        data = parse_json(res.text) if res.ok else None
        if isinstance(data, dict):
            verdicts[letters[name]] = data.get("verdicts", [])
    return ctx.write_json("review.json", {"skipped": False, "letters": {v: k for k, v in letters.items()},
                                          "disputed": disputed, "disagreements": agreement.get("points", []),
                                          "verdicts": verdicts})
