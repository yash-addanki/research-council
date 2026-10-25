"""The one interface every model CLI sits behind."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class RunResult:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    rate_limited: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Runner(Protocol):
    name: str

    def run(self, prompt: str, tier: str, *, web: bool = False, timeout_s: int = 900) -> RunResult: ...


@dataclass
class FakeRunner:
    """Test double: replays canned results and records every call."""
    name: str
    responses: list[RunResult]
    calls: list[tuple[str, str, bool]] = field(default_factory=list)

    def run(self, prompt: str, tier: str, *, web: bool = False, timeout_s: int = 900) -> RunResult:
        self.calls.append((prompt, tier, web))
        if not self.responses:
            return RunResult("", 0, 0, self.name, error="no more fake responses")
        return self.responses.pop(0)
