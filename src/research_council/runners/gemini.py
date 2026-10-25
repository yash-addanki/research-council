"""Gemini council member via the Antigravity CLI (`agy -p`). Google retired Gemini CLI sign-in for AI Pro accounts.

Plan mode keeps it read-only; headless mode auto-denies tools needing permission, so it has no live web search
and answers from the evidence pack. Errors come as status ERROR with an `error` field, and a denied tool can
yield SUCCESS with an empty response, so both count as failures.
"""

import json

from research_council.runners.base import RunResult
from research_council.runners.cli import CliRunner, looks_rate_limited


class GeminiRunner(CliRunner):
    name = "gemini"

    def build_argv(self, prompt: str, model: str, web: bool) -> list[str]:
        return ["agy", "-p", prompt, "--output-format", "json", "--model", model, "--mode", "plan"]

    def parse(self, stdout: str, stderr: str, returncode: int) -> RunResult:
        try:
            data = json.loads(stdout)
        except (json.JSONDecodeError, TypeError):
            msg = ((stdout or "") + (stderr or "")).strip()[:500]
            return RunResult("", 0, 0, "", rate_limited=looks_rate_limited(msg), error=f"gemini: bad output: {msg}")
        usage = data.get("usage") or {}
        tin, tout = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        text = (data.get("response") or "").strip()
        if data.get("status") != "SUCCESS" or not text:
            denied = ", ".join(a.get("display_name", "") for a in data.get("denied_actions") or [])
            msg = data.get("error") or (f"empty reply; denied tools: {denied}" if denied else "empty reply")
            return RunResult("", tin, tout, "", rate_limited=looks_rate_limited(msg), error=f"gemini: {msg}"[:500])
        return RunResult(text, tin, tout, "")
