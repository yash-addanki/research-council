"""Per-run context shared by every step, including the single gate for model calls."""

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from research_council.config import Config
from research_council.notion import Topic
from research_council.tokens import total_tokens
from research_council.runners.base import RunResult, Runner
from research_council.state import State

COOLDOWN_S = 3 * 3600
CHAIRMAN_SHARE = 0.12  # budget kept back for the final write-up, which always runs
OUT_RESERVE = 4000  # expected reply tokens, reserved with the prompt until the call reports real usage


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
    notion: object = None  # NotionClient, set by the pipeline
    notifier: object = None  # has notify(text); set by the pipeline
    _calls: dict[str, int] = field(default_factory=dict)
    _reserved: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

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
        budget = self.cfg.caps.get(f"tokens_{self.depth.lower()}")
        reserve = 0
        if budget and step != "chairman":
            # parallel calls (council, review) all start before any has reported usage, so each one
            # reserves its expected cost here and the check counts what is already in flight
            reserve = len(prompt) // 4 + OUT_RESERVE
            with self._lock:
                spent = total_tokens(self.state.usage_for_run(self.run_id))
                if spent + self._reserved + reserve > budget * (1 - CHAIRMAN_SHARE):
                    return RunResult("", 0, 0, runner_name, error=f"token budget {budget:,} for {self.depth} reached")
                self._reserved += reserve
        self._calls[runner_name] = self._calls.get(runner_name, 0) + 1
        try:
            res = runner.run(prompt, tier, web=web, timeout_s=timeout_s)
            self.state.record_usage(self.run_id, step, runner_name, res.tokens_in, res.tokens_out, now)
        finally:
            with self._lock:
                self._reserved -= reserve
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
