"""Per-run context shared by every step, including the single gate for model calls."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from research_council.config import Config
from research_council.notion import Topic
from research_council.runners.base import RunResult, Runner
from research_council.state import State

COOLDOWN_S = 3 * 3600


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    topic: Topic
    depth: str
    runners: dict[str, Runner]
    state: State
    cfg: Config
    dry_run: bool = False
    clock: Callable[[], float] = time.time
    _calls: dict[str, int] = field(default_factory=dict)

    def call(self, runner_name: str, prompt: str, tier: str, step: str, web: bool = False,
             timeout_s: int = 900) -> RunResult:
        now = self.clock()
        runner = self.runners.get(runner_name)
        if runner is None:
            return RunResult("", 0, 0, runner_name, error=f"{runner_name}: not configured")
        if self.state.in_cooldown(runner_name, now):
            return RunResult("", 0, 0, runner_name, error=f"{runner_name}: in cooldown")
        cap = self.cfg.caps["calls_per_model_per_run"]
        if self._calls.get(runner_name, 0) >= cap:
            return RunResult("", 0, 0, runner_name, error=f"{runner_name}: per-run call cap {cap} reached")
        self._calls[runner_name] = self._calls.get(runner_name, 0) + 1
        res = runner.run(prompt, tier, web=web, timeout_s=timeout_s)
        self.state.record_usage(self.run_id, step, runner_name, res.tokens_in, res.tokens_out, now)
        if res.rate_limited:
            self.state.set_cooldown(runner_name, now + COOLDOWN_S)
        return res

    def available(self, names: list[str]) -> list[str]:
        now = self.clock()
        return [n for n in names if n in self.runners and not self.state.in_cooldown(n, now)]

    # step file helpers
    def path(self, name: str) -> Path:
        return self.run_dir / name

    def read_json(self, name: str):
        return json.loads(self.path(name).read_text())

    def write_json(self, name: str, data) -> Path:
        p = self.path(name)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return p
