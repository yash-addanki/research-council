"""Shared subprocess handling for the model CLIs."""

import subprocess
import tempfile

from research_council.runners.base import RunResult
from research_council.sources.crawl import clean_text

LIMIT_MARKERS = ("429", "rate limit", "rate_limit", "usage limit", "usage_limit", "resource_exhausted", "quota")


def looks_rate_limited(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in LIMIT_MARKERS)


class CliRunner:
    """Subclasses supply build_argv() and parse(); run() is the same for every CLI."""
    name = "cli"

    def __init__(self, tiers: dict[str, str]):
        self.tiers = tiers

    def build_argv(self, prompt: str, model: str, web: bool) -> list[str]:
        raise NotImplementedError

    def parse(self, stdout: str, stderr: str, returncode: int) -> RunResult:
        raise NotImplementedError

    def run(self, prompt: str, tier: str, *, web: bool = False, timeout_s: int = 900) -> RunResult:
        model = self.tiers[tier]
        try:
            # run outside the repo so no CLAUDE.md / AGENTS.md / GEMINI.md gets pulled into the prompt
            proc = subprocess.run(self.build_argv(clean_text(prompt), model, web), capture_output=True, text=True,
                                  timeout=timeout_s, stdin=subprocess.DEVNULL, cwd=tempfile.gettempdir())
        except subprocess.TimeoutExpired:
            return RunResult("", 0, 0, model, error=f"{self.name}: timed out after {timeout_s}s")
        except FileNotFoundError:
            return RunResult("", 0, 0, model, error=f"{self.name}: CLI not installed")
        res = self.parse(proc.stdout, proc.stderr, proc.returncode)
        res.model = res.model or model  # agy's JSON doesn't name the model
        return res
