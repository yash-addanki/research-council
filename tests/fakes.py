from research_council.notion import Topic


class FakeNotion:
    def __init__(self, topics=None):
        self.topics = list(topics or [])
        self.calls = []

    def next_topic(self):
        return self.topics[0] if self.topics else None

    def get_topic(self, page_id):
        return next(t for t in self.topics if t.page_id == page_id)

    def set_status(self, page_id, status):
        self.calls.append(("status", page_id, status))

    def set_props(self, page_id, **kw):
        self.calls.append(("props", page_id, kw))

    def append_markdown(self, page_id, md):
        self.calls.append(("append", page_id, md))


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def notify(self, text):
        self.sent.append(text)


def topic(page_id="p1", depth="High", title="Best local LLM for coding"):
    return Topic(page_id, title, "", depth, ["Tech"], depth)
