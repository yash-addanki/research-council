import json
from datetime import datetime, timezone

from research_council import tools

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
TOOL = tools.Tool("thing", "acme/thing", check=["thing", "--version"], install=["brew", "install", "thing"])


def shell(present=False, pushed="2026-09-01T00:00:00Z", install_code=0):
    calls = []

    def sh(argv):
        calls.append(argv)
        if argv[0] == "gh":
            return 0, json.dumps({"stars": 42, "pushed_at": pushed, "archived": False})
        if argv == TOOL.check:
            return (0 if present else 127), ""
        return install_code, ""
    return sh, calls


def test_present_tool_is_left_alone():
    sh, calls = shell(present=True)
    assert tools.ensure(TOOL, ["acme/thing"], ask=None, sh=sh, now=NOW) == "present"
    assert calls == [TOOL.check]


def test_allowlisted_tool_installs_without_asking():
    sh, calls = shell()
    assert tools.ensure(TOOL, ["acme/thing"], ask=lambda q: 1 / 0, sh=sh, now=NOW) == "installed"
    assert TOOL.install in calls


def test_stale_repo_is_not_installed():
    sh, calls = shell(pushed="2025-01-01T00:00:00Z")
    assert tools.ensure(TOOL, ["acme/thing"], ask=None, sh=sh, now=NOW) == "stale"
    assert TOOL.install not in calls


def test_new_tool_asks_and_skips_on_no():
    sh, calls = shell()
    asked = []
    assert tools.ensure(TOOL, [], ask=lambda q: (asked.append(q), "no")[-1], sh=sh, now=NOW) == "skipped"
    assert "acme/thing" in asked[0] and "42" in asked[0] and TOOL.install not in calls


def test_new_tool_installs_on_yes_and_joins_allowlist():
    sh, _ = shell()
    allow = []
    assert tools.ensure(TOOL, allow, ask=lambda q: "yes", sh=sh, now=NOW) == "installed"
    assert allow == ["acme/thing"]


def test_new_tool_without_approval_channel_is_skipped():
    sh, _ = shell()
    assert tools.ensure(TOOL, [], ask=None, sh=sh, now=NOW) == "skipped"


def test_failed_install_reported():
    sh, _ = shell(install_code=1)
    assert tools.ensure(TOOL, ["acme/thing"], ask=None, sh=sh, now=NOW) == "failed"


def test_save_allowlist_rewrites_only_that_line(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('allowlist = ["a/b"]\n\n[paths]\ngitrepos = "~/GitRepos"\n')
    tools.save_allowlist(p, ["a/b", "c/d"])
    assert p.read_text() == 'allowlist = ["a/b", "c/d"]\n\n[paths]\ngitrepos = "~/GitRepos"\n'


def test_cli_install_asks_for_new_tool(tmp_path, monkeypatch):
    from research_council import cli
    from .steps.conftest import EXAMPLE
    cfg = tmp_path / "config.toml"
    cfg.write_text(EXAMPLE.read_text())
    seen = {}
    monkeypatch.setattr(tools, "setup", lambda path, allow, ask, tools=None: seen.update(path=path, tools=tools) or {"x": "skipped"})
    monkeypatch.setattr(cli, "_notifier", lambda: None)
    assert cli.main(["--config", str(cfg), "install", "x", "acme/x", "--check", "x --version", "--", "brew", "install", "x"]) == 0
    t = seen["tools"][0]
    assert (t.repo, t.check, t.install) == ("acme/x", ["sh", "-c", "x --version"], ["brew", "install", "x"])
