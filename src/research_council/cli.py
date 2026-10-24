"""`research` command: next | run <notion-url> | resume <run-id> | status."""

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

from research_council.config import Config, load_config
from research_council.conductor import Blocked, LeaseLost, run_pipeline
from research_council.notion import NotionClient, Topic
from research_council.runners.claude import ClaudeRunner
from research_council.runners.codex import CodexRunner
from research_council.runners.gemini import GeminiRunner
from research_council.secrets import get_secret
from research_council.state import State
from research_council.steps.context import RunContext

DEFAULT_CONFIG = Path("~/GitRepos/research-council/config.toml").expanduser()


def slugify(text: str, words: int = 7) -> str:
    parts = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(parts[:words]) or "topic"


def page_id_from(value: str) -> str:
    hexes = re.findall(r"[0-9a-f]{32}", value.replace("-", ""))
    h = hexes[-1] if hexes else value
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def make_runners(cfg: Config) -> dict:
    return {"claude": ClaudeRunner(cfg.tiers["claude"]), "codex": CodexRunner(cfg.tiers["codex"]),
            "gemini": GeminiRunner(cfg.tiers["gemini"]), "chrome": ClaudeRunner(cfg.tiers["claude"], chrome=True)}


def start_run(cfg: Config, notion, topic: Topic, dry_run: bool, notifier, run_id: str | None = None) -> int:
    state = State(cfg.paths.db)
    version = state.acquire_lease(topic.page_id, now=time.time())
    if version is None:
        print(f"'{topic.title}' is already running; nothing to do.")
        return 0
    run_id = run_id or f"{date.today().isoformat()}-{slugify(topic.title)}"
    run_dir = cfg.paths.runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "topic.json").write_text(json.dumps(topic.__dict__, indent=2))
    if not dry_run:
        notion.set_status(topic.page_id, "Researching")
        notion.set_props(topic.page_id, run_id=run_id)
    ctx = RunContext(run_id, run_dir, topic, topic.depth, make_runners(cfg), state, cfg, dry_run=dry_run)
    try:
        report = run_pipeline(ctx, notion, notifier, version)
        print(f"Done: {report}")
        return 0
    except (Blocked, LeaseLost) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        state.release(topic.page_id, version)


def cmd_next(cfg: Config, notion, dry_run: bool, notifier) -> int:
    topic = notion.next_topic()
    if topic is None:
        print("No topics with Status 'To Research'.")
        return 0
    return start_run(cfg, notion, topic, dry_run, notifier)


def cmd_status(cfg: Config) -> int:
    runs = sorted(cfg.paths.runs_dir.glob("*/topic.json"))
    for t in runs[-10:]:
        d = t.parent
        done = (d / "report_done.json").exists()
        steps = sorted(p.name for p in d.iterdir())
        print(f"{d.name}: {'done' if done else 'in progress / stopped'} ({len(steps)} files)")
    if not runs:
        print("No runs yet.")
    return 0


def _notifier():
    """WhatsApp notifier when its Keychain entries exist, else None."""
    try:
        from research_council.approvals import notifier_from_keychain
        return notifier_from_keychain()
    except Exception:
        return None


def cmd_tools(args, cfg: Config) -> int:
    from research_council import tools
    notifier = _notifier()
    ask = notifier.ask if notifier else None
    if args.cmd == "setup":
        results = tools.setup(args.config, cfg.allowlist, ask)
    else:
        cmd = args.install_cmd[1:] if args.install_cmd[:1] == ["--"] else args.install_cmd
        tool = tools.Tool(args.name, args.repo, ["sh", "-c", args.check], cmd)
        results = tools.setup(args.config, cfg.allowlist, ask, tools=[tool])
    for name, result in results.items():
        print(f"{name}: {result}")
    return 0 if "failed" not in results.values() else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="research")
    ap.add_argument("--config", type=Path, default=Path(os.environ.get("RESEARCH_COUNCIL_CONFIG", DEFAULT_CONFIG)))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_next = sub.add_parser("next", help="research the highest-priority 'To Research' topic")
    p_next.add_argument("--dry-run", action="store_true")
    p_next.add_argument("--ask-first", action="store_true", help="check idle/quota and ask on WhatsApp first")
    p_run = sub.add_parser("run", help="research one Notion topic by URL or id")
    p_run.add_argument("topic")
    p_run.add_argument("--dry-run", action="store_true")
    p_resume = sub.add_parser("resume", help="continue a stopped run")
    p_resume.add_argument("run_id")
    p_resume.add_argument("--dry-run", action="store_true")
    sub.add_parser("status", help="list recent runs")
    sub.add_parser("setup", help="install the allowlisted research tools")
    p_inst = sub.add_parser("install", help="install a new tool; asks on WhatsApp unless allowlisted")
    p_inst.add_argument("name")
    p_inst.add_argument("repo", help="owner/name on GitHub")
    p_inst.add_argument("--check", required=True, help="shell command that succeeds when already installed")
    p_inst.add_argument("install_cmd", nargs="+", help="install command, after --")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.cmd == "status":
        return cmd_status(cfg)
    if args.cmd in ("setup", "install"):
        return cmd_tools(args, cfg)
    notion = NotionClient(get_secret("notion_token"), cfg.notion_data_source_id)
    notifier = _notifier()
    if args.cmd == "next":
        if args.ask_first:
            from research_council.quota import ask_first
            if not ask_first(cfg, notion, notifier):
                return 0
        return cmd_next(cfg, notion, args.dry_run, notifier)
    if args.cmd == "run":
        return start_run(cfg, notion, notion.get_topic(page_id_from(args.topic)), args.dry_run, notifier)
    if args.cmd == "resume":
        run_dir = cfg.paths.runs_dir / args.run_id
        topic = Topic(**json.loads((run_dir / "topic.json").read_text()))
        return start_run(cfg, notion, topic, args.dry_run, notifier, run_id=args.run_id)
    return 2


if __name__ == "__main__":
    sys.exit(main())
