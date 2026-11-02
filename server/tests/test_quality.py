import json
from pathlib import Path

import pytest

from acc import checks, config
from tests.helpers import decide, new_chat, project, task, turn


def _to_review(client, p, text="Bir satır ekle"):
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, text, p["id"])["meta"]["task_id"]
    return chat_id, task_id, task(client, chat_id, task_id)


def test_detect_npm(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run", "lint": "eslint .", "dev": "vite"}})
    )
    (tmp_path / "package-lock.json").write_text("{}")
    d = checks.detect(tmp_path)
    assert d["setup"] == "npm ci"
    assert [c["command"] for c in d["commands"]] == ["npm run lint", "npm run test"]


def test_detect_ignores_npm_placeholder_test(tmp_path: Path):
    placeholder = 'echo "Error: no test specified" && exit 1'
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": placeholder}}))
    assert checks.detect(tmp_path)["commands"] == []


def test_detect_python_uv(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length=100\n")
    (tmp_path / "uv.lock").write_text("")
    (tmp_path / "tests").mkdir()
    d = checks.detect(tmp_path)
    assert d["setup"] == "uv sync"
    assert [c["name"] for c in d["commands"]] == ["pytest", "ruff"]


def test_detect_nothing(tmp_path: Path):
    assert checks.detect(tmp_path) == {"setup": None, "commands": []}


def _configure(client, project_id, commands, setup=None):
    r = client.put(
        f"/api/projects/{project_id}/checks",
        json={"config": {"setup": setup, "commands": commands}},
    )
    assert r.status_code == 200, r.text
    return r.json()


needs_sandbox = pytest.mark.skipif(
    not checks.sandbox_available(), reason="sandbox-runtime not installed (make setup)"
)


@needs_sandbox
def test_checks_run_in_sandbox_and_show_in_review(client):
    p = project(client)
    escape = Path.home() / "orbit-check-escape.txt"
    tmp_escape = Path("/tmp/orbit-check-escape.txt")
    tmp_escape.unlink(missing_ok=True)
    escape.unlink(missing_ok=True)
    _configure(
        client,
        p["id"],
        [
            {"name": "geçen", "command": "test -f ORBIT_DEMO.md && echo tamam"},
            {"name": "kaçış denemesi", "command": f"echo x > {escape}"},
            {"name": "tmp denemesi", "command": f"echo x > {tmp_escape}"},
            {"name": "geçici dosya", "command": 'python3 -c "import tempfile; tempfile.mkstemp()"'},
        ],
    )
    _, task_id, t = _to_review(client, p)
    by_name = {r["name"]: r for r in t["checks"]}
    assert by_name["geçen"]["status"] == "passed" and "tamam" in by_name["geçen"]["output"]
    assert by_name["kaçış denemesi"]["status"] == "failed"
    assert by_name["tmp denemesi"]["status"] == "failed"
    assert not escape.exists() and not tmp_escape.exists(), "a check wrote outside its worktree"
    # Normal temp-file use still works, via the private TMPDIR.
    assert by_name["geçici dosya"]["status"] == "passed", by_name["geçici dosya"]["output"]


@needs_sandbox
def test_failed_checks_reach_the_next_turn(client, rec):
    p = project(client)
    # Fails until the demo assistant has written the file twice.
    _configure(
        client,
        p["id"],
        [{"name": "iki satır", "command": "test $(grep -c Demo ORBIT_DEMO.md) -ge 2"}],
    )
    chat_id, task_id, t = _to_review(client, p)
    assert t["checks"][0]["status"] == "failed"
    # "Fix it" is just another message; the assistant is shown what failed.
    turn(client, chat_id, "Kontrolleri düzelt, bir satır daha ekle")
    assert "BAŞARISIZ KONTROLLER" in rec.requests[-1].prompt
    assert "iki satır" in rec.requests[-1].prompt
    assert task(client, chat_id, task_id)["checks"][0]["status"] == "passed"
    turn(client, chat_id, "Teşekkürler")
    assert "BAŞARISIZ KONTROLLER" not in rec.requests[-1].prompt


def test_without_sandbox_nothing_runs(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SRT_BIN", tmp_path / "yok" / "srt")
    p = project(client)
    marker = tmp_path / "ran.txt"
    _configure(client, p["id"], [{"name": "yaz", "command": f"echo x > {marker}"}])
    _, _, t = _to_review(client, p)
    assert t["checks"][0]["status"] == "skipped"
    assert not marker.exists()


def test_checks_config_endpoint(client):
    p = project(client)
    info = client.get(f"/api/projects/{p['id']}/checks").json()
    assert info["configured"] is None and info["effective"] == info["detected"]
    _configure(client, p["id"], [{"name": "a", "command": "true"}], setup="  ")
    info = client.get(f"/api/projects/{p['id']}/checks").json()
    assert info["configured"] == {"setup": None, "commands": [{"name": "a", "command": "true"}]}
    client.put(f"/api/projects/{p['id']}/checks", json={"config": None})
    assert client.get(f"/api/projects/{p['id']}/checks").json()["configured"] is None
    bad = client.put(
        f"/api/projects/{p['id']}/checks", json={"config": {"commands": [{"name": ""}]}}
    )
    assert bad.status_code == 422


def test_review_has_no_checks_when_none_defined(client):
    p = project(client)
    _, _, t = _to_review(client, p)
    assert t["checks"] == []


@needs_sandbox
def test_checks_work_with_long_worktree_paths(client, monkeypatch, tmp_path):
    """Real installs have long paths; srt's own unix sockets must not live under them."""
    deep = tmp_path.joinpath(*["uzun-bir-klasor-adi"] * 6, "worktrees")
    monkeypatch.setattr(config, "WORKTREES_DIR", deep)
    p = project(client)
    _configure(
        client,
        p["id"],
        [{"name": "tmp", "command": 'python3 -c "import tempfile; tempfile.mkstemp()"'}],
    )
    _, _, t = _to_review(client, p)
    assert len(str(deep)) > 120
    assert t["checks"][0]["status"] == "passed", t["checks"][0]["output"]


@needs_sandbox
def test_rerun_checks_without_a_new_turn(client):
    p = project(client)
    _configure(client, p["id"], [{"name": "işaret", "command": "test -f HAZIR"}])
    chat_id, task_id, t = _to_review(client, p)
    assert t["checks"][0]["status"] == "failed"
    # Fix the check itself (not the code), then run the checks again: no new steps.
    _configure(client, p["id"], [{"name": "işaret", "command": "test -f ORBIT_DEMO.md"}])
    steps_before = len(t["steps"])
    assert decide(client, task_id, "rerun_checks").status_code == 200
    t = task(client, chat_id, task_id)
    assert t["status"] == "waiting_approval" and t["checks"][0]["status"] == "passed"
    assert len(t["steps"]) == steps_before
    pending = [a for a in client.get("/api/approvals").json() if a["task_id"] == task_id]
    assert len(pending) == 1  # the old review approval was superseded, not duplicated
