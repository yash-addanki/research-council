"""Pick active, relevant repos and star / fork / clone them into ~/GitRepos."""

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

Shell = Callable[[list[str]], tuple[int, str]]


def run_shell(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    return proc.returncode, proc.stdout.strip()


@dataclass
class RepoCandidate:
    full_name: str
    url: str
    stars: int
    pushed_at: datetime
    description: str
    relevance: float


def fetch_meta(full_name: str, sh: Shell = run_shell) -> dict | None:
    code, out = sh(["gh", "api", f"repos/{full_name}", "--jq",
                    "{stars: .stargazers_count, pushed_at: .pushed_at, description: .description, url: .html_url, archived: .archived}"])
    if code != 0:
        return None
    meta = json.loads(out)
    return None if meta.get("archived") else meta


def filter_and_rank(cands: list[RepoCandidate], now: datetime, max_age_days: int = 365, prefer_days: int = 180,
                    top_n: int = 3, min_relevance: float = 0.6) -> list[RepoCandidate]:
    keep = [c for c in cands if (now - c.pushed_at).days <= max_age_days and c.relevance >= min_relevance]
    keep.sort(key=lambda c: ((now - c.pushed_at).days <= prefer_days, c.relevance, c.stars), reverse=True)
    return keep[:top_n]


def act_on(cands: list[RepoCandidate], gitrepos: Path, dry_run: bool, sh: Shell = run_shell,
           report_note: str = "") -> list[Path]:
    if dry_run:
        for c in cands:
            print(f"[dry-run] would star, fork and clone {c.full_name}")
        return []
    login = sh(["gh", "api", "user", "--jq", ".login"])[1]
    paths = []
    for c in cands:
        name = c.full_name.split("/")[1]
        sh(["gh", "api", "-X", "PUT", f"user/starred/{c.full_name}"])
        if sh(["gh", "repo", "view", f"{login}/{name}", "--json", "name"])[0] != 0:
            sh(["gh", "repo", "fork", c.full_name, "--clone=false"])
        dest = gitrepos / name
        if not dest.exists():
            sh(["git", "clone", f"https://github.com/{login}/{name}.git", str(dest)])
            sh(["git", "-C", str(dest), "remote", "add", "upstream", f"https://github.com/{c.full_name}.git"])
        paths.append(dest)
    if paths and paths[0].exists():
        kickoff = paths[0] / "KICKOFF.md"
        if not kickoff.exists():
            others = ", ".join(c.full_name for c in cands[1:]) or "none"
            kickoff.write_text(f"# Kickoff\n\nChosen by the research council.\n\n{report_note}\n\nRelated repos cloned: {others}\n")
    return paths
