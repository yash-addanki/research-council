"""codex exec runner (ChatGPT login). Parses the --json event stream."""

import json

from research_council.runners.base import RunResult
from research_council.runners.cli import CliRunner, looks_rate_limited

EFFORT = {"cheap": "low", "mid": "medium", "top": "high"}


class CodexRunner(CliRunner):
    name = "codex"

    def build_argv(self, prompt: str, model: str, web: bool) -> list[str]:
        tier = next((t for t, m in self.tiers.items() if m == model), "mid")
        argv = ["codex", "exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral",
                "-m", model, "-c", f'model_reasoning_effort="{EFFORT.get(tier, "medium")}"']
        if web:
            argv += ["-c", 'web_search="live"']
        return argv + [prompt]

    def parse(self, stdout: str, stderr: str, returncode: int) -> RunResult:
        text, tin, tout, failure = "", 0, 0, None
        for line in (stdout or "").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = ev.get("type")
            if kind == "item.completed" and ev.get("item", {}).get("type") == "agent_message":
                text = ev["item"].get("text", "")
            elif kind == "turn.completed":
                u = ev.get("usage", {})
                tin += u.get("input_tokens", 0) - u.get("cached_input_tokens", 0)
                tout += u.get("output_tokens", 0)
            elif kind == "turn.failed":
                failure = ev.get("error", {}).get("message", "turn failed")
        if failure or (returncode != 0 and not text):
            msg = failure or (stderr or "codex failed").strip()[:500]
            return RunResult("", tin, tout, "", rate_limited=looks_rate_limited(msg), error=f"codex: {msg}")
        if not text:
            return RunResult("", tin, tout, "", error="codex: no agent message in output")
        return RunResult(text, tin, tout, "")
