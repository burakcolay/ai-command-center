import time

import pytest

from acc.adapters import registry
from acc.adapters.mock import MockAdapter


class _Recorder(MockAdapter):
    """Mock that remembers every request it was given."""

    def __init__(self, delay=0.01):
        super().__init__(delay)
        self.requests = []

    async def run(self, req, run_id):
        self.requests.append(req)
        async for ev in super().run(req, run_id):
            yield ev


@pytest.fixture
def rec():
    original = registry._adapters
    r = _Recorder()
    registry._adapters = {"mock": r}
    registry._health.clear()
    yield r
    registry._adapters = original


def _wait_msg(client, chat_id, msg_id, status, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        m = next(
            x for x in client.get(f"/api/chats/{chat_id}").json()["messages"] if x["id"] == msg_id
        )
        if m["status"] == status:
            return m
        time.sleep(0.02)
    raise AssertionError(f"message {msg_id} never reached {status}: {m}")


def _say(client, chat_id, text, mode="chat", project_id=None):
    r = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": text, "mode": mode, "project_id": project_id},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_chat_reply_streams_and_completes(client, rec):
    chat = client.post("/api/chats", json={}).json()
    out = _say(client, chat["id"], "Merhaba")
    assert out["task"] is None
    reply = out["messages"][1]
    assert reply["role"] == "assistant" and reply["status"] == "streaming"
    done = _wait_msg(client, chat["id"], reply["id"], "done")
    assert "Göreve dönüştür" in done["content"]
    req = rec.requests[-1]
    assert req.stream_text and req.json_schema is None
    # No project: the assistant may search the web but has no file tools.
    assert req.tools == ["WebSearch", "WebFetch"]


def test_chat_remembers_history(client, rec):
    chat = client.post("/api/chats", json={}).json()
    first = _say(client, chat["id"], "Uygulamanın adı Orbit olsun")
    _wait_msg(client, chat["id"], first["messages"][1]["id"], "done")
    second = _say(client, chat["id"], "Adı neydi?")
    _wait_msg(client, chat["id"], second["messages"][1]["id"], "done")
    prompt = rec.requests[-1].prompt
    assert "Kullanıcı: Uygulamanın adı Orbit olsun" in prompt
    assert "Asistan: Demo yanıtı" in prompt
    assert prompt.rstrip().endswith("Adı neydi?")


def test_project_chat_is_read_only(client, rec):
    p = client.post("/api/projects", json={"name": "Sohbet Proje"}).json()
    chat = client.post("/api/chats", json={"project_id": p["id"]}).json()
    out = _say(client, chat["id"], "Kodu incele", project_id=p["id"])
    _wait_msg(client, chat["id"], out["messages"][1]["id"], "done")
    req = rec.requests[-1]
    assert str(req.cwd) == p["path"]
    assert not {"Edit", "Write", "Bash"} & set(req.tools)


def test_task_after_chat_carries_the_conversation(client, rec):
    chat = client.post("/api/chats", json={}).json()
    first = _say(client, chat["id"], "Giriş ekranı koyu temalı ve tek sütun olsun")
    _wait_msg(client, chat["id"], first["messages"][1]["id"], "done")
    out = _say(client, chat["id"], "Kararlaştırdıklarımızı uygula", mode="task")
    assert out["task"]["status"] == "planning"
    deadline = time.time() + 5
    while time.time() < deadline and not any(r.json_schema for r in rec.requests):
        time.sleep(0.02)
    plan_req = next(r for r in rec.requests if r.json_schema)
    assert "SOHBET GEÇMİŞİ" in plan_req.prompt
    assert "Giriş ekranı koyu temalı ve tek sütun olsun" in plan_req.prompt


@pytest.fixture
def slow():
    original = registry._adapters
    registry._adapters = {"mock": MockAdapter(delay=1.0)}
    yield
    registry._adapters = original


def test_cancel_keeps_partial_answer_and_blocks_overlap(client, slow):
    chat = client.post("/api/chats", json={}).json()
    out = _say(client, chat["id"], "Uzun bir yanıt ver")
    msg_id = out["messages"][1]["id"]
    time.sleep(0.35)  # a few chunks arrive
    # A second chat message while the first reply is still being written is refused.
    r = client.post(f"/api/chats/{chat['id']}/messages", json={"content": "x", "mode": "chat"})
    assert r.status_code == 409
    assert client.post(f"/api/messages/{msg_id}/cancel").status_code == 200
    m = _wait_msg(client, chat["id"], msg_id, "cancelled")
    assert m["content"].startswith("Demo yanıtı") and m["content"].endswith("_(durduruldu)_")
