import json

import httpx

from research_council.approvals import WhatsApp


class Graph:
    """Fake Graph API + relay."""
    def __init__(self, replies=None, send_status=200, send_error=None):
        self.replies = replies or {}
        self.sent = []
        self.polls = 0
        self.send_status, self.send_error = send_status, send_error

    def __call__(self, req: httpx.Request):
        if req.url.host == "graph.facebook.com":
            body = json.loads(req.content)
            self.sent.append(body)
            if self.send_error and body["type"] != "template":
                return httpx.Response(400, json={"error": {"code": self.send_error, "message": "re-engagement"}})
            return httpx.Response(self.send_status, json={"messages": [{"id": "wamid.1"}]})
        self.polls += 1
        assert req.headers["authorization"] == "Bearer relay"
        aid = req.url.params["approval_id"]
        return httpx.Response(200, json=self.replies.get(aid, []) if self.polls >= 2 else [])


def wa(graph, clock):
    return WhatsApp("tok", "PHONE", "15550001", "https://relay.example/functions/v1/wa-webhook", "relay",
                    client=httpx.Client(transport=httpx.MockTransport(graph)), sleep=lambda s: clock.__setitem__(0, clock[0] + s),
                    clock=lambda: clock[0], new_id=lambda: "abc123")


def test_ask_sends_buttons_and_returns_yes_on_matching_reply():
    g = Graph(replies={"abc123": [{"approval_id": "abc123", "answer": "yes", "from_number": "15550001"}]})
    assert wa(g, [0.0]).ask("Start research: X?") == "yes"
    msg = g.sent[0]
    assert msg["type"] == "interactive" and msg["to"] == "15550001"
    ids = [b["reply"]["id"] for b in msg["interactive"]["action"]["buttons"]]
    assert ids == ["abc123:yes", "abc123:no"]


def test_ask_ignores_other_approval_ids():
    g = Graph(replies={"zzz": [{"approval_id": "zzz", "answer": "yes"}]})
    assert wa(g, [0.0]).ask("q", timeout_s=100, poll_s=20) == "timeout"


def test_ask_timeout_is_no_reply():
    g = Graph()
    clock = [0.0]
    assert wa(g, clock).ask("q", timeout_s=60, poll_s=20) == "timeout"
    assert clock[0] >= 60


def test_ask_falls_back_to_template_outside_24h_window():
    g = Graph(replies={"abc123": [{"approval_id": "abc123", "answer": "no", "from_number": "15550001"}]}, send_error=131047)
    assert wa(g, [0.0]).ask("q") == "no"
    tmpl = g.sent[1]
    assert tmpl["type"] == "template" and tmpl["template"]["name"] == "research_approval"
    payloads = [c["parameters"][0]["payload"] for c in tmpl["template"]["components"] if c["type"] == "button"]
    assert payloads == ["abc123:yes", "abc123:no"]


def test_notify_sends_text():
    g = Graph()
    wa(g, [0.0]).notify("done")
    assert g.sent[0]["type"] == "text" and g.sent[0]["text"]["body"] == "done"


def test_send_failure_counts_as_no_reply():
    g = Graph(send_status=500)
    assert wa(g, [0.0]).ask("q", timeout_s=40) == "timeout"


def test_ask_ignores_reply_from_another_number():
    g = Graph(replies={"abc123": [{"approval_id": "abc123", "answer": "yes", "from_number": "19998887777"}]})
    assert wa(g, [0.0]).ask("q", timeout_s=100, poll_s=20) == "timeout"
