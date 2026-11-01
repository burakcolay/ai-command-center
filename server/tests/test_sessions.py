import time

import pytest

from acc import checks
from acc.adapters import registry
from acc.adapters.mock import MockAdapter
from tests.test_execution import _git, _project, _wait


def _edit(client, chat_id, text, project_id=None):
    r = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": text, "mode": "edit", "project_id": project_id},
    )
    assert r.status_code == 201, r.text
    return r.json()["task"]


def _diff_lines(client, task_id):
    return client.get(f"/api/tasks/{task_id}/diff").json()["patch"].count("+Demo adaptörünün")


def _pending(client, task_id):
    return [a for a in client.get("/api/approvals").json() if a["task_id"] == task_id]


def test_edit_needs_a_project(client):
    chat = client.post("/api/chats", json={}).json()
    r = client.post(f"/api/chats/{chat['id']}/messages", json={"content": "x", "mode": "edit"})
    assert r.status_code == 400


def test_session_applies_edits_immediately_and_accumulates(client):
    p = _project(client)
    chat = client.post("/api/chats", json={"project_id": p["id"]}).json()
    t = _edit(client, chat["id"], "Başlığı büyüt", p["id"])
    assert t["kind"] == "session" and t["plan"] is None
    t = _wait(client, chat["id"], t["id"], "waiting_approval", "merge")  # no plan approval
    assert [s["kind"] for s in t["steps"]] == ["edit"]
    assert _diff_lines(client, t["id"]) == 1

    t2 = _edit(client, chat["id"], "Rengi koyulaştır")
    assert t2["id"] == t["id"]  # same session
    time.sleep(0.05)
    t2 = _wait(client, chat["id"], t["id"], "waiting_approval", "merge")
    assert len(t2["steps"]) == 2 and all(s["status"] == "done" for s in t2["steps"])
    assert _diff_lines(client, t["id"]) == 2
    assert len(_pending(client, t["id"])) == 1  # superseded review, not duplicated


def test_undo_last_then_merge_then_new_session(client):
    p = _project(client)
    chat = client.post("/api/chats", json={"project_id": p["id"]}).json()
    t = _edit(client, chat["id"], "Bir", p["id"])
    _wait(client, chat["id"], t["id"], "waiting_approval", "merge")
    _edit(client, chat["id"], "İki")
    time.sleep(0.05)
    t = _wait(client, chat["id"], t["id"], "waiting_approval", "merge")
    assert _diff_lines(client, t["id"]) == 2

    r = client.post(f"/api/tasks/{t['id']}/decision", json={"decision": "undo_last"})
    assert r.status_code == 200, r.text
    time.sleep(0.05)
    t = _wait(client, chat["id"], t["id"], "waiting_approval", "merge")
    assert [s["status"] for s in t["steps"]] == ["done", "reverted"]
    assert _diff_lines(client, t["id"]) == 1

    # A retry must never bring a reverted edit back; a new edit runs only itself.
    _edit(client, chat["id"], "Üç")
    time.sleep(0.05)
    t = _wait(client, chat["id"], t["id"], "waiting_approval", "merge")
    assert [s["status"] for s in t["steps"]] == ["done", "reverted", "done"]
    assert _diff_lines(client, t["id"]) == 2

    assert (
        client.post(f"/api/tasks/{t['id']}/decision", json={"decision": "approve"}).status_code
        == 200
    )
    _wait(client, chat["id"], t["id"], "completed")
    assert _git(p["path"], "show", "HEAD:ORBIT_DEMO.md").count("Demo adaptörünün") == 2

    nxt = _edit(client, chat["id"], "Dört")
    assert nxt["id"] != t["id"]  # merged session is closed; a new one starts
    _wait(client, chat["id"], nxt["id"], "waiting_approval", "merge")


def test_undo_everything_keeps_session_open(client):
    p = _project(client)
    chat = client.post("/api/chats", json={"project_id": p["id"]}).json()
    t = _edit(client, chat["id"], "Tek", p["id"])
    _wait(client, chat["id"], t["id"], "waiting_approval", "merge")
    client.post(f"/api/tasks/{t['id']}/decision", json={"decision": "undo_last"})
    time.sleep(0.05)
    t = _wait(client, chat["id"], t["id"], "waiting_approval", "merge")
    assert client.get(f"/api/tasks/{t['id']}/diff").json()["files"] == []
    r = client.post(f"/api/tasks/{t['id']}/decision", json={"decision": "undo_last"})
    assert r.status_code == 409  # nothing left to undo


@pytest.fixture
def slow():
    original = registry._adapters
    registry._adapters = {"mock": MockAdapter(delay=0.4)}
    yield
    registry._adapters = original


def test_edit_sent_while_running_is_picked_up(client, slow):
    p = _project(client)
    chat = client.post("/api/chats", json={"project_id": p["id"]}).json()
    t = _edit(client, chat["id"], "Bir", p["id"])
    time.sleep(0.1)
    _edit(client, chat["id"], "İki")  # arrives while the first one runs
    t = _wait(client, chat["id"], t["id"], "waiting_approval", "merge", timeout=10)
    assert [s["status"] for s in t["steps"]] == ["done", "done"]
    assert _diff_lines(client, t["id"]) == 2


def test_reject_session_discards_everything(client):
    p = _project(client)
    chat = client.post("/api/chats", json={"project_id": p["id"]}).json()
    t = _edit(client, chat["id"], "Bir", p["id"])
    _wait(client, chat["id"], t["id"], "waiting_approval", "merge")
    client.post(f"/api/tasks/{t['id']}/decision", json={"decision": "reject"})
    _wait(client, chat["id"], t["id"], "cancelled")
    assert f"orbit/task-{t['id']}" not in _git(p["path"], "branch")


@pytest.mark.skipif(not checks.sandbox_available(), reason="sandbox-runtime not installed")
def test_setup_runs_once_per_session(client):
    p = _project(client)
    r = client.put(
        f"/api/projects/{p['id']}/checks",
        json={
            "config": {
                "setup": "echo x >> .orbit-cache/setup-count",
                "commands": [
                    {
                        "name": "kurulum sayısı",
                        "command": "test $(wc -l < .orbit-cache/setup-count) -eq 1",
                    }
                ],
            }
        },
    )
    assert r.status_code == 200
    chat = client.post("/api/chats", json={"project_id": p["id"]}).json()
    t = _edit(client, chat["id"], "Bir", p["id"])
    t = _wait(client, chat["id"], t["id"], "waiting_approval", "merge")
    assert t["checks"][-1]["status"] == "passed"
    _edit(client, chat["id"], "İki")
    time.sleep(0.05)
    t = _wait(client, chat["id"], t["id"], "waiting_approval", "merge")
    assert [c["name"] for c in t["checks"]] == ["kurulum sayısı"]  # setup skipped: cached
    assert t["checks"][0]["status"] == "passed"
