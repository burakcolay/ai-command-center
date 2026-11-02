"""Quota: a turn that hits the subscription limit waits and continues by itself."""

import time

import pytest

from acc import chat as chat_module
from acc import notify
from acc.adapters import registry
from acc.adapters.base import ModelState, QuotaExceeded, RunRequest
from acc.adapters.claude_code import ClaudeCodeAdapter
from acc.adapters.mock import MockAdapter
from tests.helpers import chat_state, new_chat, project, send, use, wait_msg


def _event(status, resets):
    return {
        "type": "rate_limit_event",
        "rate_limit_info": {
            "status": status,
            "resetsAt": resets,
            "isUsingOverage": False,
            "unifiedWindows": {
                "five_hour": {"utilization": 1.0, "resetsAt": resets, "status": status}
            },
        },
    }


def test_rejected_window_raises_with_reset_time():
    a = ClaudeCodeAdapter()
    resets = int(time.time()) + 3600
    with pytest.raises(QuotaExceeded) as e:
        a._translate(_event("rejected", resets))
    assert e.value.resets_at == resets
    assert a._blocked_until() == resets


def test_warning_is_not_cooldown():
    a = ClaudeCodeAdapter()
    events = a._translate(_event("allowed_warning", int(time.time()) + 3600))
    assert any("Kota uyarısı" in ev.data.get("text", "") for ev in events)
    assert a._blocked_until() is None


def test_past_reset_is_not_blocking():
    a = ClaudeCodeAdapter()
    with pytest.raises(QuotaExceeded):
        a._translate(_event("rejected", int(time.time()) - 10))
    assert a._blocked_until() is None  # already reset


class _QuotaOnce(MockAdapter):
    """The first turn hits the quota after writing a little; afterwards it works."""

    def __init__(self):
        super().__init__(delay=0.01)
        self.hit = False

    async def run(self, req, run_id):
        if not self.hit and req.tools:
            self.hit = True
            from acc.adapters.base import AdapterEvent

            yield AdapterEvent("delta", {"text": "Başladım"})
            raise QuotaExceeded(int(time.time()) + 1)
        async for ev in super().run(req, run_id):
            yield ev


@pytest.fixture
def quota(monkeypatch):
    monkeypatch.setattr(chat_module, "RESUME_MARGIN_S", 0)
    original = use(_QuotaOnce())
    yield
    registry._adapters = original
    registry._health.clear()


def test_a_turn_waits_for_the_reset_and_continues(client, quota):
    p = project(client)
    chat_id = new_chat(client, p["id"])
    msg_id = send(client, chat_id, "Bir satır ekle", p["id"])
    waiting = wait_msg(client, chat_id, msg_id, "waiting")
    assert waiting["meta"]["resume_at"] and "kotası doldu" in waiting["content"]
    assert waiting["content"].startswith("Başladım")  # what was written is kept
    # A new message while one is waiting is fine; the waiting one continues later.
    done = wait_msg(client, chat_id, msg_id, "done", timeout=15)
    assert "ORBIT_DEMO.md" in done["content"] and done["meta"]["task_id"]


def test_a_waiting_turn_can_be_retried_now(client, quota, monkeypatch):
    monkeypatch.setattr(chat_module, "RESUME_MARGIN_S", 3600)
    chat_id = new_chat(client)
    msg_id = send(client, chat_id, "Selam")
    wait_msg(client, chat_id, msg_id, "waiting")
    assert client.post(f"/api/messages/{msg_id}/resume").status_code == 200
    wait_msg(client, chat_id, msg_id, "done")
    assert client.post(f"/api/messages/{msg_id}/resume").status_code == 409


def test_a_waiting_turn_can_be_stopped(client, quota, monkeypatch):
    monkeypatch.setattr(chat_module, "RESUME_MARGIN_S", 3600)
    chat_id = new_chat(client)
    msg_id = send(client, chat_id, "Selam")
    wait_msg(client, chat_id, msg_id, "waiting")
    assert client.post(f"/api/messages/{msg_id}/cancel").status_code == 200
    m = wait_msg(client, chat_id, msg_id, "cancelled")
    assert m["content"].endswith("_(durduruldu)_")
    assert client.post(f"/api/messages/{msg_id}/resume").status_code == 409
    assert chat_state(client, chat_id)["messages"][-1]["status"] == "cancelled"


async def test_cooldown_blocks_new_runs_until_reset(tmp_path):
    from tests.test_cost_guard import _fake_cli

    cli = _fake_cli(
        tmp_path, {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"}
    )
    a = ClaudeCodeAdapter(binary=cli)
    assert (await a.health_check()).state == ModelState.AVAILABLE
    resets = int(time.time()) + 600
    with pytest.raises(QuotaExceeded):
        a._translate(_event("rejected", resets))
    h = await a.health_check()
    assert h.state == ModelState.COOLDOWN and h.data["resets_at"] == resets
    with pytest.raises(QuotaExceeded) as e:
        [ev async for ev in a.run(RunRequest(prompt="x"), "r")]
    assert e.value.resets_at == resets


def test_notifications_pass_text_as_arguments(monkeypatch):
    import asyncio

    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)

        class P:
            async def wait(self):
                return 0

        return P()

    monkeypatch.setattr(notify, "supported", lambda: True)
    monkeypatch.setattr(notify.prefs, "get", lambda k, d=None: True)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    async def main():
        assert notify.send('Başlık"; do shell script "rm -rf ~', "gövde")
        await asyncio.sleep(0.01)

    asyncio.run(main())
    args = calls[0]
    assert args[0] == "osascript"
    # Title is a separate argv item, never spliced into the AppleScript source.
    assert args[-2] == 'Başlık"; do shell script "rm -rf ~'
    assert all("rm -rf" not in a for a in args[:-2])


def test_notifications_respect_preference(monkeypatch):
    monkeypatch.setattr(notify, "supported", lambda: True)
    monkeypatch.setattr(notify.prefs, "get", lambda k, d=None: False)
    assert notify.send("a", "b") is False
