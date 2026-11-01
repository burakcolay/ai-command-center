import time
from datetime import timedelta

import pytest

from acc import notify
from acc import orchestrator as orch
from acc.adapters import registry
from acc.adapters.base import ModelState, QuotaExceeded, RunRequest
from acc.adapters.claude_code import ClaudeCodeAdapter
from acc.adapters.mock import MockAdapter
from tests.test_execution import _project, _wait


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
    """First execution step hits the quota; afterwards it works."""

    def __init__(self):
        super().__init__(delay=0.01)
        self.hit = False

    async def _step(self, req, run_id):
        if not self.hit:
            self.hit = True
            raise QuotaExceeded(int(time.time()) + 2)  # resets ~2 s from now
        async for ev in super()._step(req, run_id):
            yield ev


@pytest.fixture
def quota(monkeypatch):
    monkeypatch.setattr(orch, "RESUME_MARGIN", timedelta(seconds=0.3))
    original = registry._adapters
    registry._adapters = {"mock": _QuotaOnce()}
    registry._health.clear()
    yield
    registry._adapters = original


def test_task_pauses_and_resumes_by_itself(client, quota):
    p = _project(client)
    chat = client.post("/api/chats", json={"project_id": p["id"]}).json()
    task_id = client.post(
        f"/api/chats/{chat['id']}/messages", json={"content": "x", "project_id": p["id"]}
    ).json()["task"]["id"]
    _wait(client, chat["id"], task_id, "waiting_approval", "plan")
    client.post(f"/api/tasks/{task_id}/decision", json={"decision": "approve"})
    paused = _wait(client, chat["id"], task_id, "paused")
    assert paused["resume_at"] and paused["error"] is None
    logs = [e["data"].get("text", "") for e in client.get(f"/api/tasks/{task_id}/events").json()]
    assert any("kotası doldu" in t for t in logs)
    # No click needed: it continues after the reset.
    done = _wait(client, chat["id"], task_id, "waiting_approval", "merge", timeout=10)
    assert all(s["status"] == "done" for s in done["steps"])


def test_paused_task_can_be_retried_now(client, quota, monkeypatch):
    monkeypatch.setattr(orch, "RESUME_MARGIN", timedelta(hours=1))
    p = _project(client)
    chat = client.post("/api/chats", json={"project_id": p["id"]}).json()
    task_id = client.post(
        f"/api/chats/{chat['id']}/messages", json={"content": "x", "project_id": p["id"]}
    ).json()["task"]["id"]
    _wait(client, chat["id"], task_id, "waiting_approval", "plan")
    client.post(f"/api/tasks/{task_id}/decision", json={"decision": "approve"})
    _wait(client, chat["id"], task_id, "paused")
    r = client.post(f"/api/tasks/{task_id}/decision", json={"decision": "retry"})
    assert r.status_code == 200
    _wait(client, chat["id"], task_id, "waiting_approval", "merge")


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
