"""Previewing the web app: build in the sandbox, screenshots from a locked browser."""

import json
import struct
import time
from pathlib import Path

import pytest

from acc import checks, config, preview, sessions
from tests.helpers import decide, git, new_chat, project, task, turn
from tests.test_designs import _top_left_rgb

# No <meta charset>: the text must still arrive as UTF-8 (red = JS ran and "ş" survived).
PAGE = """<!doctype html><html><body style="margin:0;background:#fff"><p id="t">ş</p>
<script>
  const ok = document.getElementById("t").textContent === "\\u015f";
  document.body.style.background = ok ? "rgb(255, 0, 0)" : "rgb(0, 0, 255)";
  console.error("ornek hata");
  fetch("https://example.com/veri").catch(() => {});
</script></body></html>"""

needs_browser = pytest.mark.skipif(not config.CHROMIUM_PATH, reason="Chromium yok")
needs_sandbox = pytest.mark.skipif(not checks.sandbox_available(), reason="srt yok")


def _project_with(client, files: dict[str, str]):
    p = project(client)
    for name, text in files.items():
        f = Path(p["path"]) / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    git(p["path"], "add", "-A")
    git(p["path"], "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "site")
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, "Bir satır ekle", p["id"])["meta"]["task_id"]
    return p, chat_id, task_id


def _preview(client, chat_id, task_id, timeout=120):
    r = client.post(f"/api/tasks/{task_id}/preview")
    assert r.status_code == 202, r.text
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = task(client, chat_id, task_id)["preview"]
        if got and got["status"] != "running":
            return got
        time.sleep(0.2)
    raise AssertionError("önizleme bitmedi")


def test_text_files_are_sent_as_utf8():
    assert preview.content_type(Path("index.html")) == "text/html; charset=utf-8"
    assert preview.content_type(Path("a.js")).endswith("javascript; charset=utf-8")
    assert preview.content_type(Path("logo.png")) == "image/png"


def test_files_are_served_only_from_the_build(tmp_path):
    (tmp_path / "index.html").write_text("x")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "a.js").write_text("y")
    root = tmp_path.resolve()
    o = preview.ORIGIN
    assert preview._local_file(root, f"{o}/assets/a.js?v=1") == root / "assets" / "a.js"
    assert preview._local_file(root, f"{o}/ayarlar") == root / "index.html"  # SPA route
    assert preview._local_file(root, f"{o}/yok.png") is None
    assert preview._local_file(root, f"{o}/../../etc/passwd") is None


@needs_browser
def test_a_static_site_is_shown_with_its_js_and_no_network(client):
    p, chat_id, task_id = _project_with(client, {"index.html": PAGE})
    got = _preview(client, chat_id, task_id)
    assert got["status"] == "ok" and got["build"] is None
    assert "ornek hata" in got["errors"]
    assert any("example.com" in u for u in got["blocked"])  # never left the machine
    shot = preview.folder(task_id) / "phone.png"
    assert struct.unpack(">II", shot.read_bytes()[16:24]) == (393 * 2, 852 * 2)
    assert _top_left_rgb(shot) == (255, 0, 0)
    img = client.get(got["images"]["desktop"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert client.get(f"/api/previews/{task_id}/..%2Fx.png").status_code == 404
    assert not any("ERR_FAILED" in e for e in got["errors"])  # our own aborts aren't errors
    # The next turn sees what the browser complained about, and that the network was off.
    block = sessions.preview_block(task_id)
    assert "ornek hata" in block and "bilerek kapalıydı" in block


@needs_browser
@needs_sandbox
def test_a_built_app_is_built_in_the_sandbox_and_cleaned_away(client):
    pkg = {"name": "x", "scripts": {"build": "mkdir -p dist && cp src/index.html dist/index.html"}}
    p, chat_id, task_id = _project_with(
        client, {"package.json": json.dumps(pkg), "src/index.html": PAGE}
    )
    got = _preview(client, chat_id, task_id)
    assert got["status"] == "ok" and got["build"] == "npm run build"
    wt = sessions.worktree_path(chat_id)
    assert not (wt / "dist").exists()  # the build output never joins the change
    files = [f["path"] for f in client.get(f"/api/tasks/{task_id}/diff").json()["files"]]
    assert files == ["ORBIT_DEMO.md"]


@needs_sandbox
def test_a_failed_build_is_reported_for_fixing(client):
    pkg = {"name": "x", "scripts": {"build": "echo derleme-kirildi && exit 3"}}
    p, chat_id, task_id = _project_with(client, {"package.json": json.dumps(pkg)})
    got = _preview(client, chat_id, task_id)
    assert got["status"] == "build_failed" and "derleme-kirildi" in got["output"]
    assert "ÖNİZLEME DERLEMESİ BAŞARISIZ" in sessions.preview_block(task_id)


def test_not_a_web_project(client):
    p, chat_id, task_id = _project_with(client, {"main.py": "print(1)"})
    assert _preview(client, chat_id, task_id)["status"] == "unsupported"


def test_nothing_touches_the_copy_while_a_preview_runs(client):
    from acc.db import session
    from acc.models import Task

    p, chat_id, task_id = _project_with(client, {"index.html": "<p>x</p>"})
    with session() as s:
        s.get(Task, task_id).preview = {"status": "running"}
    r = client.post(f"/api/chats/{chat_id}/messages", json={"content": "x"})
    assert r.status_code == 409
    assert decide(client, task_id, "approve").status_code == 409
    assert client.post(f"/api/tasks/{task_id}/preview").status_code == 409
    sessions.recover()  # e.g. a restart: the stuck preview no longer blocks the chat
    assert task(client, chat_id, task_id)["preview"]["status"] == "error"


@needs_browser
def test_a_new_change_or_undo_drops_the_old_preview(client):
    p, chat_id, task_id = _project_with(client, {"index.html": PAGE})
    assert _preview(client, chat_id, task_id)["status"] == "ok"
    turn(client, chat_id, "Bir satır daha ekle", p["id"])  # the picture is out of date now
    assert task(client, chat_id, task_id)["preview"] is None
    assert sessions.preview_block(task_id) == ""
    assert _preview(client, chat_id, task_id)["status"] == "ok"
    assert decide(client, task_id, "undo_last").status_code == 200
    assert task(client, chat_id, task_id)["preview"] is None
    assert decide(client, task_id, "reject").status_code == 200
    assert not preview.folder(task_id).exists()  # screenshots go with the copy


def test_a_build_folder_pointing_outside_the_copy_is_refused(client, tmp_path):
    outside = tmp_path / "gizli"
    outside.mkdir()
    (outside / "index.html").write_text("<p>gizli</p>")
    p, chat_id, task_id = _project_with(client, {"index.html": "<p>site</p>"})
    (sessions.worktree_path(chat_id) / "dist").symlink_to(outside)
    got = _preview(client, chat_id, task_id)
    assert got["status"] == "error" and "dışında" in got["reason"]
