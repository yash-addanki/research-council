"""claude -p runner. Tokens come from .modelUsage (whole run), not .usage (last turn only)."""

import json

from research_council.runners.base import RunResult
from research_council.runners.cli import CliRunner, looks_rate_limited

WEB_TOOLS = "WebSearch,WebFetch"
SYSTEM = "You are a careful research assistant. Follow the requested output format exactly."
# Without these, every call loads the user's plugins, hooks, skills and MCP servers (~145k input tokens).
LEAN = ["--setting-sources", "", "--strict-mcp-config", "--no-session-persistence", "--system-prompt", SYSTEM]


class ClaudeRunner(CliRunner):
    name = "claude"

    def __init__(self, tiers: dict[str, str], chrome: bool = False):
        super().__init__(tiers)
        self.chrome = chrome

    def build_argv(self, prompt: str, model: str, web: bool) -> list[str]:
        tools = WEB_TOOLS if web else ""
        argv = ["claude", "-p", prompt, "--output-format", "json", "--model", model, "--tools", tools]
        if web:
            argv += ["--allowedTools", WEB_TOOLS]
        if self.chrome:  # the Chrome extension connection comes from the user's own setup
            return argv + ["--chrome", "--allowedTools", "mcp__claude-in-chrome__*"]
        return argv + LEAN

    def parse(self, stdout: str, stderr: str, returncode: int) -> RunResult:
        try:
            data = json.loads(stdout)
        except (json.JSONDecodeError, TypeError):
            msg = (stderr or stdout or "").strip()[:500]
            return RunResult("", 0, 0, "", rate_limited=looks_rate_limited(msg), error=f"claude: bad output: {msg}")
        usage = data.get("modelUsage") or {}
        tin = sum(u.get("inputTokens", 0) + u.get("cacheCreationInputTokens", 0) for u in usage.values())
        tout = sum(u.get("outputTokens", 0) for u in usage.values())
        model = next(iter(usage), "")
        if data.get("is_error") or returncode != 0:
            msg = str(data.get("result") or data.get("subtype"))
            limited = data.get("api_error_status") == 429 or looks_rate_limited(msg)
            return RunResult("", tin, tout, model, rate_limited=limited, error=f"claude: {msg}")
        return RunResult(data.get("result", ""), tin, tout, model)
