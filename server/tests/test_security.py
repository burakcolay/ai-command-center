import json
import stat

from acc import config, security
from acc.adapters.base import RunRequest
from acc.adapters.claude_code import ClaudeCodeAdapter
from acc.agents import AGENTS


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


def test_shell_agents_get_sandbox_plus_secret_rules():
    s = _settings(RunRequest(prompt="x", settings=AGENTS["developer"].settings))
    assert s["sandbox"]["enabled"] and s["sandbox"]["failIfUnavailable"]
    assert s["sandbox"]["allowUnsandboxedCommands"] is False
    assert "~/.ssh" in s["sandbox"]["filesystem"]["denyRead"]
    assert str(config.DATA_DIR / "acc.db") in s["sandbox"]["filesystem"]["denyRead"]
    assert "Read(**/.env)" in s["permissions"]["deny"]
    assert AGENTS["reviewer"].settings is None  # no shell, no sandbox needed


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


def test_task_logs_are_redacted(client):
    from acc.api import orchestrator

    chat = client.post("/api/chats", json={}).json()
    task_id = client.post(f"/api/chats/{chat['id']}/messages", json={"content": "x"}).json()[
        "task"
    ]["id"]
    orchestrator._event(
        task_id, "tool", {"name": "Bash", "input": {"command": "export TOKEN=abcdef123456"}}
    )
    events = client.get(f"/api/tasks/{task_id}/events").json()
    assert "abcdef123456" not in json.dumps(events)


def test_data_dir_is_private():
    mode = stat.S_IMODE(config.DATA_DIR.stat().st_mode)
    assert mode == 0o700


def test_timestamps_carry_utc_zone(client):
    chat = client.post("/api/chats", json={}).json()
    assert chat["created_at"].endswith("+00:00")
