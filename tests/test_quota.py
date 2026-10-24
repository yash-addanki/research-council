import json

from research_council import quota
from research_council.state import State

from .fakes import FakeNotion, topic
from .steps.conftest import EXAMPLE

PROCS_IDLE = ["/sbin/launchd", "/Users/y/.local/bin/claude -p hello --output-format json", "codex exec --json hi"]


def test_busy_when_recent_input():
    assert quota.user_busy(PROCS_IDLE, hid_idle_s=60)


def test_not_busy_for_headless_claude_p():
    assert not quota.user_busy(PROCS_IDLE, hid_idle_s=3600)


def test_busy_when_interactive_claude_running():
    assert quota.user_busy(["/Users/y/.local/bin/claude"], hid_idle_s=3600)
    assert quota.user_busy(["node /usr/local/bin/gemini"], hid_idle_s=3600)
    assert quota.user_busy(["/opt/homebrew/bin/codex resume"], hid_idle_s=3600)


def test_busy_when_antigravity_open():
    assert quota.user_busy(["/Applications/Antigravity.app/Contents/MacOS/Antigravity"], hid_idle_s=3600)
    assert quota.user_busy(["/Applications/Codex.app/Contents/MacOS/Codex"], hid_idle_s=3600)


def test_codex_quota_reads_newest_rollout(tmp_path):
    day = tmp_path / "2026" / "10" / "24"
    day.mkdir(parents=True)
    ev = lambda pct: json.dumps({"type": "event_msg", "payload": {"type": "token_count", "rate_limits": {"primary": {"used_percent": pct}}}})
    (day / "rollout-a.jsonl").write_text(ev(10) + "\n")
    newest = day / "rollout-b.jsonl"
    newest.write_text(ev(40) + "\n" + ev(56) + "\n")
    import os
    os.utime(day / "rollout-a.jsonl", (1, 1))
    assert quota.codex_used_percent(tmp_path) == 56


def test_codex_quota_none_when_no_sessions(tmp_path):
    assert quota.codex_used_percent(tmp_path / "missing") is None


def test_models_available_excludes_cooldown_and_heavy_codex(tmp_path):
    st = State(tmp_path / "s.db")
    st.set_cooldown("gemini", until=5000)
    assert quota.models_available(st, ["claude", "codex", "gemini"], now=1000, cap=50, codex_used=95) == ["claude"]
    assert quota.models_available(st, ["claude", "codex"], now=1000, cap=50, codex_used=40) == ["claude", "codex"]


def test_models_available_excludes_over_cap(tmp_path):
    st = State(tmp_path / "s.db")
    for i in range(3):
        st.record_usage("r", "s", "claude", 1, 1, now=900 + i)
    assert quota.models_available(st, ["claude"], now=1000, cap=3) == []


class Asker:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def ask(self, q, timeout_s=1800):
        self.asked.append(q)
        return self.answer


def _cfg(tmp_path):
    from research_council.config import load_config
    cfg = load_config(EXAMPLE)
    cfg.paths.db = tmp_path / "s.db"
    return cfg


def test_ask_first_no_reply_does_not_run(tmp_path, monkeypatch):
    monkeypatch.setattr(quota, "list_processes", lambda: [])
    monkeypatch.setattr(quota, "hid_idle_seconds", lambda: 3600)
    monkeypatch.setattr(quota, "codex_used_percent", lambda *a: None)
    asker = Asker("timeout")
    assert quota.ask_first(_cfg(tmp_path), FakeNotion([topic()]), asker) is False
    assert "Best local LLM for coding" in asker.asked[0] and "(High)" in asker.asked[0]


def test_ask_first_yes_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(quota, "list_processes", lambda: [])
    monkeypatch.setattr(quota, "hid_idle_seconds", lambda: 3600)
    monkeypatch.setattr(quota, "codex_used_percent", lambda *a: None)
    assert quota.ask_first(_cfg(tmp_path), FakeNotion([topic()]), Asker("yes")) is True


def test_ask_first_busy_never_asks(tmp_path, monkeypatch):
    monkeypatch.setattr(quota, "list_processes", lambda: ["/Users/y/.local/bin/claude"])
    monkeypatch.setattr(quota, "hid_idle_seconds", lambda: 3600)
    asker = Asker("yes")
    assert quota.ask_first(_cfg(tmp_path), FakeNotion([topic()]), asker) is False
    assert asker.asked == []


def test_ask_first_without_notifier_does_not_run(tmp_path, monkeypatch):
    monkeypatch.setattr(quota, "list_processes", lambda: [])
    monkeypatch.setattr(quota, "hid_idle_seconds", lambda: 3600)
    monkeypatch.setattr(quota, "codex_used_percent", lambda *a: None)
    assert quota.ask_first(_cfg(tmp_path), FakeNotion([topic()]), None) is False
