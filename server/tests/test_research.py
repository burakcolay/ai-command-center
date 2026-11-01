import json
from pathlib import Path

from acc import prefs
from acc.adapters.base import RunRequest
from acc.adapters.claude_code import ClaudeCodeAdapter
from acc.agents import CHAT_SYSTEM, RESEARCH_SYSTEM
from tests.test_chat import _wait_msg
from tests.test_memory import rec  # noqa: F401  (fixture)


def _args(req):
    return ClaudeCodeAdapter()._args(req)


def test_research_mode_runs_deep_and_saves_a_report(client, rec):  # noqa: F811
    chat = client.post("/api/chats", json={}).json()
    r = client.post(
        f"/api/chats/{chat['id']}/messages",
        json={"content": "iOS için düşük rekabetli nişleri araştır", "mode": "research"},
    )
    assert r.status_code == 201, r.text
    msg = r.json()["messages"][1]
    assert msg["meta"] == {"kind": "research"}
    done = _wait_msg(client, chat["id"], msg["id"], "done")
    req = rec.requests[-1]
    assert req.system_prompt == RESEARCH_SYSTEM
    assert req.effort == "xhigh"  # balanced quality: research thinks hardest
    assert set(req.tools) == {"WebSearch", "WebFetch"}  # no project: web only
    path = Path(done["meta"]["report_path"])
    assert path.exists() and path.parent.name == "Araştırmalar"
    text = path.read_text()
    assert "Soru: iOS için düşük rekabetli nişleri araştır" in text


def test_chat_uses_the_new_prompt_and_effort(client, rec):  # noqa: F811
    chat = client.post("/api/chats", json={}).json()
    r = client.post(f"/api/chats/{chat['id']}/messages", json={"content": "selam", "mode": "chat"})
    _wait_msg(client, chat["id"], r.json()["messages"][1]["id"], "done")
    req = rec.requests[-1]
    assert req.system_prompt == CHAT_SYSTEM and "İnisiyatif al" in CHAT_SYSTEM
    assert req.effort == "high"


def test_quality_and_model_preferences(client):
    assert client.put("/api/preferences/quality", json={"value": "best"}).status_code == 200
    assert client.put("/api/preferences/quality", json={"value": "turbo"}).status_code == 400
    assert client.put("/api/preferences/claude_model", json={"value": "opus"}).status_code == 200
    assert client.get("/api/system").json()["quality"] == "best"
    args = _args(RunRequest(prompt="x", effort="xhigh"))
    assert args[args.index("--model") + 1] == "opus"
    assert args[args.index("--effort") + 1] == "xhigh"
    prefs.put("claude_model", "default")
    prefs.put("quality", "balanced")
    assert "--model" not in _args(RunRequest(prompt="x"))  # default: the subscription decides


def test_research_templates_exist(client):
    modes = {t["id"]: t["mode"] for t in client.get("/api/templates").json()}
    assert modes["b-market"] == "research" and modes["b-competitors"] == "research"
    r = client.post("/api/templates", json={"title": "x", "body": "y", "mode": "research"})
    assert r.status_code == 201
    assert json.dumps(client.get("/api/templates").json()).count('"custom": true') >= 1
