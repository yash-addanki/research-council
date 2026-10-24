"""gemini -p runner (Google AI Pro login). In JSON mode errors arrive on stderr with empty stdout."""

import json

from research_council.runners.base import RunResult
from research_council.runners.cli import CliRunner, looks_rate_limited


class GeminiRunner(CliRunner):
    name = "gemini"

    def build_argv(self, prompt: str, model: str, web: bool) -> list[str]:
        # google_web_search is built in; plan mode keeps it read-only either way
        return ["gemini", "-p", prompt, "--output-format", "json", "-m", model, "--approval-mode", "plan"]

    def parse(self, stdout: str, stderr: str, returncode: int) -> RunResult:
        raw = stdout if (stdout or "").strip() else stderr
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            msg = (raw or "").strip()[:500]
            return RunResult("", 0, 0, "", rate_limited=looks_rate_limited(msg), error=f"gemini: bad output: {msg}")
        models = (data.get("stats") or {}).get("models") or {}
        tin = sum(m.get("tokens", {}).get("input", 0) for m in models.values())
        tout = sum(m.get("tokens", {}).get("candidates", 0) + m.get("tokens", {}).get("thoughts", 0)
                   for m in models.values())
        model = next(iter(models), "")
        if data.get("error"):
            err = data["error"]
            msg = str(err.get("message", ""))
            limited = err.get("code") == 429 or looks_rate_limited(msg)
            return RunResult("", tin, tout, model, rate_limited=limited, error=f"gemini: {msg}")
        return RunResult(data.get("response", ""), tin, tout, model)
