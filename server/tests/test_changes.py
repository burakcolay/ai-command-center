"""Changes asked for in chat: an isolated copy, one commit per turn, review, merge or discard."""

import time
from pathlib import Path

from acc import assistant, config
from acc.adapters.mock import MockAdapter
from tests.helpers import (  # noqa: F401
    chat_state,
    decide,
    diff_lines,
    git,
    new_chat,
    project,
    send,
    task,
    turn,
    use,
    wait_msg,
)


def _pending(client, task_id):
    return [a for a in client.get("/api/approvals").json() if a["task_id"] == task_id]


def _events(client, task_id):
    return [e["data"].get("text", "") for e in client.get(f"/api/tasks/{task_id}/events").json()]


def test_new_project_has_initial_commit(client):
    assert git(project(client)["path"], "log", "--oneline")


def test_an_edit_lands_in_an_isolated_copy_for_review(client, rec):
    p = project(client)
    chat_id = new_chat(client, p["id"])
    m = turn(client, chat_id, "Başlığa bir satır ekle", p["id"])
    task_id = m["meta"]["task_id"]
    req = rec.requests[-1]
    assert req.tools == [*assistant.PROJECT_TOOLS, "Agent"] and req.settings["sandbox"]["enabled"]
    assert set(req.agents) == {"kesifci", "arastirmaci", "tasarimci", "test-yazari", "inceleyici"}
    assert req.cwd == config.WORKTREES_DIR / f"chat-{chat_id}"
    assert "ÇALIŞMA KOPYASI" in req.prompt

    t = task(client, chat_id, task_id)
    assert t["status"] == "waiting_approval" and t["stage"] == "merge"
    assert t["branch"] == f"orbit/task-{task_id}"
    assert [s["kind"] for s in t["steps"]] == ["edit"] and t["steps"][0]["commit"]
    assert not (Path(p["path"]) / "ORBIT_DEMO.md").exists()  # the real project is untouched
    d = client.get(f"/api/tasks/{task_id}/diff").json()
    assert [f["path"] for f in d["files"]] == ["ORBIT_DEMO.md"]
    assert len(_pending(client, task_id)) == 1


def test_talking_about_a_project_changes_nothing(client, rec):
    p = project(client)
    chat_id = new_chat(client, p["id"])
    m = turn(client, chat_id, "Bu proje ne işe yarıyor?", p["id"])
    assert "task_id" not in (m["meta"] or {})
    tasks = chat_state(client, chat_id)["tasks"]
    assert all(not t["steps"] for t in tasks)
    assert all(_pending(client, t["id"]) == [] for t in tasks)


def test_turns_accumulate_in_one_session_until_merged(client):
    p = project(client)
    chat_id = new_chat(client, p["id"])
    first = turn(client, chat_id, "Bir satır ekle", p["id"])["meta"]["task_id"]
    second = turn(client, chat_id, "Bir satır daha ekle")["meta"]["task_id"]
    assert first == second
    t = task(client, chat_id, first)
    assert len(t["steps"]) == 2 and all(s["status"] == "done" for s in t["steps"])
    assert diff_lines(client, first) == 2
    assert len(_pending(client, first)) == 1  # the review is replaced, not duplicated

    assert decide(client, first, "approve").status_code == 200
    done = task(client, chat_id, first)
    assert done["status"] == "completed" and done["merged_commit"]
    assert (Path(p["path"]) / "ORBIT_DEMO.md").read_text().count("Demo adaptörünün") == 2
    assert f"orbit/task-{first}" not in git(p["path"], "branch")
    assert _pending(client, first) == []

    # The next change starts a fresh session on top of the merged work.
    third = turn(client, chat_id, "Bir satır daha ekle")["meta"]["task_id"]
    assert third != first and diff_lines(client, third) == 1


def test_undo_last_change(client):
    p = project(client)
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, "Bir ekle", p["id"])["meta"]["task_id"]
    turn(client, chat_id, "İki ekle")
    assert diff_lines(client, task_id) == 2
    assert decide(client, task_id, "undo_last").status_code == 200
    t = task(client, chat_id, task_id)
    assert [s["status"] for s in t["steps"]] == ["done", "reverted"]
    assert diff_lines(client, task_id) == 1
    assert decide(client, task_id, "undo_last").status_code == 200
    assert client.get(f"/api/tasks/{task_id}/diff").json()["files"] == []
    assert _pending(client, task_id) == []  # nothing left to merge
    r = decide(client, task_id, "undo_last")
    assert r.status_code == 409
    # The chat keeps going in the same session.
    assert turn(client, chat_id, "Yine ekle")["meta"]["task_id"] == task_id
    assert diff_lines(client, task_id) == 1


def test_discard_everything(client):
    p = project(client)
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, "Bir satır ekle", p["id"])["meta"]["task_id"]
    assert decide(client, task_id, "reject").status_code == 200
    assert task(client, chat_id, task_id)["status"] == "cancelled"
    assert not (config.WORKTREES_DIR / f"chat-{chat_id}").exists()
    assert f"orbit/task-{task_id}" not in git(p["path"], "branch")
    assert not (Path(p["path"]) / "ORBIT_DEMO.md").exists()


