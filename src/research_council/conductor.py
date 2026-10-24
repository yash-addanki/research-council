"""Runs the research steps in order, resumes from saved step files, and applies the failure policy."""

import json
import logging
from pathlib import Path
from typing import Callable

from research_council.steps import brief, chairman, citations, council, review, scout
from research_council.steps.context import RunContext
from research_council.tokens import token_table, total_tokens

log = logging.getLogger(__name__)

STEPS = ["brief", "scout", "deep_submit", "council", "citations", "review", "chairman", "act", "report"]
OUTPUTS = {
    "brief": "brief.json", "scout": "evidence.jsonl", "deep_submit": "deep_submit.json", "council": "missing.json",
    "citations": "citations.json", "review": "review.json", "chairman": "report.md", "act": "act.json",
    "report": "report_done.json",
}
ATTEMPTS = 2


class Blocked(RuntimeError):
    pass


class LeaseLost(RuntimeError):
    pass


def _skipped(name: str) -> Callable[[RunContext], Path]:
    def step(ctx: RunContext) -> Path:
        return ctx.write_json(OUTPUTS[name], {"skipped": True, "reason": "not enabled yet"})
    return step


def report_step(ctx: RunContext) -> Path:
    rows = ctx.state.usage_for_run(ctx.run_id)
    apps = sorted(p.name[len("deep."):-len(".md")] for p in ctx.run_dir.glob("deep.*.md"))
    report = ctx.path("report.md").read_text()
    full = f"{report.rstrip()}\n\n## Tokens used\n\n{token_table(rows, apps)}\n"
    ctx.path("final_report.md").write_text(full)
    total = total_tokens(rows)
    answer = report.split("## Answer", 1)[-1].strip().split("\n\n")[0].replace("\n", " ")[:300]
    summary = f"Research done: {ctx.topic.title}\n{answer}\n{total:,} tokens used."
    if ctx.dry_run:
        print(full)
        print(summary)
    else:
        ctx.notion.append_markdown(ctx.topic.page_id, full)
        ctx.notion.set_props(ctx.topic.page_id, run_id=ctx.run_id, tokens_used=total)
        ctx.notion.set_status(ctx.topic.page_id, "Resolved")
        if ctx.notifier:
            ctx.notifier.notify(summary)
    return ctx.write_json(OUTPUTS["report"], {"tokens": total})


DEFAULT_STEPS: dict[str, Callable[[RunContext], Path]] = {
    "brief": brief.run, "scout": scout.run, "deep_submit": _skipped("deep_submit"), "council": council.run,
    "citations": citations.run, "review": review.run, "chairman": chairman.run, "act": _skipped("act"),
    "report": report_step,
}


class Pipeline:
    def __init__(self, ctx: RunContext, notion, notifier, lease_version: int, steps=None):
        self.ctx, self.notion, self.notifier = ctx, notion, notifier
        self.lease_version = lease_version
        self.steps = steps or DEFAULT_STEPS
        ctx.notion, ctx.notifier = notion, notifier

    def _block(self, step: str, reason: str):
        msg = f"Blocked at {step}: {reason}"
        log.error(msg)
        if not self.ctx.dry_run:
            notes = f"{self.ctx.topic.notes}\n{msg}".strip()
            self.notion.set_props(self.ctx.topic.page_id, notes=notes)
            self.notion.set_status(self.ctx.topic.page_id, "Blocked")
            if self.notifier:
                self.notifier.notify(f"Research Blocked: {self.ctx.topic.title}\n{msg}")
        raise Blocked(msg)

    def run(self) -> Path:
        ctx = self.ctx
        for name in STEPS:
            if not ctx.state.heartbeat(ctx.topic.page_id, self.lease_version, ctx.clock()):
                raise LeaseLost(f"lease on {ctx.topic.page_id} was taken by another run")
            out = ctx.path(OUTPUTS[name])
            if out.exists():
                continue
            last_error = None
            for _ in range(ATTEMPTS):
                try:
                    self.steps[name](ctx)
                    last_error = None
                    break
                except Exception as exc:  # any step failure gets one retry, then Blocked
                    last_error = exc
                    log.warning("step %s failed: %s", name, exc)
            if last_error is not None:
                self._block(name, str(last_error))
            if name == "council" and not list(ctx.run_dir.glob("answer.*.json")) \
                    and not list(ctx.run_dir.glob("deep.*.md")):
                missing = json.loads(out.read_text()) if out.exists() else {}
                out.unlink(missing_ok=True)  # let a resume retry the council
                self._block(name, "no council member answered (" + "; ".join(f"{k}: {v}" for k, v in missing.items()) + ")")
        return ctx.path("final_report.md")


def run_pipeline(ctx: RunContext, notion, notifier, lease_version: int) -> Path:
    return Pipeline(ctx, notion, notifier, lease_version).run()
