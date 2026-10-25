"""Machine-readable snapshot of every run, for the bob-research Claude Code mod."""

import json
import time
from pathlib import Path

from research_council.conductor import OUTPUTS, STEPS
from research_council import quota
from research_council.state import State

MODELS = ("claude", "codex", "gemini")


def _count_lines(path: Path) -> int:
    return sum(1 for line in path.read_text().splitlines() if line.strip()) if path.exists() else 0


def _citations(path: Path) -> dict[str, int]:
    """Count citation-check labels: supported, partial, unsupported, unreachable, unchecked."""
    counts: dict[str, int] = {}
    for item in json.loads(path.read_text()) if path.exists() else []:
        counts[item.get("label", "unchecked")] = counts.get(item.get("label", "unchecked"), 0) + 1
    return counts


def run_summary(run_dir: Path, state: State, now: float) -> dict:
    topic = json.loads((run_dir / "topic.json").read_text())
    done = [s for s in STEPS if (run_dir / OUTPUTS[s]).exists()]
    current = next((s for s in STEPS if s not in done), None)
    blocked = json.loads((run_dir / "blocked.json").read_text()) if (run_dir / "blocked.json").exists() else None
    if current is None:
        status = "done"
    elif blocked:
        status = "blocked"
    elif state.lease_active(topic["page_id"], now):
        status = "running"
    else:
        status = "stopped"

    per_model: dict[str, dict] = {}
    per_step: dict[str, int] = {}
    for r in state.usage_for_run(run_dir.name):
        m = per_model.setdefault(r.model, {"calls": 0, "tokens_in": 0, "tokens_out": 0})
        m["calls"] += 1
        m["tokens_in"] += r.tokens_in
        m["tokens_out"] += r.tokens_out
        per_step[r.step] = per_step.get(r.step, 0) + r.tokens_in + r.tokens_out
    mtimes = [p.stat().st_mtime for p in run_dir.iterdir()]
    started = (run_dir / "topic.json").stat().st_mtime
    return {
        "run_id": run_dir.name,
        "title": topic.get("title", ""),
        "page_id": topic.get("page_id", ""),
        "priority": topic.get("priority"),
        "depth": topic.get("depth"),
        "tags": topic.get("tags", []),
        "status": status,
        "current_step": current,
        "steps_done": len(done),
        "steps_total": len(STEPS),
        "blocked": blocked,
        "started_at": started,
        "updated_at": max(mtimes),
        "duration_s": round(max(mtimes) - started),
        "evidence_items": _count_lines(run_dir / OUTPUTS["scout"]),
        "citations": _citations(run_dir / OUTPUTS["citations"]),
        "answers": sorted(p.name[len("answer."):-len(".json")] for p in run_dir.glob("answer.*.json")),
        "deep_apps": sorted(p.name[len("deep."):-len(".md")] for p in run_dir.glob("deep.*.md")),
        "tokens": {
            "total": sum(m["tokens_in"] + m["tokens_out"] for m in per_model.values()),
            "by_model": per_model,
            "by_step": per_step,
        },
        "report": str(run_dir / "final_report.md") if (run_dir / "final_report.md").exists() else None,
    }


def snapshot(runs_dir: Path, db: Path, now: float | None = None, codex_used=None) -> dict:
    now = time.time() if now is None else now
    state = State(db)
    runs = [run_summary(t.parent, state, now) for t in Path(runs_dir).glob("*/topic.json")]
    runs.sort(key=lambda r: r["started_at"], reverse=True)
    try:
        codex = (codex_used or quota.codex_used_percent)()
    except Exception:
        codex = None
    usage = {m: {"calls_5h": state.calls_since(m, now - quota.WINDOW_S), "cooldown": state.in_cooldown(m, now)}
             for m in MODELS}
    usage["codex"]["used_percent"] = codex
    totals = {
        "runs": len(runs),
        "done": sum(r["status"] == "done" for r in runs),
        "running": sum(r["status"] == "running" for r in runs),
        "blocked": sum(r["status"] == "blocked" for r in runs),
        "tokens": sum(r["tokens"]["total"] for r in runs),
    }
    return {"generated_at": now, "totals": totals, "quota": usage, "runs": runs}
