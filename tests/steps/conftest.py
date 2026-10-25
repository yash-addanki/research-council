import json
from pathlib import Path

import pytest

from research_council.config import load_config
from research_council.notion import Topic
from research_council.runners.base import FakeRunner, RunResult
from research_council.state import State
from research_council.steps.context import RunContext

EXAMPLE = Path(__file__).parent.parent.parent / "config.example.toml"


def ok(text, tin=10, tout=5):
    return RunResult(text if isinstance(text, str) else json.dumps(text), tin, tout, "m")


@pytest.fixture
def make_ctx(tmp_path):
    def _make(runners=None, depth="High", title="Best local LLM for coding", notes="", kind="build"):
        ctx = RunContext(
            run_id="r1", run_dir=tmp_path / "run", topic=Topic("p1", title, notes, depth, ["Tech"], depth),
            depth=depth, runners=runners or {}, state=State(tmp_path / "s.db"), cfg=load_config(EXAMPLE),
            dry_run=True, clock=lambda: 1000.0,
        )
        ctx.run_dir.mkdir(parents=True, exist_ok=True)
        return ctx
    return _make


BRIEF = {"question": "Which local LLM is best for coding?", "reading_chosen": "", "success_criteria": ["x"],
         "kind": "build", "angles": ["a1", "a2"], "social_queries": ["s1"], "repo_queries": ["r1"]}


def answer(claims, conclusion="Use X", repos=None):
    return {"conclusion": conclusion, "claims": claims, "repos": repos or [], "open_questions": []}


@pytest.fixture(autouse=True)
def _no_network_fetch(monkeypatch):
    from research_council.steps import scout
    monkeypatch.setattr(scout, "fetch_text", lambda url, **k: None)
