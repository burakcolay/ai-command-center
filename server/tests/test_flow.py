import time

from acc.orchestrator import validate_plan


def _wait_status(client, chat_id, task_id, status, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        tasks = {t["id"]: t for t in client.get(f"/api/chats/{chat_id}").json()["tasks"]}
        if tasks[task_id]["status"] == status:
            return tasks[task_id]
        time.sleep(0.02)
    raise AssertionError(f"task {task_id} never reached {status}: {tasks[task_id]}")


def _new_task(client, text="Giriş ekranını iyileştir"):
    chat = client.post("/api/chats", json={}).json()
    r = client.post(f"/api/chats/{chat['id']}/messages", json={"content": text})
    assert r.status_code == 201
    return chat["id"], r.json()["task"]["id"]


def test_rejects_non_localhost_host():
    from fastapi.testclient import TestClient

    from acc.main import app

    with TestClient(app, base_url="http://evil.example") as c:
        assert c.get("/api/projects").status_code == 403


def test_create_project_in_workspace(client):
    r = client.post("/api/projects", json={"name": "Deneme Proje"})
    assert r.status_code == 201, r.text
    assert r.json()["path"].endswith("deneme-proje")
    assert client.post("/api/projects", json={"name": "Deneme Proje"}).status_code == 409
    assert client.post("/api/projects", json={"name": "x", "path": "/yok/boyle"}).status_code == 400


def test_plan_approve_flow(client):
    chat_id, task_id = _new_task(client)
    task = _wait_status(client, chat_id, task_id, "waiting_approval")
    assert len(task["plan"]["steps"]) == 3
    pending = client.get("/api/approvals").json()
    assert any(a["task_id"] == task_id for a in pending)

    r = client.post(f"/api/tasks/{task_id}/decision", json={"decision": "approve"})
    assert r.status_code == 200 and r.json()["status"] == "queued"
    assert not any(a["task_id"] == task_id for a in client.get("/api/approvals").json())
    # approving twice is not a valid transition
    r = client.post(f"/api/tasks/{task_id}/decision", json={"decision": "approve"})
    assert r.status_code == 409
    kinds = [e["kind"] for e in client.get(f"/api/tasks/{task_id}/events").json()]
    assert "tool" in kinds and "log" in kinds


def test_request_changes_replans_and_needs_note(client):
    chat_id, task_id = _new_task(client)
    _wait_status(client, chat_id, task_id, "waiting_approval")
    r = client.post(f"/api/tasks/{task_id}/decision", json={"decision": "request_changes"})
    assert r.status_code == 409
    r = client.post(
        f"/api/tasks/{task_id}/decision",
        json={"decision": "request_changes", "note": "Testleri ilk adıma al"},
    )
    assert r.json()["status"] == "planning"
    _wait_status(client, chat_id, task_id, "waiting_approval")


def test_reject_and_cancel(client):
    chat_id, task_id = _new_task(client)
    _wait_status(client, chat_id, task_id, "waiting_approval")
    r = client.post(f"/api/tasks/{task_id}/decision", json={"decision": "reject"})
    assert r.json()["status"] == "cancelled"
    r = client.post(f"/api/tasks/{task_id}/decision", json={"decision": "cancel"})
    assert r.status_code == 409


def test_validate_plan():
    good = {
        "title": "t",
        "steps": [
            {"id": "a", "agent": "developer", "depends_on": []},
            {"id": "b", "agent": "qa", "depends_on": ["a"]},
        ],
    }
    assert validate_plan(good) is None
    assert validate_plan(None)
    assert validate_plan({**good, "steps": [{"id": "a", "agent": "hacker", "depends_on": []}]})
    assert validate_plan({**good, "steps": [{"id": "a", "agent": "qa", "depends_on": ["z"]}]})
