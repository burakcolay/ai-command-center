"""Model plan per role, and the live picture of who works on a turn."""

import json
import sys

import pytest

from acc import assistant, prefs, tiers
from acc.adapters.base import RunRequest
from acc.adapters.claude_code import ClaudeCodeAdapter
from acc.orchestra import Orchestra
from tests.helpers import new_chat, turn


@pytest.fixture
def quality(client):
    yield lambda v: prefs.put("quality", v)
    prefs.put("quality", "balanced")
    prefs.put("claude_model", "default")


def test_plan_per_quality(quality):
    quality("best")  # the plan the user described: conductor strongest, builders strong-medium
    p = assistant.plan()
    assert p["lead"] == tiers.Power("guclu", "xhigh")
    assert p["builder"] == tiers.Power("guclu", "medium")
    assert assistant.lead_model() == "opus"
    quality("economy")
    assert assistant.plan()["lead"] == tiers.Power("orta", "medium")
    assert assistant.lead_model() == "sonnet"
    prefs.put("claude_model", "fable")  # a pin in Settings wins
    assert assistant.lead_model() == "fable"


def test_the_card_picks_less_never_more(quality):
    assert tiers.for_area("Hafif · low", "balanced") == tiers.Power("hafif", "low")
    assert tiers.for_area("Güçlü · xhigh", "balanced") == tiers.Power("guclu", "medium")
    assert tiers.for_area("", "balanced") == tiers.preset("balanced")["builder"]
    assert tiers.Power("orta", "low").model_for("codex") == "gpt-6.1-sol"
    assert tiers.Power("guclu", "low").model_for("claude_code") == "opus"
    assert tiers.Power("hafif", "low").model_for("gemini") is None


def test_orchestra_follows_recorded_events():
    o = Orchestra(1)
    o.set_lead("claude_code", "opus", "high")
    o.set_roster(
        {"backend-gelistirici": {"model": "sonnet", "effort": "medium"}},
        {"backend-gelistirici": "Backend geliştirici"},
        {"backend": {"model": "gpt-6.1-sol", "effort": "medium"}},
    )
    o.apply({"op": "lead", "model": "claude-opus-5-5"})
    o.apply({"op": "start", "id": "t1", "agent": "backend-gelistirici", "task": "API"})
    o.apply({"op": "model", "id": "t1", "model": "claude-sonnet-5-5"})
    o.tool(
        {"name": "Edit", "input": {"file_path": "/x/server/app.py"}, "parent": "t1", "agent": "b"}
    )
    o.apply({"op": "progress", "id": "t1", "tokens": 7895, "tools": 1, "activity": "Writing"})
    o.apply({"op": "codex", "id": "c1", "parent": "t1", "area": "backend"})
    o.apply({"op": "codex_end", "id": "c1", "error": False})
    o.apply({"op": "end", "id": "t1", "status": "completed", "tokens": 15404})
    o.add_usage(
        {"claude-opus-5-5": {"inputTokens": 10, "cacheCreationInputTokens": 90, "outputTokens": 50}}
    )
    snap = o.finish()
    assert snap["lead"]["model"] == "Opus" and snap["lead"]["actual"] == "Opus 5.5"
    backend, codex = snap["members"]
    assert backend["label"] == "Backend geliştirici" and backend["actual"] == "Sonnet 5.5"
    assert (backend["effort"], backend["tokens"], backend["status"]) == ("medium", 15404, "done")
    assert codex["vendor"] == "Codex" and codex["model"] == "GPT-6.1 Sol"
    assert snap["usage"]["Opus 5.5"] == {"input": 100, "output": 50, "cached": 0}


def test_a_turn_keeps_its_team_picture(client, rec):
    chat_id = new_chat(client)
    m = turn(client, chat_id, "Ekip kurup araştır")
    team = m["meta"]["team"]
    assert team["lead"]["status"] == "done" and team["lead"]["effort"] == "high"
    assert rec.requests[0].model == "opus" and rec.requests[0].effort == "high"
    names = [x["agent"] for x in team["members"]]
    assert names and all(x["status"] == "done" and x["tokens"] > 0 for x in team["members"])
    kesifci = next(x for x in team["members"] if x["agent"] == "kesifci")
    assert kesifci["actual"] == "Haiku 5.5" and kesifci["effort"] == "low"


async def test_an_unavailable_model_falls_back_to_the_default(tmp_path):
    status = json.dumps({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"})
    fail = {
        "type": "result",
        "is_error": True,
        "api_error_status": 404,
        "result": "There's an issue with the selected model (opus).",
    }
    ok = {"type": "result", "subtype": "success", "result": "Tamam"}
    script = tmp_path / "claude"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "a = sys.argv[1:]\n"
        f"if a[:1] == ['auth']: print({status!r}); sys.exit(0)\n"
        "if a[:1] == ['--help']: sys.exit(0)\n"
        f"open({str(tmp_path / 'calls')!r}, 'a').write(json.dumps(a) + '\\n')\n"
        "sys.stdin.read()\n"
        f"print(json.dumps({fail!r} if '--model' in a else {ok!r}))\n"
    )
    script.chmod(0o755)
    agents = {"x": {"model": "opus", "effort": "low"}, "y": {"model": "haiku", "effort": "low"}}
    req = RunRequest("x", model="opus", agents=agents)
    events = [ev async for ev in ClaudeCodeAdapter(binary=str(script)).run(req, "r")]
    calls = [json.loads(line) for line in (tmp_path / "calls").read_text().splitlines()]
    assert "--model" in calls[0] and "--model" not in calls[1]
    second = json.loads(calls[1][calls[1].index("--agents") + 1])
    assert second["x"]["model"] == "inherit" and second["y"]["model"] == "haiku"
    assert events[-1].kind == "result" and events[-1].data["text"] == "Tamam"
    assert any("aboneliğinde yok" in e.data.get("text", "") for e in events if e.kind == "log")
