"""Sending a chat's changes to GitHub as a pull request, against a local stand-in for GitHub:
a bare repository behind a github.com URL (git's insteadOf) and a fake `gh`."""

import subprocess
from pathlib import Path

import pytest

from acc import github
from tests.helpers import decide, git, new_chat, project, turn

FAKE_GH = """#!/bin/sh
echo "$@" >> "{log}"
case "$1 $2" in
  "auth status") exit {auth} ;;
  "pr create") echo "https://github.com/test/demo/pull/7" ;;
esac
"""


@pytest.fixture
def fake_github(tmp_path, monkeypatch):
    def make(auth_ok=True):
        log = tmp_path / "gh.log"
        gh = tmp_path / "gh"
        gh.write_text(FAKE_GH.format(log=log, auth=0 if auth_ok else 1))
        gh.chmod(0o755)
        monkeypatch.setattr(github, "GH", str(gh))
        return log

    return make


def _on_github(client, tmp_path) -> tuple[dict, Path]:
    p = project(client)
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    url = "https://github.com/test/demo.git"
    git(p["path"], "remote", "add", "origin", url)
    git(p["path"], "config", f"url.{bare}.insteadOf", url)
    git(p["path"], "push", "-q", "origin", "main")
    return p, bare


def test_remote_urls():
    assert github.parse_remote("https://github.com/burak/orbit.git") == "burak/orbit"
    assert github.parse_remote("git@github.com:burak/orbit.git\n") == "burak/orbit"
    assert github.parse_remote("https://github.com/burak/my.app") == "burak/my.app"
    assert github.parse_remote("https://gitlab.com/burak/orbit.git") is None


def test_open_pr_pushes_orbits_branch_and_updates_it_later(client, tmp_path, fake_github):
    log = fake_github()
    p, bare = _on_github(client, tmp_path)
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, "Karşılama satırı ekle", p["id"])["meta"]["task_id"]
    assert client.get(f"/api/tasks/{task_id}/github").json() == {
        "repo": "test/demo",
        "ready": True,
        "reason": "",
    }

    r = decide(client, task_id, "open_pr")
    assert r.status_code == 200, r.text
    assert r.json()["pr_url"] == "https://github.com/test/demo/pull/7"
    branch = f"orbit/task-{task_id}"
    assert git(bare, "rev-parse", branch) == git(p["path"], "rev-parse", branch)
    created = [line for line in log.read_text().splitlines() if line.startswith("pr create")]
    assert len(created) == 1
    assert f"--base main --head {branch}" in created[0] and "--repo test/demo" in created[0]
    assert "--title Karşılama satırı ekle" in created[0]
    # The user's own branch and project are untouched; nothing merged locally.
    assert not (Path(p["path"]) / "ORBIT_DEMO.md").exists()

    # Undo rewrites the branch; the next send force-pushes and reuses the same PR.
    turn(client, chat_id, "Bir satır daha ekle")
    decide(client, task_id, "undo_last")
    turn(client, chat_id, "Başka bir satır ekle")
    assert decide(client, task_id, "open_pr").status_code == 200
    assert git(bare, "rev-parse", branch) == git(p["path"], "rev-parse", branch)
    assert sum(line.startswith("pr create") for line in log.read_text().splitlines()) == 1


def test_not_logged_in_is_explained(client, tmp_path, fake_github):
    fake_github(auth_ok=False)
    p, bare = _on_github(client, tmp_path)
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, "Bir satır ekle", p["id"])["meta"]["task_id"]
    status = client.get(f"/api/tasks/{task_id}/github").json()
    assert status["ready"] is False and "gh auth login" in status["reason"]
    r = decide(client, task_id, "open_pr")
    assert r.status_code == 409 and "gh auth login" in r.json()["detail"]
    assert "orbit/" not in git(bare, "branch")  # nothing was pushed


def test_projects_without_github_get_no_pr(client, fake_github):
    fake_github()
    p = project(client)
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, "Bir satır ekle", p["id"])["meta"]["task_id"]
    assert client.get(f"/api/tasks/{task_id}/github").json()["repo"] is None
    assert decide(client, task_id, "open_pr").status_code == 409
