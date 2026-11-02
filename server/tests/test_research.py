"""Research is just a message; a report the assistant writes is kept as markdown."""

import json
from pathlib import Path

from acc import prefs
from acc.adapters.base import RunRequest
from acc.adapters.claude_code import ClaudeCodeAdapter
from tests.helpers import new_chat, turn  # noqa: F401


def _args(req):
    return ClaudeCodeAdapter()._args(req)


def test_a_written_report_is_saved_next_to_memory(client, rec):
    chat_id = new_chat(client)
    done = turn(client, chat_id, "iOS için düşük rekabetli nişleri araştır, rapor hazırla")
    assert "WebSearch" in rec.requests[-1].tools
    [path] = [Path(p) for p in done["meta"]["reports"]]
    assert path.exists() and path.parent.name == "Araştırmalar"
    text = path.read_text()
    assert "Soru: iOS için düşük rekabetli nişleri araştır" in text and "# Demo raporu" in text


def test_output_folder_is_per_turn(client, rec):
    chat_id = new_chat(client)
    turn(client, chat_id, "Bir rapor yaz")
    turn(client, chat_id, "Sadece sohbet")
    a, b = rec.requests[-2].output_dir, rec.requests[-1].output_dir
    assert a != b and not list(b.iterdir())


def test_quality_and_model_preferences(client):
    assert client.put("/api/preferences/quality", json={"value": "best"}).status_code == 200
    assert client.put("/api/preferences/claude_model", json={"value": "opus"}).status_code == 200
    assert client.get("/api/system").json()["quality"] == "best"
    args = _args(RunRequest(prompt="x", effort="xhigh"))
    assert args[args.index("--model") + 1] == "opus"
    assert args[args.index("--effort") + 1] == "xhigh"
    prefs.put("claude_model", "default")
    prefs.put("quality", "balanced")
    assert "--model" not in _args(RunRequest(prompt="x"))  # default: the subscription decides


def test_custom_templates(client):
    r = client.post("/api/templates", json={"title": "x", "body": "y"})
    assert r.status_code == 201
    assert json.dumps(client.get("/api/templates").json()).count('"custom": true') >= 1
    assert client.delete(f"/api/templates/{r.json()['id']}").status_code == 204
