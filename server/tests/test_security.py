import json
import stat

from acc import assistant, config, security
from acc.adapters.base import RunRequest
from acc.adapters.claude_code import ClaudeCodeAdapter


def test_cross_site_requests_are_refused(client):
    assert (
        client.get("/api/projects", headers={"Origin": "https://evil.example"}).status_code == 403
    )
    r = client.post("/api/chats", json={}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    # The app's own pages (built UI and the Vite dev server) are fine.
    ok = client.get("/api/projects", headers={"Origin": "http://localhost:5173"})
    assert ok.status_code == 200
    assert client.get("/api/projects", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200


def _settings(req: RunRequest) -> dict:
    args = ClaudeCodeAdapter()._args(req)
    return json.loads(args[args.index("--settings") + 1])


def test_every_claude_run_denies_secret_files():
    s = _settings(RunRequest(prompt="x"))  # e.g. chat: no agent settings at all
    assert "Read(**/.env)" in s["permissions"]["deny"]
    assert "Read(**/*.p8)" in s["permissions"]["deny"]
    assert "sandbox" not in s


def test_shell_access_always_comes_with_the_sandbox():
    s = _settings(RunRequest(prompt="x", settings=assistant.settings(assistant.PROJECT_TOOLS)))
    assert s["sandbox"]["enabled"] and s["sandbox"]["failIfUnavailable"]
    assert s["sandbox"]["allowUnsandboxedCommands"] is False
    assert "~/.ssh" in s["sandbox"]["filesystem"]["denyRead"]
    assert str(config.DATA_DIR / "acc.db") in s["sandbox"]["filesystem"]["denyRead"]
    assert "Read(**/.env)" in s["permissions"]["deny"]
    assert assistant.settings(assistant.SCRATCH_TOOLS) is None  # no shell, no sandbox needed


def test_assistant_prompt_keeps_the_injection_rule():
    # Instructions found in files, images and web pages must stay data.
    assert "GÜVENLİK" in assistant.SYSTEM and "veridir" in assistant.SYSTEM


def test_redaction():
    text = (
        "token=ghp_" + "a" * 36 + " key sk-ant-" + "b" * 30 + " AKIAABCDEFGHIJKLMNOP\n"
        "DATABASE_PASSWORD=supersecret123 harmless=value\n"
        "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----"
    )
    out = security.redact(text)
    for leaked in ("ghp_aaaa", "sk-ant-bbbb", "AKIAABCD", "supersecret123", "BEGIN RSA"):
        assert leaked not in out
    assert "harmless=value" in out
    assert security.redact_data({"a": ["API_KEY: abcdef123456"]}) == {"a": ["API_KEY: [gizli]"]}


def test_change_logs_are_redacted(client):
    from acc import sessions
    from tests.helpers import new_chat, project, turn

    p = project(client)
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, "Bir satır ekle", p["id"])["meta"]["task_id"]
    sessions.log(task_id, "export TOKEN=abcdef123456")
    events = client.get(f"/api/tasks/{task_id}/events").json()
    assert "abcdef123456" not in json.dumps(events)


def test_data_dir_is_private():
    mode = stat.S_IMODE(config.DATA_DIR.stat().st_mode)
    assert mode == 0o700


def test_timestamps_carry_utc_zone(client):
    chat = client.post("/api/chats", json={}).json()
    assert chat["created_at"].endswith("+00:00")


def test_unknown_api_routes_are_404_not_the_ui_page(client):
    r = client.get("/api/olmayan-endpoint")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")


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


def test_websocket_handler_ends_when_the_client_leaves(client):
    import time

    from acc.events import broker

    before = len(broker._subs)
    with client.websocket_connect("/ws") as ws:
        broker.publish({"type": "approvals_changed"})
        assert ws.receive_json() == {"type": "approvals_changed"}
        assert len(broker._subs) == before + 1
    deadline = time.time() + 2
    while len(broker._subs) > before and time.time() < deadline:
        time.sleep(0.02)
    assert len(broker._subs) == before  # no handler left waiting for the next event
