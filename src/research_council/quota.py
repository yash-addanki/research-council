"""Before a scheduled run: is Yash busy, and do the models have quota left? Then ask on WhatsApp."""

import json
import re
import subprocess
import time
from pathlib import Path

from research_council.state import State

IDLE_MIN_S = 900
WINDOW_S = 5 * 3600
CODEX_MAX_USED = 90.0
APPS = ("Antigravity", "Codex.app")
CODEX_SESSIONS = Path("~/.codex/sessions").expanduser()


def list_processes() -> list[str]:
    return subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True).stdout.splitlines()[1:]


def hid_idle_seconds() -> float:
    out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True).stdout
    m = re.search(r'"HIDIdleTime" = (\d+)', out)
    return int(m.group(1)) / 1e9 if m else 0.0


def _interactive(cmd: str, binary: str, headless_flags: tuple[str, ...]) -> bool:
    parts = cmd.split()
    idx = next((i for i, p in enumerate(parts) if Path(p).name == binary), None)
    if idx is None:
        return False
    return not any(flag in parts[idx + 1:] for flag in headless_flags)


def user_busy(process_cmds: list[str], hid_idle_s: float) -> bool:
    if hid_idle_s < IDLE_MIN_S:
        return True
    for cmd in process_cmds:
        if any(app in cmd for app in APPS):
            return True
        if (_interactive(cmd, "claude", ("-p", "--print")) or _interactive(cmd, "codex", ("exec",))
                or _interactive(cmd, "gemini", ("-p", "--prompt"))):
            return True
    return False


def codex_used_percent(sessions_dir: Path = CODEX_SESSIONS) -> float | None:
    """Codex writes rate-limit usage only into its session rollout files; read the newest one."""
    files = sorted(Path(sessions_dir).glob("*/*/*/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime)
    for path in reversed(files[-5:]):
        used = None
        for line in path.read_text().splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            limits = (ev.get("payload") or {}).get("rate_limits") if ev.get("type") == "event_msg" else None
            if limits and limits.get("primary"):
                used = limits["primary"].get("used_percent")
        if used is not None:
            return float(used)
    return None


def models_available(state: State, models: list[str], now: float, cap: int,
                     codex_used: float | None = None) -> list[str]:
    out = []
    for m in models:
        if state.in_cooldown(m, now) or state.calls_since(m, now - WINDOW_S) >= cap:
            continue
        if m == "codex" and codex_used is not None and codex_used >= CODEX_MAX_USED:
            continue
        out.append(m)
    return out


def ask_first(cfg, notion, notifier) -> bool:
    if notifier is None or not hasattr(notifier, "ask"):
        print("No WhatsApp notifier configured; scheduled runs need one to ask first.")
        return False
    if user_busy(list_processes(), hid_idle_seconds()):
        print("You're using the Mac or an AI tool right now; skipping this check.")
        return False
    now = time.time()
    cap = cfg.caps.get("calls_per_model_per_window", 60)
    available = models_available(State(cfg.paths.db), ["claude", "codex", "gemini"], now, cap, codex_used_percent())
    if len(available) < 2:
        print(f"Only {available} have quota left; skipping.")
        return False
    topic = notion.next_topic()
    if topic is None:
        return False
    answer = notifier.ask(f"Start research: {topic.title} ({topic.depth})? Models ready: {', '.join(available)}.")
    return answer == "yes"
