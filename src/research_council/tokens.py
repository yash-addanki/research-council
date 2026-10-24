"""Per-model token table for the end-of-run report."""

from research_council.state import UsageRow


def total_tokens(rows: list[UsageRow]) -> int:
    return sum(r.tokens_in + r.tokens_out for r in rows)


def token_table(rows: list[UsageRow], app_runs: list[str] = ()) -> str:
    per: dict[str, list[int]] = {}
    for r in rows:
        agg = per.setdefault(r.model, [0, 0, 0])
        agg[0] += 1
        agg[1] += r.tokens_in
        agg[2] += r.tokens_out
    lines = ["| Model | Calls | Tokens in | Tokens out | Total |", "|---|---|---|---|---|"]
    for model, (n, tin, tout) in per.items():
        lines.append(f"| {model} | {n} | {tin:,} | {tout:,} | {tin + tout:,} |")
    for app in app_runs:
        lines.append(f"| {app} | app run, not metered | | | |")
    calls = sum(v[0] for v in per.values())
    tin = sum(v[1] for v in per.values())
    tout = sum(v[2] for v in per.values())
    lines.append(f"| **Total** | {calls} | {tin:,} | {tout:,} | {tin + tout:,} |")
    return "\n".join(lines)
