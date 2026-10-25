"""This tool's own past runs as evidence, for topics about improving the research council itself."""

import json
from pathlib import Path

from research_council.evidence import EvidenceItem, now_iso
from research_council.state import State

PREFIX = "runs://"
KEEP = ("title", "depth", "status", "current_step", "steps_done", "steps_total", "blocked", "evidence_items",
        "citations", "answers", "tokens")


def items(runs_dir: Path, state: State, now: float, skip: str = "", limit: int = 10) -> list[EvidenceItem]:
    from research_council.dashboard import run_summary  # dashboard imports the conductor, which imports the steps

    out = []
    runs = sorted((t.parent for t in Path(runs_dir).glob("*/topic.json") if t.parent.name != skip),
                  key=lambda d: (d / "topic.json").stat().st_mtime, reverse=True)
    for run_dir in runs[:limit]:
        s = run_summary(run_dir, state, now)
        facts = {k: s[k] for k in KEEP}
        missing = run_dir / "missing.json"
        if missing.exists():
            facts["council_member_errors"] = json.loads(missing.read_text())
        out.append(EvidenceItem(PREFIX + run_dir.name, f"Research council run: {s['title']}", "run-history",
                                json.dumps(facts, ensure_ascii=False), None, now_iso()))
    return out
