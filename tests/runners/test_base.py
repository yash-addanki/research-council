from research_council.runners.base import FakeRunner, RunResult


def test_fake_runner_returns_responses_in_order_and_records_prompts():
    fake = FakeRunner("claude", [RunResult("a", 1, 1, "m"), RunResult("b", 2, 2, "m")])
    assert fake.run("p1", "cheap").text == "a"
    assert fake.run("p2", "top", web=True).text == "b"
    assert fake.calls == [("p1", "cheap", False), ("p2", "top", True)]


def test_fake_runner_exhausted_returns_error():
    fake = FakeRunner("codex", [])
    assert not fake.run("p", "cheap").ok


def test_runresult_ok():
    assert RunResult("x", 0, 0, "m").ok
    assert not RunResult("", 0, 0, "m", error="boom").ok
