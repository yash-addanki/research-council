import json
import os

from research_council import cli
from research_council.conductor import STEPS
from research_council.dashboard import snapshot
from research_council.state import State


def make_run(runs, run_id, files, title="T", page_id="p1", started=1000.0):
    d = runs / run_id
    d.mkdir(parents=True)
    (d / "topic.json").write_text(json.dumps({"page_id": page_id, "title": title, "notes": "", "priority": "High",
                                              "tags": ["ai"], "depth": "Low"}))
    os.utime(d / "topic.json", (started, started))
    for name, body in files.items():
        (d / name).write_text(body)
        os.utime(d / name, (started + 60, started + 60))
    return d


def test_snapshot_reports_stages_tokens_and_quota(tmp_path):
    runs, db = tmp_path / "runs", tmp_path / "s.db"
    state = State(db)
    make_run(runs, "r1", {"brief.json": "{}", "evidence.jsonl": '{"a":1}\n{"b":2}\n',
                          "answer.claude.json": "{}",
                          "citations.json": json.dumps([{"label": "supported"}, {"label": "supported"},
                                                        {"label": "unreachable"}])})
    state.record_usage("r1", "council", "claude", 100, 20, now=1050)
    state.record_usage("r1", "council", "codex", 50, 5, now=1050)
    state.record_usage("r1", "citations", "claude", 10, 1, now=1060)
    state.acquire_lease("p1", now=1070)

    snap = snapshot(runs, db, now=1100, codex_used=lambda: 42.0)
    r = snap["runs"][0]
    assert r["status"] == "running" and r["current_step"] == "deep_submit"
    assert r["steps_done"] == 3 and r["steps_total"] == len(STEPS)
    assert r["evidence_items"] == 2 and r["citations"] == {"supported": 2, "unreachable": 1}
    assert r["answers"] == ["claude"] and r["duration_s"] == 60
    assert r["tokens"]["total"] == 186
    assert r["tokens"]["by_model"]["claude"] == {"calls": 2, "tokens_in": 110, "tokens_out": 21}
    assert r["tokens"]["by_step"] == {"council": 175, "citations": 11}
    assert snap["quota"]["claude"]["calls_5h"] == 2 and snap["quota"]["codex"]["used_percent"] == 42.0
    assert snap["totals"] == {"runs": 1, "done": 0, "running": 1, "blocked": 0, "tokens": 186}


def test_snapshot_status_done_blocked_stopped(tmp_path):
    from research_council.conductor import OUTPUTS
    runs, db = tmp_path / "runs", tmp_path / "s.db"
    make_run(runs, "done", {OUTPUTS[s]: "{}" for s in STEPS}, page_id="a", started=3000)
    make_run(runs, "blk", {"blocked.json": json.dumps({"step": "brief", "reason": "x", "at": 1})},
             page_id="b", started=2000)
    make_run(runs, "stop", {}, page_id="c", started=1000)
    snap = snapshot(runs, db, now=5000, codex_used=lambda: None)
    assert [(r["run_id"], r["status"]) for r in snap["runs"]] == [("done", "done"), ("blk", "blocked"),
                                                                   ("stop", "stopped")]
    assert snap["runs"][1]["blocked"]["step"] == "brief"


def test_cli_dashboard_prints_json(tmp_path, monkeypatch, capsys):
    from research_council.config import load_config
    from .steps.conftest import EXAMPLE
    cfg = load_config(EXAMPLE)
    cfg.paths.runs_dir, cfg.paths.db = tmp_path / "runs", tmp_path / "s.db"
    monkeypatch.setattr(cli, "load_config", lambda _: cfg)
    monkeypatch.setattr("research_council.quota.codex_used_percent", lambda: None)
    assert cli.main(["dashboard"]) == 0
    assert json.loads(capsys.readouterr().out)["totals"]["runs"] == 0