def test_no_decisions_while_the_assistant_works(client, slow):
    p = project(client)
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, "Bir satır ekle", p["id"])["meta"]["task_id"]
    msg_id = send(client, chat_id, "Bir satır daha ekle")
    time.sleep(0.2)
    assert decide(client, task_id, "approve").status_code == 409
    wait_msg(client, chat_id, msg_id)
    assert decide(client, task_id, "approve").status_code == 200


def test_merge_refused_on_wrong_branch(client):
    p = project(client)
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, "Bir satır ekle", p["id"])["meta"]["task_id"]
    git(p["path"], "checkout", "-q", "-b", "baska-branch")
    r = decide(client, task_id, "approve")
    assert r.status_code == 409 and "main" in r.json()["detail"]
    assert task(client, chat_id, task_id)["status"] == "waiting_approval"
    assert len(_pending(client, task_id)) == 1
    git(p["path"], "checkout", "-q", "main")
    assert decide(client, task_id, "approve").status_code == 200


def test_switching_project_needs_open_changes_settled(client):
    a, b = project(client), project(client)
    chat_id = new_chat(client, a["id"])
    turn(client, chat_id, "Merhaba", a["id"])  # only talk: an empty session
    turn(client, chat_id, "Merhaba", b["id"])  # so switching is fine
    assert chat_state(client, chat_id)["chat"]["project_id"] == b["id"]
    task_id = turn(client, chat_id, "Bir satır ekle")["meta"]["task_id"]
    r = client.post(f"/api/chats/{chat_id}/messages", json={"content": "x", "project_id": a["id"]})
    assert r.status_code == 409
    decide(client, task_id, "reject")
    turn(client, chat_id, "Merhaba", a["id"])


def test_deleting_a_chat_removes_its_copy_but_never_the_project(client):
    p = project(client)
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, "Bir satır ekle", p["id"])["meta"]["task_id"]
    wt = config.WORKTREES_DIR / f"chat-{chat_id}"
    assert wt.is_dir()
    assert client.delete(f"/api/chats/{chat_id}").status_code == 204
    assert not wt.exists()
    assert f"orbit/task-{task_id}" not in git(p["path"], "branch")
    assert Path(p["path"]).is_dir() and git(p["path"], "log", "--oneline")


def test_a_folder_without_git_is_opened_read_only(client, rec, tmp_path):
    folder = tmp_path / "gitsiz"
    folder.mkdir()
    (folder / "notlar.txt").write_text("merhaba")
    r = client.post("/api/projects", json={"name": "Gitsiz", "path": str(folder)})
    assert r.status_code == 201, r.text
    chat_id = new_chat(client, r.json()["id"])
    m = turn(client, chat_id, "Bir satır ekle", r.json()["id"])
    req = rec.requests[-1]
    assert req.tools == [*assistant.READ_ONLY_TOOLS, "Agent"] and req.cwd == folder
    # no subagent gets more than the lead has: only the read-only ones
    assert set(req.agents) == {"kesifci", "arastirmaci"}
    assert "salt okunur" in req.prompt and "git init" in req.prompt
    assert "task_id" not in (m["meta"] or {})
    assert not (folder / "ORBIT_DEMO.md").exists()


class _JunkWriter(MockAdapter):
    """Simulates running tests: every turn leaves cache files behind."""

    async def run(self, req, run_id):
        if req.cwd and "Write" in req.tools:
            (req.cwd / "__pycache__").mkdir(exist_ok=True)
            (req.cwd / "__pycache__" / "x.cpython-313.pyc").write_bytes(b"\0")
            (req.cwd / "pkg" / "node_modules").mkdir(parents=True, exist_ok=True)
            (req.cwd / "pkg" / "node_modules" / "a.js").write_text("x")
        async for ev in super().run(req, run_id):
            yield ev


def test_build_junk_is_never_committed(client):
    from acc.adapters import registry

    original = use(_JunkWriter(delay=0.01))
    try:
        p = project(client)
        chat_id = new_chat(client, p["id"])
        task_id = turn(client, chat_id, "Bir satır ekle", p["id"])["meta"]["task_id"]
        files = [f["path"] for f in client.get(f"/api/tasks/{task_id}/diff").json()["files"]]
        assert files == ["ORBIT_DEMO.md"]
    finally:
        registry._adapters = original
        registry._health.clear()


def test_restart_puts_running_sessions_back_up_for_review(client):
    from acc import sessions
    from acc.db import session
    from acc.models import Task, TaskStatus

    p = project(client)
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, "Bir satır ekle", p["id"])["meta"]["task_id"]
    with session() as s:
        s.get(Task, task_id).status = TaskStatus.RUNNING
    sessions.recover()
    assert task(client, chat_id, task_id)["status"] == "waiting_approval"
