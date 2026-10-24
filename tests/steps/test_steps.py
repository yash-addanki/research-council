import json

from research_council.evidence import EvidenceItem
from research_council.runners.base import FakeRunner, RunResult
from research_council.steps import brief, chairman, citations, council, review, scout
from research_council.steps.util import parse_json

from .conftest import BRIEF, answer, ok


def ev(i, platform="web"):
    return EvidenceItem(f"https://s{i}.com", f"t{i}", platform, "ex", None, "now")


# --- util
def test_parse_json_strips_code_fences():
    assert parse_json('Here:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json("[1, 2]") == [1, 2]
    assert parse_json("no json here") is None


# --- brief
def test_brief_with_empty_notes_and_one_word_title(make_ctx):
    fake = FakeRunner("claude", [ok("sorry, I can't")])
    ctx = make_ctx({"claude": fake}, title="Agents", notes="")
    data = json.loads(brief.run(ctx).read_text())
    assert data["question"] and data["angles"] and data["social_queries"]
    assert data["kind"] in ("build", "knowledge")
    assert "Agents" in fake.calls[0][0]


def test_brief_uses_model_json(make_ctx):
    ctx = make_ctx({"claude": FakeRunner("claude", [ok(BRIEF)])})
    assert json.loads(brief.run(ctx).read_text())["angles"] == ["a1", "a2"]


# --- scout
def test_scout_caps_by_depth(make_ctx, monkeypatch):
    ctx = make_ctx({}, depth="High")
    ctx.write_json("brief.json", BRIEF)
    monkeypatch.setattr(scout, "web_search", lambda ctx, q, limit: [ev(f"{q}{i}") for i in range(50)])
    monkeypatch.setattr(scout, "SOCIAL_SOURCES", {"hn": lambda q, limit: [ev(f"hn{q}{i}", "hn") for i in range(50)]})
    monkeypatch.setattr(scout, "REPO_SOURCE", lambda q, limit: [])
    lines = scout.run(ctx).read_text().splitlines()
    assert len(lines) == 60


def test_scout_keeps_social_share(make_ctx, monkeypatch):
    ctx = make_ctx({}, depth="Low")
    ctx.write_json("brief.json", BRIEF)
    monkeypatch.setattr(scout, "web_search", lambda ctx, q, limit: [ev(f"{q}{i}") for i in range(50)])
    monkeypatch.setattr(scout, "SOCIAL_SOURCES", {"hn": lambda q, limit: [ev(f"hn{i}", "hn") for i in range(50)]})
    monkeypatch.setattr(scout, "REPO_SOURCE", lambda q, limit: [])
    items = [json.loads(l) for l in scout.run(ctx).read_text().splitlines()]
    assert sum(i["platform"] == "hn" for i in items) >= 10


def test_scout_survives_source_failure(make_ctx, monkeypatch):
    ctx = make_ctx({})
    ctx.write_json("brief.json", BRIEF)

    def boom(q, limit):
        raise RuntimeError("down")
    monkeypatch.setattr(scout, "web_search", lambda ctx, q, limit: [ev(q)])
    monkeypatch.setattr(scout, "SOCIAL_SOURCES", {"reddit": boom})
    monkeypatch.setattr(scout, "REPO_SOURCE", boom)
    assert len(scout.run(ctx).read_text().splitlines()) == 2


# --- council
def test_council_continues_when_one_member_errors(make_ctx):
    runners = {
        "claude": FakeRunner("claude", [ok(answer([]))]),
        "codex": FakeRunner("codex", [RunResult("", 0, 0, "m", error="auth expired")]),
        "gemini": FakeRunner("gemini", [ok(answer([]))]),
    }
    ctx = make_ctx(runners)
    ctx.write_json("brief.json", BRIEF)
    ctx.path("evidence.jsonl").write_text(json.dumps(ev(1).to_dict()) + "\n")
    council.run(ctx)
    assert ctx.path("answer.claude.json").exists() and ctx.path("answer.gemini.json").exists()
    assert not ctx.path("answer.codex.json").exists()
    assert ctx.read_json("missing.json")["codex"] == "auth expired"


def test_council_includes_deep_research_reports(make_ctx):
    ctx = make_ctx({"claude": FakeRunner("claude", [ok(answer([]))])})
    ctx.write_json("brief.json", BRIEF)
    ctx.path("evidence.jsonl").write_text("")
    ctx.path("deep.gemini_app.md").write_text("Gemini deep report")
    council.run(ctx)
    assert council.load_answers(ctx)["gemini_app"]["conclusion"] == "Gemini deep report"


# --- citations
def test_citations_marks_unreachable_without_model_call(make_ctx, monkeypatch):
    fake = FakeRunner("gemini", [])
    ctx = make_ctx({"gemini": fake})
    ctx.write_json("answer.claude.json", answer([{"id": "c1", "claim": "X", "source_urls": ["https://dead"], "confidence": 0.9}]))
    monkeypatch.setattr(citations, "fetch_text", lambda url, **k: None)
    data = json.loads(citations.run(ctx).read_text())
    assert data == [{"member": "claude", "id": "c1", "url": "https://dead", "label": "unreachable"}]
    assert fake.calls == []


def test_citations_batches_pairs(make_ctx, monkeypatch):
    claims = [{"id": f"c{i}", "claim": f"claim {i}", "source_urls": [f"https://s{i}"], "confidence": 0.9} for i in range(10)]
    reply = lambda n: ok({"results": [{"n": k, "label": "supported"} for k in range(n)]})
    fake = FakeRunner("gemini", [reply(8), reply(2)])
    ctx = make_ctx({"gemini": fake})
    ctx.write_json("answer.claude.json", answer(claims))
    monkeypatch.setattr(citations, "fetch_text", lambda url, **k: "page text")
    data = json.loads(citations.run(ctx).read_text())
    assert len(fake.calls) == 2 and all(d["label"] == "supported" for d in data)


def test_citations_low_depth_checks_only_confident_claims(make_ctx, monkeypatch):
    claims = [{"id": "c1", "claim": "a", "source_urls": ["https://a"], "confidence": 0.9},
              {"id": "c2", "claim": "b", "source_urls": ["https://b"], "confidence": 0.3}]
    ctx = make_ctx({"gemini": FakeRunner("gemini", [ok({"results": [{"n": 0, "label": "supported"}]})])}, depth="Low")
    ctx.write_json("answer.claude.json", answer(claims))
    monkeypatch.setattr(citations, "fetch_text", lambda url, **k: "t")
    assert [d["id"] for d in json.loads(citations.run(ctx).read_text())] == ["c1"]


# --- review
def _two_members(ctx, label_c2="supported"):
    ctx.write_json("answer.claude.json", answer([{"id": "c1", "claim": "agreed fact", "source_urls": ["u1"], "confidence": 0.9}]))
    ctx.write_json("answer.codex.json", answer([{"id": "c2", "claim": "contested fact", "source_urls": ["u2"], "confidence": 0.5}]))
    ctx.write_json("citations.json", [
        {"member": "claude", "id": "c1", "url": "u1", "label": "supported"},
        {"member": "codex", "id": "c2", "url": "u2", "label": label_c2},
    ])
    ctx.write_json("brief.json", BRIEF)


def test_should_skip_review_true_when_agree_and_90pct():
    answers = {"claude": answer([{"id": "c1"}]), "codex": answer([{"id": "c2"}])}
    cits = [{"member": "claude", "id": "c1", "label": "supported"}, {"member": "codex", "id": "c2", "label": "supported"}]
    assert review.should_skip_review(answers, cits, agree=True)
    assert not review.should_skip_review(answers, cits, agree=False)
    cits[1]["label"] = "unsupported"
    assert not review.should_skip_review(answers, cits, agree=True)


def test_review_sends_only_disputed_claims(make_ctx):
    agree = ok({"agree": False, "points": ["which model"]})
    verdicts = ok({"verdicts": [{"id": "B.c2", "verdict": "reject", "reason": "r", "source_urls": []}]})
    fake = FakeRunner("claude", [agree, verdicts, verdicts])
    ctx = make_ctx({"claude": fake, "codex": FakeRunner("codex", [verdicts])})
    _two_members(ctx, label_c2="unsupported")
    review.run(ctx)
    review_prompts = [c[0] for c in fake.calls[1:]]
    assert any("contested fact" in p for p in review_prompts)
    assert not any("agreed fact" in p for p in review_prompts)


def test_review_anonymises_members(make_ctx):
    agree = ok({"agree": False, "points": []})
    verdicts = ok({"verdicts": []})
    fake = FakeRunner("claude", [agree, verdicts])
    ctx = make_ctx({"claude": fake, "codex": FakeRunner("codex", [verdicts])})
    _two_members(ctx, label_c2="unsupported")
    review.run(ctx)
    for prompt, _, _ in fake.calls[1:]:
        low = prompt.lower()
        assert "claude" not in low and "codex" not in low and "gemini" not in low


def test_review_skipped_at_low_depth(make_ctx):
    fake = FakeRunner("claude", [])
    ctx = make_ctx({"claude": fake}, depth="Low")
    _two_members(ctx, label_c2="unsupported")
    assert json.loads(review.run(ctx).read_text())["skipped"] is True
    assert fake.calls == []


# --- chairman
def test_chairman_marks_unverified(make_ctx):
    fake = FakeRunner("claude", [ok("## Answer\nUse X\n\n## Unverified\n\n## Sources\n")])
    ctx = make_ctx({"claude": fake})
    _two_members(ctx, label_c2="unsupported")
    ctx.write_json("review.json", {"skipped": True})
    report = chairman.run(ctx).read_text()
    unverified = report.split("## Unverified")[1].split("## Sources")[0]
    assert "contested fact" in unverified
    assert fake.calls[0][1] == "top"


def test_chairman_writes_ranked_repos(make_ctx):
    ctx = make_ctx({"claude": FakeRunner("claude", [ok("## Answer\nx")])})
    ctx.write_json("brief.json", BRIEF)
    ctx.write_json("answer.claude.json", answer([], repos=[{"full_name": "a/b", "why": "w", "relevance": 0.9}]))
    ctx.write_json("answer.codex.json", answer([], repos=[{"full_name": "A/B", "why": "w", "relevance": 0.7},
                                                         {"full_name": "c/d", "why": "w", "relevance": 0.5}]))
    ctx.write_json("citations.json", [])
    ctx.write_json("review.json", {"skipped": True})
    chairman.run(ctx)
    repos = ctx.read_json("repos.json")
    assert repos[0]["full_name"].lower() == "a/b" and abs(repos[0]["relevance"] - 0.8) < 1e-9
    assert repos[0]["votes"] == 2
