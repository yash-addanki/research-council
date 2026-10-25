import json

import pytest

from research_council import conductor
from research_council.runners.base import FakeRunner, RunResult
from research_council.state import State
from research_council.steps.context import RunContext
from research_council.config import load_config

from .fakes import FakeNotifier, FakeNotion, topic
from .steps.conftest import EXAMPLE


def make(tmp_path, steps, dry_run=False):
    ctx = RunContext("r1", tmp_path / "run", topic(), "High", {}, State(tmp_path / "s.db"), load_config(EXAMPLE),
                     dry_run=dry_run, clock=lambda: 1000.0)
    ctx.run_dir.mkdir()
    notion, notifier = FakeNotion([ctx.topic]), FakeNotifier()
    version = ctx.state.acquire_lease("p1", now=1000)
    pipe = conductor.Pipeline(ctx, notion, notifier, lease_version=version, steps=steps)
    return ctx, notion, notifier, pipe


def writer(name, calls, content="{}"):
    def step(ctx):
        calls.append(name)
        p = ctx.path(conductor.OUTPUTS[name])
        p.write_text(content)
        return p
    return step


def all_steps(calls, **override):
    steps = {n: writer(n, calls) for n in conductor.STEPS}
    steps["council"] = lambda ctx: (calls.append("council"), ctx.write_json("answer.claude.json", {"claims": []}),
                                    ctx.write_json("missing.json", {}))[-1]
    steps.update(override)
    return steps


def test_resume_skips_completed_steps(tmp_path):
    calls = []
    ctx, notion, _, pipe = make(tmp_path, all_steps(calls))
    ctx.write_json("brief.json", {"question": "q"})
    pipe.run()
    assert "brief" not in calls and calls[0] == "scout"


def test_steps_run_in_order(tmp_path):
    calls = []
    _, _, _, pipe = make(tmp_path, all_steps(calls))
    pipe.run()
    assert calls == conductor.STEPS


def test_all_members_failed_blocks_before_chairman(tmp_path):
    calls = []
    steps = all_steps(calls, council=lambda ctx: (calls.append("council"), ctx.write_json("missing.json", {"claude": "x", "codex": "y", "gemini": "z"}))[-1])
    _, notion, notifier, pipe = make(tmp_path, steps)
    with pytest.raises(conductor.Blocked):
        pipe.run()
    assert "chairman" not in calls
    assert ("status", "p1", "Blocked") in notion.calls
    assert notifier.sent and "Blocked" in notifier.sent[0]


def test_step_failing_twice_blocks(tmp_path):
    calls = []

    def flaky(ctx):
        calls.append("scout")
        raise RuntimeError("network down")
    _, notion, _, pipe = make(tmp_path, all_steps(calls, scout=flaky))
    with pytest.raises(conductor.Blocked, match="scout"):
        pipe.run()
    assert calls.count("scout") == 2
    notes = [c for c in notion.calls if c[0] == "props"][-1][2]["notes"]
    assert "Blocked at scout: network down" in notes


def test_step_failing_once_recovers(tmp_path):
    calls, state = [], {"n": 0}

    def once(ctx):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("blip")
        return writer("scout", calls)(ctx)
    _, _, _, pipe = make(tmp_path, all_steps(calls, scout=once))
    pipe.run()
    assert "chairman" in calls


def test_dry_run_makes_no_notion_writes(tmp_path):
    calls = []
    _, notion, notifier, pipe = make(tmp_path, all_steps(calls, report=conductor.report_step), dry_run=True)
    pipe.ctx.path("report.md").write_text("## Answer\nx\n")
    pipe.run()
    assert notion.calls == [] and notifier.sent == []


def test_report_step_writes_report_tokens_and_resolves(tmp_path):
    calls = []
    ctx, notion, notifier, pipe = make(tmp_path, all_steps(calls, report=conductor.report_step))
    ctx.state.record_usage("r1", "council", "claude", 100, 20, now=1000)
    ctx.path("report.md").write_text("## Answer\nUse X\n")
    pipe.run()
    appended = next(c for c in notion.calls if c[0] == "append")[2]
    assert "Use X" in appended and "## Tokens used" in appended and "| claude |" in appended
    props = next(c for c in notion.calls if c[0] == "props")[2]
    assert props["tokens_used"] == 120 and props["run_id"] == "r1"
    assert ("status", "p1", "Resolved") in notion.calls
    assert "120 tokens" in notifier.sent[-1] and "Use X" in notifier.sent[-1]


def test_lease_lost_stops_run(tmp_path):
    calls = []
    ctx, _, _, pipe = make(tmp_path, all_steps(calls))
    ctx.state.release("p1", pipe.lease_version)
    ctx.state.acquire_lease("p1", now=1000)  # someone else took it
    with pytest.raises(conductor.LeaseLost):
        pipe.run()
    assert calls == []


def test_heartbeat_keeps_lease_alive_during_long_step(tmp_path, monkeypatch):
    import time
    monkeypatch.setattr(conductor, "HEARTBEAT_S", 0.01)
    calls, beats = [], []
    slow = writer("brief", calls)
    ctx, _, _, pipe = make(tmp_path, all_steps(calls, brief=lambda c: (time.sleep(0.15), slow(c))[-1]))
    real = ctx.state.heartbeat
    monkeypatch.setattr(ctx.state, "heartbeat", lambda *a, **k: (beats.append(1), real(*a, **k))[-1])
    pipe.run()
    assert len(beats) > len(conductor.STEPS) + 3


def test_deep_submit_uses_chrome_step():
    from research_council.runners import chrome_deep
    assert conductor.DEFAULT_STEPS["deep_submit"] is chrome_deep.submit


def test_block_writes_blocked_file_and_resume_clears_it(tmp_path):
    calls = []

    def broken(ctx):
        raise RuntimeError("network down")
    ctx, _, _, pipe = make(tmp_path, all_steps(calls, scout=broken))
    with pytest.raises(conductor.Blocked):
        pipe.run()
    assert json.loads(ctx.path("blocked.json").read_text())["step"] == "scout"
    (tmp_path / "again").mkdir()
    ctx2, _, _, pipe2 = make(tmp_path / "again", all_steps(calls))
    ctx2.write_json("blocked.json", {"step": "scout"})
    pipe2.run()
    assert not ctx2.path("blocked.json").exists()
