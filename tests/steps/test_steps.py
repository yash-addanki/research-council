import json
import pytest

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
    monkeypatch.setattr(scout, "web_search", lambda ctx, qs, limit: [ev(f"{q}{i}") for q in qs for i in range(50)])
    monkeypatch.setattr(scout, "SOCIAL_SOURCES", {"hn": lambda q, limit: [ev(f"hn{q}{i}", "hn") for i in range(50)]})
    monkeypatch.setattr(scout, "REPO_SOURCE", lambda q, limit: [])
    lines = scout.run(ctx).read_text().splitlines()
    assert len(lines) == 60


def test_scout_keeps_social_share(make_ctx, monkeypatch):
    ctx = make_ctx({}, depth="Low")
    ctx.write_json("brief.json", BRIEF)
    monkeypatch.setattr(scout, "web_search", lambda ctx, qs, limit: [ev(f"{q}{i}") for q in qs for i in range(50)])
    monkeypatch.setattr(scout, "SOCIAL_SOURCES", {"hn": lambda q, limit: [ev(f"hn{i}", "hn") for i in range(50)]})
    monkeypatch.setattr(scout, "REPO_SOURCE", lambda q, limit: [])
    items = [json.loads(l) for l in scout.run(ctx).read_text().splitlines()]
    assert sum(i["platform"] == "hn" for i in items) >= 10


def test_scout_survives_source_failure(make_ctx, monkeypatch):
    ctx = make_ctx({})
    ctx.write_json("brief.json", BRIEF)

    def boom(q, limit):
        raise RuntimeError("down")
    monkeypatch.setattr(scout, "web_search", lambda ctx, qs, limit: [ev(q) for q in qs])
    monkeypatch.setattr(scout, "SOCIAL_SOURCES", {"reddit": boom})
    monkeypatch.setattr(scout, "REPO_SOURCE", boom)
    assert len(scout.run(ctx).read_text().splitlines()) == 2


def test_scout_makes_one_web_call_for_all_angles_and_skips_gemini(make_ctx, monkeypatch):
    rows = [{"url": f"https://s{i}", "title": "t", "excerpt": "e"} for i in range(4)]
    codex, gemini = FakeRunner("codex", [ok(rows)]), FakeRunner("gemini", [])
    ctx = make_ctx({"codex": codex, "gemini": gemini})
    ctx.write_json("brief.json", BRIEF)
    monkeypatch.setattr(scout, "SOCIAL_SOURCES", {})
    monkeypatch.setattr(scout, "REPO_SOURCE", lambda q, limit: [])
    items = [json.loads(l) for l in scout.run(ctx).read_text().splitlines()]
    assert len(codex.calls) == 1 and gemini.calls == [] and len(items) == 4
    assert "a1" in codex.calls[0][0] and "a2" in codex.calls[0][0]


def test_scout_swaps_short_excerpt_for_real_page_passage(make_ctx, monkeypatch):
    ctx = make_ctx({})
    ctx.write_json("brief.json", BRIEF)
    monkeypatch.setattr(scout, "web_search", lambda ctx, qs, limit: [ev("x")])
    monkeypatch.setattr(scout, "SOCIAL_SOURCES", {})
    monkeypatch.setattr(scout, "REPO_SOURCE", lambda q, limit: [])
    monkeypatch.setattr(scout, "fetch_text", lambda url, **k: "menu " * 300 + "the best local LLM for coding is X " * 5)
    item = json.loads(scout.run(ctx).read_text().splitlines()[0])
    assert "best local LLM for coding" in item["excerpt"]


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


def test_council_collects_deep_reports_alongside_members(make_ctx, monkeypatch):
    ctx = make_ctx({"claude": FakeRunner("claude", [ok(answer([]))])})
    ctx.write_json("brief.json", BRIEF)
    ctx.path("evidence.jsonl").write_text("")
    monkeypatch.setattr(council.chrome_deep, "collect",
                        lambda c: [c.path("deep.muse.md").write_text("Muse report") and c.path("deep.muse.md")])
    council.run(ctx)
    answers = council.load_answers(ctx)
    assert answers["muse"]["conclusion"] == "Muse report" and "claude" in answers


def test_council_survives_deep_collect_crash(make_ctx, monkeypatch):
    ctx = make_ctx({"claude": FakeRunner("claude", [ok(answer([]))])})
    ctx.write_json("brief.json", BRIEF)
    ctx.path("evidence.jsonl").write_text("")
    monkeypatch.setattr(council.chrome_deep, "collect", lambda c: 1 / 0)
    council.run(ctx)
    assert "deep_research" in ctx.read_json("missing.json")


