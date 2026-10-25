import subprocess
from pathlib import Path

import pytest

from research_council.runners.claude import ClaudeRunner
from research_council.runners.codex import CodexRunner
from research_council.runners.gemini import GeminiRunner

FIX = Path(__file__).parent.parent / "fixtures" / "cli"
TIERS = {"cheap": "c-model", "mid": "m-model", "top": "t-model"}


def fx(name):
    return (FIX / name).read_text()


# ---- Claude
def test_claude_parse_ok_fixture():
    r = ClaudeRunner(TIERS).parse(fx("claude_ok.json"), "", 0)
    assert r.ok and r.text == "OK"
    assert r.tokens_in == 10 + 5764 and r.tokens_out == 42
    assert r.model == "claude-haiku-4-5-20251001"


def test_claude_parse_web_uses_model_usage_totals():
    r = ClaudeRunner(TIERS).parse(fx("claude_web.json"), "", 0)
    assert r.tokens_in == 10920 + 26525 and r.tokens_out == 645


def test_claude_rate_limit_detected():
    r = ClaudeRunner(TIERS).parse(fx("claude_ratelimit.synthetic.json"), "", 1)
    assert not r.ok and r.rate_limited


def test_claude_parse_garbage_returns_error():
    r = ClaudeRunner(TIERS).parse("<html>", "", 0)
    assert not r.ok and not r.rate_limited


def test_claude_argv_readonly_and_web():
    argv = ClaudeRunner(TIERS).build_argv("hi", "m-model", web=False)
    assert argv[:3] == ["claude", "-p", "hi"] and "--tools" in argv and argv[argv.index("--tools") + 1] == ""
    web = ClaudeRunner(TIERS).build_argv("hi", "m-model", web=True)
    assert web[web.index("--tools") + 1] == "WebSearch,WebFetch"
    assert web[web.index("--allowedTools") + 1] == "WebSearch,WebFetch"
    assert web[web.index("--model") + 1] == "m-model"


def test_claude_argv_skips_user_plugins_hooks_and_mcp():
    # measured on the Mac: default 148,567 input tokens for "OK", lean flags 935
    argv = ClaudeRunner(TIERS).build_argv("hi", "m-model", web=False)
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in argv and "--no-session-persistence" in argv and "--system-prompt" in argv


def test_chrome_runner_keeps_user_settings():
    argv = ClaudeRunner(TIERS, chrome=True).build_argv("hi", "m-model", web=False)
    assert "--chrome" in argv and "--setting-sources" not in argv and "--strict-mcp-config" not in argv


def test_runners_start_outside_any_repo(monkeypatch):
    seen = {}
    def fake_run(argv, **kw):
        seen.update(kw)
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)
    monkeypatch.setattr(subprocess, "run", fake_run)
    ClaudeRunner(TIERS).run("hi", "cheap", timeout_s=1)
    assert seen["cwd"] and not (Path(seen["cwd"]) / "CLAUDE.md").exists()


# ---- Codex
def test_codex_parse_ok_fixture():
    r = CodexRunner(TIERS).parse(fx("codex_ok.jsonl"), "", 0)
    assert r.ok and r.text == "OK"
    assert r.tokens_in == 19721 - 12544 and r.tokens_out == 5


def test_codex_parse_web_takes_last_agent_message():
    r = CodexRunner(TIERS).parse(fx("codex_web.jsonl"), "", 0)
    assert "v2.103.2" in r.text and r.tokens_out == 82


def test_codex_model_error_is_error_not_rate_limit():
    r = CodexRunner(TIERS).parse(fx("codex_model_error.jsonl"), "", 1)
    assert not r.ok and not r.rate_limited and "not supported" in r.error


def test_codex_rate_limit_detected():
    r = CodexRunner(TIERS).parse(fx("codex_ratelimit.synthetic.jsonl"), "", 1)
    assert not r.ok and r.rate_limited


def test_codex_argv_readonly_and_web():
    argv = CodexRunner(TIERS).build_argv("hi", "m-model", web=True)
    assert argv[:2] == ["codex", "exec"] and argv[-1] == "hi"
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert 'web_search="live"' in argv
    assert "--search" not in argv
    assert 'web_search="live"' not in CodexRunner(TIERS).build_argv("hi", "m", web=False)


# ---- Gemini
def test_gemini_parse_agy_ok_fixture():
    r = GeminiRunner(TIERS).parse(fx("agy.ok.json"), "", 0)
    assert r.ok and r.text == "OK" and (r.tokens_in, r.tokens_out) == (9048, 1390)


def test_gemini_empty_reply_with_denied_tool_is_error():
    r = GeminiRunner(TIERS).parse(fx("agy.web.json"), fx("agy.web.stderr"), 0)
    assert not r.ok and "RunCommand" in r.error and r.tokens_in == 29434


def test_gemini_bad_model_is_error_not_rate_limit():
    r = GeminiRunner(TIERS).parse(fx("agy.badmodel.json"), "error: invalid model selection", 1)
    assert not r.ok and "invalid model selection" in r.error and not r.rate_limited


def test_gemini_non_json_output_is_error():
    r = GeminiRunner(TIERS).parse("", "error: quota exhausted for Gemini Models", 1)
    assert not r.ok and r.rate_limited


def test_gemini_argv_uses_agy_plan_mode():
    argv = GeminiRunner(TIERS).build_argv("hi", "m-model", web=True)
    assert argv[:2] == ["agy", "-p"]
    assert argv[argv.index("--mode") + 1] == "plan" and argv[argv.index("--model") + 1] == "m-model"
    assert "--dangerously-skip-permissions" not in argv


def test_gemini_prompt_forbids_tools():
    argv = GeminiRunner(TIERS).build_argv("hi", "m-model", web=False)
    assert argv[2].endswith("hi") and "Do not use any tools" in argv[2]


# ---- shared run() behaviour
@pytest.mark.parametrize("runner", [ClaudeRunner(TIERS), CodexRunner(TIERS), GeminiRunner(TIERS)])
def test_timeout_returns_error(runner, monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)
    monkeypatch.setattr(subprocess, "run", boom)
    r = runner.run("hi", "cheap", timeout_s=1)
    assert not r.ok and "timed out" in r.error


@pytest.mark.parametrize("runner", [ClaudeRunner(TIERS), CodexRunner(TIERS), GeminiRunner(TIERS)])
def test_missing_cli_returns_error(runner, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("nope")
    monkeypatch.setattr(subprocess, "run", boom)
    assert "not installed" in runner.run("hi", "cheap").error


def test_run_passes_devnull_stdin_and_tier_model(monkeypatch):
    seen = {}

    def fake(argv, **kw):
        seen.update(kw, argv=argv)
        return subprocess.CompletedProcess(argv, 0, fx("claude_ok.json"), "")
    monkeypatch.setattr(subprocess, "run", fake)
    ClaudeRunner(TIERS).run("hi", "top")
    assert seen["stdin"] == subprocess.DEVNULL and "t-model" in seen["argv"]


@pytest.mark.parametrize("runner", [ClaudeRunner(TIERS), CodexRunner(TIERS), GeminiRunner(TIERS)])
def test_run_strips_null_bytes_from_prompt(runner, monkeypatch):
    seen = {}

    def fake(argv, **kw):
        seen["argv"] = argv
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)
    monkeypatch.setattr(subprocess, "run", fake)
    runner.run("evidence \x00 from a pdf\x01", "cheap", timeout_s=1)
    assert not any("\x00" in a or "\x01" in a for a in seen["argv"])
