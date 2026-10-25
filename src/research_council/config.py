"""Load research-council settings from a TOML file."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Paths:
    runs_dir: Path
    gitrepos: Path
    db: Path


@dataclass
class Config:
    tiers: dict[str, dict[str, str]]
    caps: dict[str, int]
    paths: Paths
    notion_data_source_id: str
    allowlist: list[str] = field(default_factory=list)


def _path(value: str) -> Path:
    return Path(value).expanduser()


def load_config(path: Path) -> Config:
    data = tomllib.loads(Path(path).read_text())
    p = data["paths"]
    return Config(
        tiers=data["tiers"],
        caps=data["caps"],
        paths=Paths(_path(p["runs_dir"]), _path(p["gitrepos"]), _path(p["db"])),
        notion_data_source_id=data["notion_data_source_id"],
        allowlist=data.get("allowlist", []),
    )