def test_ensure_unverified_skips_paraphrased_claims():
    report = "## Answer\nx\n\n## Unverified\n\n- The README says llm-council is 99% vibe coded and unsupported.\n"
    out = chairman.ensure_unverified(report, ["llm-council README says it is 99% vibe coded and unsupported by the author",
                                              "Mistral Large 3 costs $0.50 per million input tokens"])
    assert "vibe coded and unsupported by the author" not in out and "Mistral Large 3" in out


def test_ensure_unverified_adds_missed_claims_after_the_curated_list_once():
    report = "## Answer\nx\n\n## Unverified\n\n- curated item\n\n## Sources\n1. a\n"
    out = chairman.ensure_unverified(report, ["Mistral Large 3 costs $0.50 per million input tokens",
                                              "Mistral  Large 3 costs $0.50 per million input tokens."])
    unverified = out.split("## Unverified", 1)[1].split("## Sources", 1)[0]
    assert unverified.index("curated item") < unverified.index("Mistral")
    assert out.count("Mistral") == 1 and out.rstrip().endswith("1. a")


# --- run history as evidence
def _past_run(runs_dir, name, ctx):
    d = runs_dir / name
    d.mkdir()
    (d / "topic.json").write_text(json.dumps({"title": "Old topic", "page_id": "p0", "depth": "High"}))
    (d / "evidence.jsonl").write_text('{"url": "https://a"}\n')
    (d / "missing.json").write_text(json.dumps({"gemini": "empty reply; denied tools: RunCommand"}))
    ctx.state.record_usage(name, "council", "codex", 90_000, 5_000, 1.0)


def test_scout_adds_past_runs_for_topics_about_this_tool(make_ctx, monkeypatch):
    ctx = make_ctx()
    _past_run(ctx.run_dir.parent, "old-run", ctx)
    ctx.write_json("brief.json", {**BRIEF, "about_this_tool": True})
    (ctx.run_dir / "topic.json").write_text(json.dumps({"title": "now", "page_id": "p1"}))
    monkeypatch.setattr(scout, "web_search", lambda ctx, qs, limit: [ev("w")])
    monkeypatch.setattr(scout, "SOCIAL_SOURCES", {})
    monkeypatch.setattr(scout, "REPO_SOURCE", lambda q, limit: [])
    items = [json.loads(l) for l in scout.run(ctx).read_text().splitlines()]
    hist = [i for i in items if i["platform"] == "run-history"]
    assert [i["url"] for i in hist] == ["runs://old-run"]  # the current run is not its own evidence
    facts = json.loads(hist[0]["excerpt"])
    assert facts["tokens"]["total"] == 95_000 and "denied tools" in facts["council_member_errors"]["gemini"]


def test_scout_leaves_run_history_out_of_other_topics(make_ctx, monkeypatch):
    ctx = make_ctx()
    _past_run(ctx.run_dir.parent, "old-run", ctx)
    ctx.write_json("brief.json", BRIEF)
    monkeypatch.setattr(scout, "web_search", lambda ctx, qs, limit: [ev("w")])
    monkeypatch.setattr(scout, "SOCIAL_SOURCES", {})
    monkeypatch.setattr(scout, "REPO_SOURCE", lambda q, limit: [])
    assert all(json.loads(l)["platform"] != "run-history" for l in scout.run(ctx).read_text().splitlines())


def test_citations_check_run_history_claims_against_the_summary(make_ctx, monkeypatch):
    fake = FakeRunner("gemini", [ok({"results": [{"n": 0, "label": "supported"}]})])
    ctx = make_ctx({"gemini": fake})
    ctx.path("evidence.jsonl").write_text(json.dumps({"url": "runs://old", "excerpt": '{"tokens": {"total": 95000}}'}) + "\n")
    ctx.write_json("answer.claude.json", answer([{"id": "c1", "claim": "used 95k", "source_urls": ["runs://old"], "confidence": 0.9}]))
    monkeypatch.setattr(citations, "fetch_text", lambda url, **k: pytest.fail("runs:// is not fetched"))
    data = json.loads(citations.run(ctx).read_text())
    assert data[0]["label"] == "supported" and "95000" in fake.calls[0][0]


def test_citations_verbatim_claim_is_supported_without_model(make_ctx, monkeypatch):
    fake = FakeRunner("gemini", [])
    ctx = make_ctx({"gemini": fake})
    ctx.write_json("answer.claude.json", answer([{"id": "c1", "claim": "Beam merges  answers", "source_urls": ["https://a"], "confidence": 0.9}]))
    monkeypatch.setattr(citations, "fetch_text", lambda url, **k: "menu " * 2000 + "big-AGI Beam merges answers from many models")
    data = json.loads(citations.run(ctx).read_text())
    assert data[0]["label"] == "supported" and fake.calls == []
