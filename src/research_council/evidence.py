"""Evidence items gathered by scouts, with URL canonicalisation and dedupe."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass
class EvidenceItem:
    url: str
    title: str
    platform: str
    excerpt: str
    published_at: str | None
    fetched_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")]
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def dedupe(items: list[EvidenceItem]) -> list[EvidenceItem]:
    seen: set[str] = set()
    out = []
    for item in items:
        key = canonical_url(item.url)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out
