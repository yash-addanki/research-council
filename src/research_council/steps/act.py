"""Step 9: for build topics, star/fork/clone the chosen repos and ask before any building starts."""

from datetime import datetime, timezone
from pathlib import Path

from research_council import repos
from research_council.repos import RepoCandidate, act_on, filter_and_rank
from research_council.steps.context import RunContext


def run(ctx: RunContext) -> Path:
    brief = ctx.read_json("brief.json")
    if brief["kind"] != "build" or not ctx.path("repos.json").exists():
        return ctx.write_json("act.json", {"skipped": True, "reason": "knowledge topic"})
    cands = []
    for r in ctx.read_json("repos.json")[:8]:
        meta = repos.fetch_meta(r["full_name"])
        if meta:
            cands.append(RepoCandidate(r["full_name"], meta["url"], meta["stars"] or 0,
                                       datetime.fromisoformat(meta["pushed_at"].replace("Z", "+00:00")),
                                       meta.get("description") or "", r["relevance"]))
    chosen = filter_and_rank(cands, datetime.now(timezone.utc))
    if not chosen:
        return ctx.write_json("act.json", {"skipped": True, "reason": "no repo active in the last 12 months"})
    note = f"Research topic: {ctx.topic.title}\nRun: {ctx.run_id} (full report on the Notion topic page)"
    paths = act_on(chosen, ctx.cfg.paths.gitrepos, ctx.dry_run, report_note=note)
    names = [c.full_name for c in chosen]
    answer = "skipped"
    if not ctx.dry_run and ctx.notifier and hasattr(ctx.notifier, "ask"):
        answer = ctx.notifier.ask(f"Ready to start building '{ctx.topic.title}' with {', '.join(names)}? "
                                  f"Cloned to {', '.join(str(p) for p in paths)}.")
    return ctx.write_json("act.json", {"skipped": False, "repos": names, "paths": [str(p) for p in paths],
                                       "ready_to_build": answer})
