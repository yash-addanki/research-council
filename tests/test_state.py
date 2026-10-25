import pytest

from research_council.state import State


@pytest.fixture
def state(tmp_path):
    return State(tmp_path / "s.db")


def test_second_lease_denied_while_live(state):
    assert state.acquire_lease("t1", now=1000) == 1
    assert state.acquire_lease("t1", now=1001) is None


def test_lease_reacquired_after_ttl(state):
    state.acquire_lease("t1", now=1000)
    assert state.acquire_lease("t1", now=1000 + 1801) == 2


def test_released_lease_can_be_reacquired(state):
    v = state.acquire_lease("t1", now=1000)
    state.release("t1", v)
    assert state.acquire_lease("t1", now=1001) == 2


def test_stale_version_heartbeat_fails(state):
    state.acquire_lease("t1", now=1000)
    state.acquire_lease("t1", now=3000)  # expired, version 2
    assert state.heartbeat("t1", 1, now=3001) is False
    assert state.heartbeat("t1", 2, now=3001) is True


def test_heartbeat_extends_lease(state):
    state.acquire_lease("t1", now=1000)
    state.heartbeat("t1", 1, now=2500)
    assert state.acquire_lease("t1", now=3000) is None


def test_cooldown_expires(state):
    state.set_cooldown("codex", until=2000)
    assert state.in_cooldown("codex", now=1999)
    assert not state.in_cooldown("codex", now=2001)
    assert not state.in_cooldown("gemini", now=1000)


def test_usage_rows_roundtrip(state):
    state.record_usage("r1", "council", "claude", 100, 20, now=1000)
    state.record_usage("r1", "brief", "claude", 10, 5, now=1001)
    state.record_usage("r2", "brief", "codex", 1, 1, now=1002)
    rows = state.usage_for_run("r1")
    assert [(r.step, r.model, r.tokens_in, r.tokens_out) for r in rows] == [
        ("council", "claude", 100, 20),
        ("brief", "claude", 10, 5),
    ]


def test_calls_since_counts_recent_calls(state):
    state.record_usage("r1", "a", "claude", 1, 1, now=1000)
    state.record_usage("r1", "b", "claude", 1, 1, now=2000)
    assert state.calls_since("claude", since=1500) == 1


def test_record_usage_is_thread_safe(state):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda i: state.record_usage("r", "s", "m", i, i, now=i), range(400)))
    assert len(state.usage_for_run("r")) == 400
