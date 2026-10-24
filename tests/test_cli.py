from research_council import cli
from research_council.state import State

from .fakes import FakeNotion, topic
from .steps.conftest import EXAMPLE


def test_slugify():
    assert cli.slugify("How can we optimize the Research Council flow?!") == "how-can-we-optimize-the-research-council"


def test_page_id_from_url():
    url = "https://app.notion.com/p/40324ea98c5481748293c686858190d5?pvs=204"
    assert cli.page_id_from(url) == "40324ea9-8c54-8174-8293-c686858190d5"
    assert cli.page_id_from("40324ea9-8c54-8174-8293-c686858190d5") == "40324ea9-8c54-8174-8293-c686858190d5"


def test_cli_next_exits_when_no_lease(tmp_path, monkeypatch, capsys):
    from research_council.config import load_config
    cfg = load_config(EXAMPLE)
    cfg.paths.runs_dir, cfg.paths.db = tmp_path / "runs", tmp_path / "s.db"
    State(cfg.paths.db).acquire_lease("p1", now=__import__("time").time())  # another run holds it
    started = []
    monkeypatch.setattr(cli, "run_pipeline", lambda *a, **k: started.append(1))
    code = cli.start_run(cfg, FakeNotion([topic()]), topic(), dry_run=True, notifier=None)
    assert code == 0 and started == []
    assert "already running" in capsys.readouterr().out


def test_cli_next_with_empty_queue(tmp_path, capsys):
    from research_council.config import load_config
    cfg = load_config(EXAMPLE)
    cfg.paths.runs_dir, cfg.paths.db = tmp_path / "runs", tmp_path / "s.db"
    assert cli.cmd_next(cfg, FakeNotion([]), dry_run=True, notifier=None) == 0
    assert "No topics" in capsys.readouterr().out


def test_make_runners_includes_chrome_runner():
    from research_council.config import load_config
    from .steps.conftest import EXAMPLE
    runners = cli.make_runners(load_config(EXAMPLE))
    assert set(runners) == {"claude", "codex", "gemini", "chrome"} and runners["chrome"].chrome
