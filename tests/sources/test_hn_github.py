import json
import subprocess
from pathlib import Path

import httpx

from research_council.sources import github, hn

FIX = Path(__file__).parent.parent / "fixtures" / "sources"


def _client(status, body):
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, text=body)))


def test_hn_search_parses_fixture():
    items = hn.search("llm council", 10, client=_client(200, (FIX / "hn.json").read_text()))
    assert len(items) == 2
    assert items[0].url == "https://github.com/karpathy/llm-council"
    assert items[0].platform == "hn"
    # text posts link to the HN discussion
    assert items[1].url == "https://news.ycombinator.com/item?id=41000002"
    assert items[1].published_at == "2026-09-01T10:00:00Z"


def test_hn_search_failure_returns_empty():
    assert hn.search("x", 5, client=_client(500, "boom")) == []


def test_github_search_parses_fixture(monkeypatch):
    out = (FIX / "gh_repos.json").read_text()
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    items = github.search("research agent", 5)
    assert items[0].url == "https://github.com/assafelovic/gpt-researcher"
    assert items[0].platform == "github"
    assert "30278" in items[0].excerpt
    assert items[0].published_at == "2026-10-10T22:03:51Z"


def test_github_search_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "auth"))
    assert github.search("x", 5) == []
