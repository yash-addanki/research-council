"""GitHub repository search through the gh CLI."""

import json
import logging
import subprocess

from research_council.evidence import EvidenceItem, now_iso

log = logging.getLogger(__name__)
FIELDS = "fullName,stargazersCount,pushedAt,description,url"


def search(query: str, limit: int) -> list[EvidenceItem]:
    proc = subprocess.run(
        ["gh", "search", "repos", query, "--json", FIELDS, "--limit", str(limit), "--sort", "stars"],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        log.warning("gh search failed: %s", proc.stderr.strip())
        return []
    try:
        repos = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    return [
        EvidenceItem(
            url=r["url"], title=r["fullName"], platform="github",
            excerpt=f"{r['stargazersCount']} stars, last push {r['pushedAt']}. {r.get('description') or ''}".strip(),
            published_at=r["pushedAt"], fetched_at=now_iso(),
        )
        for r in repos
    ]
