"""Shared helpers for steps."""

import json
import re


def parse_json(text: str):
    """Pull the first JSON object or array out of a model reply (tolerates code fences and prose)."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidates = [fenced.group(1)] if fenced else []
    candidates.append(text)
    for cand in candidates:
        cand = cand.strip()
        for opener, closer in (("{", "}"), ("[", "]")):
            start, end = cand.find(opener), cand.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(cand[start:end + 1])
                except json.JSONDecodeError:
                    continue
    return None


def evidence_text(items: list[dict], max_chars: int = 30000) -> str:
    lines, total = [], 0
    for i, e in enumerate(items, 1):
        line = f"[{i}] ({e['platform']}, {e.get('published_at') or 'undated'}) {e['title']} — {e['url']}\n    {e['excerpt']}"
        total += len(line)
        if total > max_chars:
            break
        lines.append(line)
    return "\n".join(lines)
