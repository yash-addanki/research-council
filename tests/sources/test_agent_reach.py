import subprocess
from pathlib import Path

from research_council.sources import agent_reach

FIX = Path(__file__).parent.parent / "fixtures" / "sources"


def _run_returning(text, code=0, seen=None):
    def fake(argv, **kw):
        if seen is not None:
            seen.append(argv)
        return subprocess.CompletedProcess(argv, code, text, "")
    return fake


def test_reddit_search_parses_and_skips_items_without_url(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", _run_returning((FIX / "agent_reach_reddit.synthetic.json").read_text(), seen=seen))
    items = agent_reach.search_channel("reddit", "local coding model", 5)
    assert seen[0][:4] == ["agent-reach", "reddit", "search", "local coding model"]
    assert len(items) == 1 and items[0].platform == "reddit"
    assert items[0].published_at == "2026-09-30T12:00:00Z" and "512" in items[0].excerpt


def test_twitter_items_nested_and_alt_keys(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_returning((FIX / "agent_reach_twitter.synthetic.json").read_text()))
    items = agent_reach.search_channel("twitter", "council", 5)
    assert items[0].url == "https://x.com/someone/status/1" and "council of models" in items[0].excerpt


def test_need_setup_returns_empty(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _run_returning((FIX / "agent_reach_needsetup.json").read_text(), code=1))
    assert agent_reach.search_channel("reddit", "x", 5) == []


def test_missing_binary_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(subprocess, "run", boom)
    assert agent_reach.search_channel("youtube", "x", 5) == []


def test_sources_registry_has_social_channels():
    assert set(agent_reach.SOURCES) == {"reddit", "twitter", "youtube"}
