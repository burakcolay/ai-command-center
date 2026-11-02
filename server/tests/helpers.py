"""Shared helpers: every user action is just a chat message now."""

import subprocess
import time

import pytest

from acc.adapters import registry
from acc.adapters.mock import MockAdapter


def git(cwd, *args) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


_n = 0


def project(client) -> dict:
    global _n
    _n += 1
    r = client.post("/api/projects", json={"name": f"Test Proje {_n}"})
    assert r.status_code == 201, r.text
    return r.json()


def new_chat(client, project_id=None) -> int:
    return client.post("/api/chats", json={"project_id": project_id}).json()["id"]


def send(client, chat_id, text, project_id=None, attachments=None) -> int:
    """Posts a message; returns the id of the assistant reply."""
    body = {"content": text, "project_id": project_id, "attachments": attachments or []}
    r = client.post(f"/api/chats/{chat_id}/messages", json=body)
    assert r.status_code == 201, r.text
    return r.json()["messages"][1]["id"]


def chat_state(client, chat_id) -> dict:
    return client.get(f"/api/chats/{chat_id}").json()


def wait_msg(client, chat_id, msg_id, status="done", timeout=10) -> dict:
    deadline = time.time() + timeout
    m = None
    while time.time() < deadline:
        m = next(x for x in chat_state(client, chat_id)["messages"] if x["id"] == msg_id)
        if m["status"] == status:
            return m
        time.sleep(0.02)
    raise AssertionError(f"message {msg_id} never reached {status}: {m}")


def turn(client, chat_id, text, project_id=None, attachments=None) -> dict:
    """Sends a message and waits for the finished reply."""
    return wait_msg(client, chat_id, send(client, chat_id, text, project_id, attachments))


def task(client, chat_id, task_id) -> dict:
    return next(t for t in chat_state(client, chat_id)["tasks"] if t["id"] == task_id)


def decide(client, task_id, decision):
    return client.post(f"/api/tasks/{task_id}/decision", json={"decision": decision})


def diff_lines(client, task_id) -> int:
    return client.get(f"/api/tasks/{task_id}/diff").json()["patch"].count("+Demo adaptörünün")


class Recorder(MockAdapter):
    """Mock that remembers every request it was given."""

    def __init__(self, delay=0.01):
        super().__init__(delay)
        self.requests = []

    async def run(self, req, run_id):
        self.requests.append(req)
        async for ev in super().run(req, run_id):
            yield ev


def use(*adapters):
    """Swap the registered adapters for the length of a test."""
    original = registry._adapters
    registry._adapters = {a.info.id: a for a in adapters}
    registry._health.clear()
    return original


@pytest.fixture
def rec():
    r = Recorder()
    original = use(r)
    yield r
    registry._adapters = original
    registry._health.clear()


@pytest.fixture
def slow():
    original = use(MockAdapter(delay=3.0))
    yield
    registry._adapters = original
    registry._health.clear()
