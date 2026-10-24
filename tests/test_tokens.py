from research_council.state import UsageRow
from research_council.tokens import token_table, total_tokens


def test_token_table_totals():
    rows = [UsageRow("r", "brief", "claude", 100, 10), UsageRow("r", "council", "claude", 1000, 200),
            UsageRow("r", "council", "codex", 500, 50)]
    table = token_table(rows, app_runs=["gemini_app"])
    lines = table.splitlines()
    assert lines[0].startswith("| Model |")
    assert "| claude | 2 | 1,100 | 210 | 1,310 |" in table
    assert "| codex | 1 | 500 | 50 | 550 |" in table
    assert "| **Total** | 3 | 1,600 | 260 | 1,860 |" in table
    assert "| gemini_app | app run, not metered |" in table
    assert total_tokens(rows) == 1860
