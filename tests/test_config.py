import pytest
from pathlib import Path

from research_council.config import load_config

EXAMPLE = Path(__file__).parent.parent / "config.example.toml"


def test_load_config_reads_tiers():
    cfg = load_config(EXAMPLE)
    assert cfg.tiers["claude"]["top"] == "opus"
    assert cfg.tiers["gemini"]["cheap"] == "gemini-2.5-flash"


def test_load_config_reads_caps_and_paths():
    cfg = load_config(EXAMPLE)
    assert cfg.caps["evidence_high"] == 60
    assert cfg.notion_data_source_id == "584e4526-ff39-4614-96d7-f1c0e2b051dd"
    assert cfg.paths.gitrepos == Path("~/GitRepos").expanduser()
    assert "mvanhorn/last30days-skill" in cfg.allowlist


def test_missing_secret_raises(monkeypatch):
    import subprocess

    from research_council import secrets

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 44, "", "not found"))
    with pytest.raises(secrets.MissingSecret):
        secrets.get_secret("wa_token")
