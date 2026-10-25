import json

from research_council.runners import chrome_deep
from research_council.runners.base import FakeRunner
from research_council.runners.claude import ClaudeRunner

from ..steps.conftest import BRIEF, ok


class Asker:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def ask(self, q, timeout_s=1800):
        self.asked.append(q)
        return self.answer


def _ctx(make_ctx, depth="High", answer="yes", replies=()):
    fake = FakeRunner("chrome", [ok(r) for r in replies])
    ctx = make_ctx({"chrome": fake}, depth=depth)
    ctx.dry_run = False
    ctx.notifier = Asker(answer)
    ctx.write_json("brief.json", BRIEF)
    return ctx, fake


def test_submit_skipped_below_high(make_ctx):
    ctx, fake = _ctx(make_ctx, depth="Medium")
    assert ctx.read_json(chrome_deep.submit(ctx).name)["skipped"] is True
    assert fake.calls == [] and ctx.notifier.asked == []


def test_submit_skipped_on_no(make_ctx):
    ctx, fake = _ctx(make_ctx, answer="no")
    data = ctx.read_json(chrome_deep.submit(ctx).name)
    assert data["skipped"] is True and fake.calls == []
    assert "Deep Research" in ctx.notifier.asked[0]


def test_submit_records_tabs(make_ctx):
    tabs = {"gemini_app": "https://gemini.google.com/app/1", "chatgpt_app": "https://chatgpt.com/c/2", "muse_app": "blocked: login"}
    ctx, fake = _ctx(make_ctx, replies=[tabs])
    data = ctx.read_json(chrome_deep.submit(ctx).name)
    assert data["tabs"] == tabs and data["submitted_at"] == 1000.0
    assert BRIEF["question"] in fake.calls[0][0]


def test_collect_blocked_app_goes_to_missing(make_ctx, monkeypatch):
    ctx, fake = _ctx(make_ctx, replies=[{"gemini_app": "Gemini report text", "chatgpt_app": "unfinished: still running"}])
    ctx.write_json("deep_submit.json", {"skipped": False, "submitted_at": 0, "tabs": {
        "gemini_app": "https://g", "chatgpt_app": "https://c", "muse_app": "blocked: login"}})
    slept = []
    monkeypatch.setattr(chrome_deep, "SLEEP", slept.append)
    paths = chrome_deep.collect(ctx)
    assert [p.name for p in paths] == ["deep.gemini_app.md"]
    assert ctx.path("deep.gemini_app.md").read_text() == "Gemini report text"
    missing = ctx.read_json("deep_missing.json")
    assert set(missing) == {"chatgpt_app", "muse_app"}


def test_collect_waits_until_30_minutes_after_submit(make_ctx, monkeypatch):
    ctx, _ = _ctx(make_ctx, replies=[{}])
    ctx.write_json("deep_submit.json", {"skipped": False, "submitted_at": 900.0, "tabs": {"gemini_app": "https://g"}})
    slept = []
    monkeypatch.setattr(chrome_deep, "SLEEP", slept.append)
    chrome_deep.collect(ctx)
    assert slept == [900.0 + 1800 - 1000.0]


def test_collect_noop_when_not_submitted(make_ctx):
    ctx, fake = _ctx(make_ctx)
    assert chrome_deep.collect(ctx) == [] and fake.calls == []


def test_argv_includes_chrome_flag():
    argv = ClaudeRunner({"mid": "sonnet"}, chrome=True).build_argv("p", "sonnet", web=False)
    assert "--chrome" in argv
    assert argv[argv.index("--allowedTools") + 1] == "mcp__claude-in-chrome__*"
