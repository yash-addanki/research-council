"""Step 8: the top Claude model writes the final report; repos are ranked deterministically."""

import json
import re
from pathlib import Path

from research_council.prompts import render
from research_council.steps.context import RunContext
from research_council.steps.council import load_answers
from research_council.steps.review import is_supported, support_by_claim


def rank_repos(answers: dict) -> list[dict]:
    pooled: dict[str, dict] = {}
    for a in answers.values():
        for r in a.get("repos", []):
            key = r["full_name"].lower()
            entry = pooled.setdefault(key, {"full_name": r["full_name"], "why": [], "scores": []})
            entry["why"].append(r.get("why", ""))
            entry["scores"].append(float(r.get("relevance", 0)))
    ranked = [{"full_name": e["full_name"], "why": " / ".join(w for w in e["why"] if w),
               "relevance": sum(e["scores"]) / len(e["scores"]), "votes": len(e["scores"])} for e in pooled.values()]
    return sorted(ranked, key=lambda r: (r["votes"], r["relevance"]), reverse=True)


def unverified_claims(answers: dict, citations: list[dict]) -> list[str]:
    support = support_by_claim(citations)
    return [c["claim"] for m, a in answers.items() for c in a.get("claims", [])
            if (m, c["id"]) in support and not is_supported(support[(m, c["id"])])]


def _covered(claim: str, report_words: set[str]) -> bool:
    words = {w for w in re.findall(r"[a-z0-9$.%]+", claim.lower()) if len(w) > 2}
    return not words or len(words & report_words) / len(words) >= 0.6  # the chairman paraphrases


def ensure_unverified(report: str, claims: list[str]) -> str:
    report_words = set(re.findall(r"[a-z0-9$.%]+", report.lower()))
    absent = {}
    for c in claims:
        if not _covered(c, report_words):
            absent.setdefault(" ".join(c.lower().split()).rstrip("."), " ".join(c.split()))  # members repeat claims
    if not absent:
        return report
    bullets = "".join(f"- {c}\n" for c in absent.values())
    marker = "## Unverified"
    if marker not in report:
        return report.rstrip() + f"\n\n{marker}\n\n{bullets}"
    head, tail = report.split(marker, 1)
    section, sep, rest = tail.partition("\n## ")  # add after the chairman's own list, before the next section
    listed = section.strip() + "\n" if section.strip() else ""
    return f"{head}{marker}\n\n{listed}{bullets}" + (f"\n## {rest}" if sep else "")


def run(ctx: RunContext) -> Path:
    answers = load_answers(ctx)
    citations = ctx.read_json("citations.json") if ctx.path("citations.json").exists() else []
    review = ctx.read_json("review.json") if ctx.path("review.json").exists() else {"skipped": True}
    brief = ctx.read_json("brief.json")
    missing = ctx.read_json("missing.json") if ctx.path("missing.json").exists() else {}
    anon = {f"Member {chr(ord('A') + i)}": a for i, a in enumerate(answers.values())}
    repos = rank_repos(answers)
    ctx.write_json("repos.json", repos)
    prompt = render(
        "chairman", brief=json.dumps(brief, indent=1), answers=json.dumps(anon, indent=1, ensure_ascii=False),
        citations=json.dumps(citations, indent=1), review=json.dumps(review, indent=1),
        missing=", ".join(f"{k} ({v})" for k, v in missing.items()) or "none",
        repo_section="## Repos (ranked table: repo, why, relevance, votes)\n" + json.dumps(repos[:8]) if brief["kind"] == "build" else "",
    )
    tier = "mid" if ctx.depth == "Low" else "top"
    res = ctx.call("claude", prompt, tier, step="chairman", timeout_s=1800)
    if not res.ok:
        raise RuntimeError(f"chairman failed: {res.error}")
    report = ensure_unverified(res.text.strip(), unverified_claims(answers, citations))
    path = ctx.path("report.md")
    path.write_text(report + "\n")
    return path
