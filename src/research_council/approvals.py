"""WhatsApp approvals: send Yes/No buttons from the business number, poll the Supabase relay for the tap."""

import logging
import time
import uuid
from typing import Literal

import httpx

from research_council.secrets import get_secret

log = logging.getLogger(__name__)
GRAPH = "https://graph.facebook.com/v23.0"
OUTSIDE_WINDOW = 131047  # Meta: more than 24 h since the user last messaged; templates only
Answer = Literal["yes", "no", "timeout"]


class WhatsApp:
    def __init__(self, token: str, phone_id: str, to: str, relay_url: str, relay_secret: str,
                 client: httpx.Client | None = None, sleep=time.sleep, clock=time.time,
                 new_id=lambda: uuid.uuid4().hex[:12]):
        self.token, self.phone_id, self.to = token, phone_id, to
        self.relay_url, self.relay_secret = relay_url.rstrip("/"), relay_secret
        self.client = client or httpx.Client(timeout=30)
        self.sleep, self.clock, self.new_id = sleep, clock, new_id

    def _send(self, body: dict) -> httpx.Response:
        return self.client.post(f"{GRAPH}/{self.phone_id}/messages", json={"messaging_product": "whatsapp", "to": self.to, **body},
                                headers={"Authorization": f"Bearer {self.token}"})

    @staticmethod
    def _outside_window(resp: httpx.Response) -> bool:
        try:
            return resp.json().get("error", {}).get("code") == OUTSIDE_WINDOW
        except ValueError:
            return False

    def _send_with_fallback(self, body: dict, template: dict) -> bool:
        resp = self._send(body)
        if resp.status_code >= 400 and self._outside_window(resp):
            resp = self._send({"type": "template", "template": template})
        if resp.status_code >= 400:
            log.error("WhatsApp send failed: %s %s", resp.status_code, resp.text[:300])
            return False
        return True

    def notify(self, text: str) -> bool:
        template = {"name": "research_update", "language": {"code": "en"},
                    "components": [{"type": "body", "parameters": [{"type": "text", "text": text[:1000]}]}]}
        return self._send_with_fallback({"type": "text", "text": {"body": text[:4096]}}, template)

    def ask(self, question: str, timeout_s: int = 1800, poll_s: int = 20) -> Answer:
        aid = self.new_id()
        buttons = [{"type": "reply", "reply": {"id": f"{aid}:{a}", "title": a.capitalize()}} for a in ("yes", "no")]
        body = {"type": "interactive", "interactive": {"type": "button", "body": {"text": question[:1024]},
                                                        "action": {"buttons": buttons}}}
        template = {"name": "research_approval", "language": {"code": "en"}, "components": [
            {"type": "body", "parameters": [{"type": "text", "text": question[:1000]}]},
            *({"type": "button", "sub_type": "quick_reply", "index": str(i),
               "parameters": [{"type": "payload", "payload": f"{aid}:{a}"}]} for i, a in enumerate(("yes", "no"))),
        ]}
        sent = self._send_with_fallback(body, template)
        deadline = self.clock() + timeout_s
        while sent and self.clock() < deadline:
            self.sleep(poll_s)
            try:
                rows = self.client.get(f"{self.relay_url}/pending", params={"approval_id": aid},
                                       headers={"Authorization": f"Bearer {self.relay_secret}"}).json()
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("relay poll failed: %s", exc)
                continue
            for row in rows:
                if row.get("approval_id") == aid and row.get("answer") in ("yes", "no") \
                        and _digits(row.get("from_number")) == _digits(self.to):  # only Yash's own reply counts
                    return row["answer"]
        if not sent:
            self.sleep(min(timeout_s, poll_s))
        return "timeout"


def _digits(number) -> str:
    return "".join(ch for ch in str(number or "") if ch.isdigit())


def notifier_from_keychain() -> WhatsApp:
    return WhatsApp(get_secret("wa_token"), get_secret("wa_phone_id"), get_secret("wa_to"),
                    get_secret("relay_url"), get_secret("relay_secret"))


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        print(notifier_from_keychain().ask("research-council test: tap Yes or No", timeout_s=300))
