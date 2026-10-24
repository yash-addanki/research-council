"""Install the research toolchain: allowlisted repos install quietly, anything new needs a WhatsApp yes."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from research_council.repos import Shell, fetch_meta, run_shell

MAX_AGE_DAYS = 365
HOME = str(Path.home())


@dataclass
class Tool:
    name: str
    repo: str  # owner/name on GitHub, checked for recent activity before installing
    check: list[str]
    install: list[str]


def _sh(cmd: str) -> list[str]:
    return ["sh", "-c", cmd]


TOOLS = [
    Tool("uv", "astral-sh/uv", ["uv", "--version"], ["brew", "install", "uv"]),
    Tool("gh", "cli/cli", ["gh", "--version"], ["brew", "install", "gh"]),
    Tool("codex", "openai/codex", ["codex", "--version"], ["npm", "install", "-g", "@openai/codex"]),
    Tool("gemini", "google-gemini/gemini-cli", ["gemini", "--version"], ["npm", "install", "-g", "@google/gemini-cli"]),
    Tool("crawl4ai", "unclecode/crawl4ai", ["uv", "run", "python", "-c", "import crawl4ai"],
         _sh("uv sync --extra crawl && uv run crawl4ai-setup")),
    Tool("agent-reach", "Panniantong/Agent-Reach", ["agent-reach", "--version"],
         ["uv", "tool", "install", f"{HOME}/GitRepos/Agent-Reach"]),
    Tool("karpathy-skills", "multica-ai/andrej-karpathy-skills", ["test", "-d", f"{HOME}/GitRepos/andrej-karpathy-skills"],
         ["git", "clone", "https://github.com/multica-ai/andrej-karpathy-skills", f"{HOME}/GitRepos/andrej-karpathy-skills"]),
    Tool("find-skills", "vercel-labs/skills", _sh("ls ~/.claude/skills ~/.agents/skills 2>/dev/null | grep -qx find-skills"),
         ["npx", "-y", "skills", "add", "vercel-labs/skills", "--skill", "find-skills", "-g", "-y", "-a", "claude-code"]),
    Tool("supabase-skill", "supabase/agent-skills", _sh("ls ~/.claude/skills ~/.agents/skills 2>/dev/null | grep -qx supabase"),
         ["npx", "-y", "skills", "add", "supabase/agent-skills", "--skill", "supabase", "-g", "-y", "-a", "claude-code"]),
]


def ensure(tool: Tool, allowlist: list[str], ask: Callable[[str], str] | None, sh: Shell = run_shell,
           now: datetime | None = None) -> str:
    """Return present | installed | stale | skipped | failed. Appends to allowlist when Yash approves a new tool."""
    if sh(tool.check)[0] == 0:
        return "present"
    meta = fetch_meta(tool.repo, sh)
    if not meta:
        return "skipped"
    pushed = datetime.fromisoformat(meta["pushed_at"].replace("Z", "+00:00"))
    if ((now or datetime.now(timezone.utc)) - pushed).days > MAX_AGE_DAYS:
        return "stale"
    if tool.repo not in allowlist:
        question = f"Install {tool.name} ({tool.repo}, {meta['stars']}★, last commit {pushed.date()})?"
        if ask is None or ask(question) != "yes":
            return "skipped"
        allowlist.append(tool.repo)
    return "installed" if sh(tool.install)[0] == 0 else "failed"


def save_allowlist(config_path: Path, allowlist: list[str]) -> None:
    line = "allowlist = [" + ", ".join(f'"{r}"' for r in allowlist) + "]"
    text = config_path.read_text()
    config_path.write_text(re.sub(r"^allowlist = \[.*\]$", line, text, count=1, flags=re.M))


def setup(config_path: Path, allowlist: list[str], ask, sh: Shell = run_shell, tools: list[Tool] = TOOLS) -> dict:
    before = list(allowlist)
    results = {t.name: ensure(t, allowlist, ask, sh) for t in tools}
    if allowlist != before:
        save_allowlist(config_path, allowlist)
    return results
