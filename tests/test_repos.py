import json
from datetime import datetime, timedelta, timezone

from research_council import repos
from research_council.repos import RepoCandidate, act_on, filter_and_rank
from research_council.steps import act

from .steps.conftest import BRIEF

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def cand(name, days_old, relevance=0.8, stars=100):
    return RepoCandidate(name, f"https://github.com/{name}", stars, NOW - timedelta(days=days_old), "d", relevance)


def test_filter_drops_older_than_365_days():
    out = filter_and_rank([cand("a/old", 400), cand("a/new", 30)], NOW)
    assert [c.full_name for c in out] == ["a/new"]


def test_filter_drops_low_relevance():
    assert filter_and_rank([cand("a/x", 10, relevance=0.5)], NOW) == []


def test_filter_prefers_recent_over_stars():
    out = filter_and_rank([cand("a/popular-stale", 300, stars=90000), cand("a/fresh", 20, stars=50)], NOW)
    assert [c.full_name for c in out] == ["a/fresh", "a/popular-stale"]


def test_filter_top_n():
    assert len(filter_and_rank([cand(f"a/{i}", 10) for i in range(6)], NOW, top_n=3)) == 3


class Shell:
    def __init__(self, existing_forks=()):
        self.cmds = []
        self.existing_forks = set(existing_forks)

    def __call__(self, argv):
        self.cmds.append(argv)
        if argv[:3] == ["gh", "api", "user"]:
            return 0, "yash-addanki"
        if argv[:3] == ["gh", "repo", "view"]:
            return (0, "{}") if argv[3] in self.existing_forks else (1, "")
        return 0, ""


def test_act_stars_forks_and_clones(tmp_path):
    sh = Shell()
    paths = act_on([cand("org/tool", 10)], tmp_path, dry_run=False, sh=sh, report_note="see Notion")
    assert ["gh", "api", "-X", "PUT", "user/starred/org/tool"] in sh.cmds
    assert ["gh", "repo", "fork", "org/tool", "--clone=false"] in sh.cmds
    clone = next(c for c in sh.cmds if c[:2] == ["git", "clone"])
    assert clone[2] == "https://github.com/yash-addanki/tool.git" and clone[3] == str(tmp_path / "tool")
    assert paths == [tmp_path / "tool"]


def test_act_skips_existing_fork_and_folder(tmp_path):
    (tmp_path / "tool").mkdir()
    sh = Shell(existing_forks={"yash-addanki/tool"})
    act_on([cand("org/tool", 10)], tmp_path, dry_run=False, sh=sh, report_note="")
    assert not any(c[:3] == ["gh", "repo", "fork"] for c in sh.cmds)
    assert not any(c[:2] == ["git", "clone"] for c in sh.cmds)


def test_kickoff_written_to_first_clone(tmp_path):
    def sh(argv):
        if argv[:2] == ["git", "clone"]:
            (tmp_path / "tool").mkdir()
        return Shell()(argv)
    act_on([cand("org/tool", 10)], tmp_path, dry_run=False, sh=sh, report_note="Report: X")
    assert "Report: X" in (tmp_path / "tool" / "KICKOFF.md").read_text()


def test_dry_run_runs_no_gh_commands(tmp_path):
    sh = Shell()
    act_on([cand("org/tool", 10)], tmp_path, dry_run=True, sh=sh, report_note="")
    assert sh.cmds == []


def test_knowledge_topic_skips_act(make_ctx):
    ctx = make_ctx()
    ctx.write_json("brief.json", {**BRIEF, "kind": "knowledge"})
    assert ctx.read_json(act.run(ctx).name)["skipped"] is True


def test_act_step_asks_ready_to_build(make_ctx, monkeypatch):
    ctx = make_ctx()
    ctx.dry_run = False
    ctx.write_json("brief.json", BRIEF)
    ctx.write_json("repos.json", [{"full_name": "org/tool", "why": "w", "relevance": 0.9, "votes": 2}])
    monkeypatch.setattr(repos, "fetch_meta", lambda name, sh=None: {"stars": 10, "pushed_at": "2026-10-01T00:00:00Z",
                                                                     "description": "d", "url": "https://github.com/org/tool"})
    monkeypatch.setattr(act, "act_on", lambda cands, root, dry_run, report_note: [root / "tool"])

    class Asker:
        asked = []
        def ask(self, q, timeout_s=1800):
            self.asked.append(q)
            return "yes"
        def notify(self, t): pass
    ctx.notifier = Asker()
    data = ctx.read_json(act.run(ctx).name)
    assert data["ready_to_build"] == "yes" and data["repos"] == ["org/tool"]
    assert "org/tool" in Asker.asked[0]
