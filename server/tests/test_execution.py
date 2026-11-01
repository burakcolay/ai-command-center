import subprocess
import time
from pathlib import Path

import pytest

from acc import config
from acc.adapters import registry
from acc.adapters.base import AdapterEvent
from acc.adapters.mock import MockAdapter


def _git(cwd, *args) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _wait(client, chat_id, task_id, status, stage=None, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = next(
            x for x in client.get(f"/api/chats/{chat_id}").json()["tasks"] if x["id"] == task_id
        )
        if t["status"] == status and (stage is None or t["stage"] == stage):
            return t
        time.sleep(0.02)
    raise AssertionError(f"task {task_id} never reached {status}/{stage}: {t}")


_n = 0


def _project(client) -> dict:
    global _n
    _n += 1
    r = client.post("/api/projects", json={"name": f"Exec Proje {_n}"})
    assert r.status_code == 201, r.text
    return r.json()


def _to_review(client, project):
    chat = client.post("/api/chats", json={"project_id": project["id"]}).json()
    r = client.post(
        f"/api/chats/{chat['id']}/messages",
        json={"content": "Demo dosyası ekle", "project_id": project["id"]},
    )
    task_id = r.json()["task"]["id"]
    _wait(client, chat["id"], task_id, "waiting_approval", "plan")
    assert (
        client.post(f"/api/tasks/{task_id}/decision", json={"decision": "approve"}).status_code
        == 200
    )
    task = _wait(client, chat["id"], task_id, "waiting_approval", "merge")
    return chat["id"], task_id, task


def test_new_project_has_initial_commit(client):
    p = _project(client)
    assert _git(p["path"], "log", "--oneline")


def test_execute_review_merge(client):
    p = _project(client)
    chat_id, task_id, task = _to_review(client, p)

    assert task["branch"] == f"orbit/task-{task_id}"
    assert [s["status"] for s in task["steps"]] == ["done", "done", "done"]
    assert task["steps"][1]["commit"]  # developer step committed
    # The user's working tree is untouched until merge.
    assert not (Path(p["path"]) / "ORBIT_DEMO.md").exists()

    d = client.get(f"/api/tasks/{task_id}/diff").json()
    assert [f["path"] for f in d["files"]] == ["ORBIT_DEMO.md"]
    assert "+Demo adaptörünün yazdığı satır." in d["patch"]

    r = client.post(f"/api/tasks/{task_id}/decision", json={"decision": "approve"})
    assert r.status_code == 200, r.text
    done = _wait(client, chat_id, task_id, "completed")
    assert done["merged_commit"] and done["stage"] == "done"
    assert (Path(p["path"]) / "ORBIT_DEMO.md").exists()
    # Worktree and branch are cleaned up after merge.
    assert not (config.WORKTREES_DIR / f"task-{task_id}").exists()
    assert f"orbit/task-{task_id}" not in _git(p["path"], "branch")


def test_request_changes_adds_revision(client):
    p = _project(client)
    chat_id, task_id, _ = _to_review(client, p)
    r = client.post(
        f"/api/tasks/{task_id}/decision",
        json={"decision": "request_changes", "note": "Bir satır daha ekle"},
    )
    assert r.status_code == 200
    task = _wait(client, chat_id, task_id, "waiting_approval", "merge")
    assert task["steps"][-1]["kind"] == "revision" and task["steps"][-1]["status"] == "done"
    patch = client.get(f"/api/tasks/{task_id}/diff").json()["patch"]
    assert patch.count("+Demo adaptörünün yazdığı satır.") == 2


def test_reject_removes_worktree_and_branch(client):
    p = _project(client)
    chat_id, task_id, _ = _to_review(client, p)
    client.post(f"/api/tasks/{task_id}/decision", json={"decision": "reject"})
    _wait(client, chat_id, task_id, "cancelled")
    assert not (config.WORKTREES_DIR / f"task-{task_id}").exists()
    assert f"orbit/task-{task_id}" not in _git(p["path"], "branch")
    assert not (Path(p["path"]) / "ORBIT_DEMO.md").exists()


def test_merge_refused_on_wrong_branch(client):
    p = _project(client)
    chat_id, task_id, _ = _to_review(client, p)
    _git(p["path"], "checkout", "-q", "-b", "baska-branch")
    r = client.post(f"/api/tasks/{task_id}/decision", json={"decision": "approve"})
    assert r.status_code == 409 and "main" in r.json()["detail"]
    # Nothing changed: still waiting, approval still pending.
    assert _wait(client, chat_id, task_id, "waiting_approval", "merge")
    assert any(a["task_id"] == task_id for a in client.get("/api/approvals").json())
    _git(p["path"], "checkout", "-q", "main")
    assert (
        client.post(f"/api/tasks/{task_id}/decision", json={"decision": "approve"}).status_code
        == 200
    )


def test_execution_without_project_fails_cleanly(client):
    chat = client.post("/api/chats", json={}).json()
    task_id = client.post(f"/api/chats/{chat['id']}/messages", json={"content": "x"}).json()[
        "task"
    ]["id"]
    _wait(client, chat["id"], task_id, "waiting_approval")
    client.post(f"/api/tasks/{task_id}/decision", json={"decision": "approve"})
    t = _wait(client, chat["id"], task_id, "failed")
    assert "projesi olmalı" in t["error"]


class _SneakyReadOnly(MockAdapter):
    """Writes a file even when it has no write tools — must be reverted by Orbit."""

    async def _step(self, req, run_id):
        if req.cwd and "Write" not in (req.tools or []):
            (req.cwd / "sizinti.txt").write_text("olmamalı")
            yield AdapterEvent("result", {"text": "yazdım"})
            return
        async for ev in super()._step(req, run_id):
            yield ev


@pytest.fixture
def sneaky():
    original = registry._adapters
    registry._adapters = {"mock": _SneakyReadOnly(delay=0.01)}
    yield
    registry._adapters = original


def test_read_only_agent_changes_are_reverted(client, sneaky):
    p = _project(client)
    chat_id, task_id, _ = _to_review(client, p)
    files = [f["path"] for f in client.get(f"/api/tasks/{task_id}/diff").json()["files"]]
    assert files == ["ORBIT_DEMO.md"]
    logs = [e["data"].get("text", "") for e in client.get(f"/api/tasks/{task_id}/events").json()]
    assert any("geri alındı" in t for t in logs)


class _JunkWriter(MockAdapter):
    """Simulates running tests: every step leaves cache files behind."""

    async def _step(self, req, run_id):
        if req.cwd:
            (req.cwd / "__pycache__").mkdir(exist_ok=True)
            (req.cwd / "__pycache__" / "x.cpython-313.pyc").write_bytes(b"\0")
            (req.cwd / "pkg" / "node_modules").mkdir(parents=True, exist_ok=True)
            (req.cwd / "pkg" / "node_modules" / "a.js").write_text("x")
        async for ev in super()._step(req, run_id):
            yield ev


@pytest.fixture
def junk():
    original = registry._adapters
    registry._adapters = {"mock": _JunkWriter(delay=0.01)}
    yield
    registry._adapters = original


def test_build_junk_is_never_committed(client, junk):
    p = _project(client)
    _, task_id, _ = _to_review(client, p)
    files = [f["path"] for f in client.get(f"/api/tasks/{task_id}/diff").json()["files"]]
    assert files == ["ORBIT_DEMO.md"]
    logs = [e["data"].get("text", "") for e in client.get(f"/api/tasks/{task_id}/events").json()]
    assert not any("geri alındı" in t for t in logs)  # caches are not a read-only violation
