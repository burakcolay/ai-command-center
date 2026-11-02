"""Codex adapter against a fake `codex` CLI that speaks the documented JSONL format."""

import json
import sys
import time

import pytest

from acc.adapters.base import ModelState, QuotaExceeded, RunRequest
from acc.adapters.codex import CodexAdapter

FAKE = r"""#!{python}
import json, os, sys
args = sys.argv[1:]
if args[:2] == ["login", "status"]:
    mode = os.environ.get("FAKE_LOGIN", "chatgpt")
    if mode == "chatgpt":
        print("Logged in using ChatGPT")
    elif mode == "apikey":
        print("Logged in using an API key - sk-proj-***")
    else:
        print("Not logged in")
        sys.exit(1)
    sys.exit(0)
prompt = sys.stdin.read()
with open(os.environ["FAKE_LOG"], "w") as f:
    json.dump({{"args": args, "prompt": prompt,
               "openai_key": "OPENAI_API_KEY" in os.environ}}, f)
scenario = os.environ.get("FAKE_SCENARIO", "ok")
with open(os.path.join(os.path.dirname(os.environ["FAKE_LOG"]), "calls.jsonl"), "a") as f:
    f.write(json.dumps({{"args": args}}) + "\n")
if scenario == "nomodel" and "-m" in args:
    why = "The 'gpt-6-astra' model is not supported when using Codex with a ChatGPT account."
    out_ = {{"type": "turn.failed", "error": {{"message": why}}}}
    print(json.dumps(out_), flush=True)
    sys.exit(1)
def out(o): print(json.dumps(o), flush=True)
out({{"type": "thread.started", "thread_id": "t-1"}})
out({{"type": "turn.started"}})
if scenario == "quota":
    msg = "You've hit your usage limit. Try again in 2 hours 5 minutes."
    out({{"type": "error", "message": msg}})
    sys.exit(1)
if scenario == "fail":
    out({{"type": "turn.failed", "error": {{"message": "model error"}}}})
    sys.exit(1)
cmd = {{"id": "i1", "type": "command_execution", "command": "ls"}}
out({{"type": "item.started", "item": cmd}})
out({{"type": "item.completed", "item": {{"id": "i1", "type": "command_execution", "command": "ls",
     "exit_code": 0}}}})
out({{"type": "item.completed", "item": {{"id": "i2", "type": "file_change",
     "changes": [{{"path": "a.py", "kind": "update"}}]}}}})
final = json.dumps({{"ozet": "iyi", "sorunlar": []}}) if scenario == "schema" else "Bitti."
out({{"type": "item.completed", "item": {{"id": "i3", "type": "agent_message", "text": final}}}})
out({{"type": "turn.completed", "usage": {{"input_tokens": 10, "output_tokens": 5}}}})
"""


@pytest.fixture
def codex(tmp_path, monkeypatch):
    cli = tmp_path / "codex"
    cli.write_text(FAKE.format(python=sys.executable))
    cli.chmod(0o755)
    log = tmp_path / "run.json"
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-arrive")
    adapter = CodexAdapter(binary=str(cli))
    adapter.log = log
    return adapter


async def _events(adapter, req):
    return [ev async for ev in adapter.run(req, "r1")]


async def test_only_a_chatgpt_login_is_usable(codex, monkeypatch, tmp_path):
    assert (await codex.health_check()).state == ModelState.AVAILABLE
    monkeypatch.setenv("FAKE_LOGIN", "apikey")
    h = await codex.health_check()
    assert h.state == ModelState.PAID_ACCESS_REQUIRED and "codex logout" in h.detail
    monkeypatch.setenv("FAKE_LOGIN", "none")
    assert (await codex.health_check()).state == ModelState.AUTH_REQUIRED
    missing = CodexAdapter(binary=str(tmp_path / "yok"))
    assert (await missing.health_check()).state == ModelState.NOT_CONFIGURED


async def test_a_review_runs_read_only_and_returns_structured_output(codex, tmp_path):
    req = RunRequest(
        prompt="İncele",
        cwd=tmp_path,
        system_prompt="Sen inceleyicisin.",
        tools=["Read", "Glob", "Grep"],
        json_schema={"type": "object"},
        effort="xhigh",
    )
    events = await _events(codex, req)
    sent = json.loads(codex.log.read_text())
    args = sent["args"]
    assert args[args.index("-s") + 1] == "read-only"
    assert 'forced_login_method="chatgpt"' in args and 'approval_policy="never"' in args
    assert 'model_reasoning_effort="xhigh"' in args and "--output-schema" in args
    assert args[-1] == "-" and sent["prompt"].startswith("TALİMATLAR:\nSen inceleyicisin.")
    assert sent["openai_key"] is False  # API keys never reach the CLI
    result = events[-1]
    assert result.kind == "result" and result.data["text"] == "Bitti."


async def test_writing_work_gets_a_workspace_sandbox(codex, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SCENARIO", "schema")
    out = tmp_path / "out"
    req = RunRequest(
        prompt="Değiştir",
        cwd=tmp_path,
        tools=["Read", "Edit", "Write", "Bash", "WebSearch"],
        output_dir=out,
        json_schema={"type": "object"},
        stream_text=True,
    )
    events = await _events(codex, req)
    args = json.loads(codex.log.read_text())["args"]
    assert args[args.index("-s") + 1] == "workspace-write"
    assert args[args.index("--add-dir") + 1] == str(out)
    assert 'web_search="live"' in args
    tools = [ev.data for ev in events if ev.kind == "tool"]
    assert tools == [
        {"name": "Bash", "input": {"command": "ls"}},  # once, though started + completed
        {"name": "Edit", "input": {"file_path": "a.py"}},
    ]
    assert any(ev.kind == "delta" for ev in events)
    assert events[-1].data["structured"] == {"ozet": "iyi", "sorunlar": []}


async def test_usage_limit_waits_instead_of_failing(codex, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_SCENARIO", "quota")
    with pytest.raises(QuotaExceeded) as e:
        await _events(codex, RunRequest(prompt="x", cwd=tmp_path, tools=["Read"]))
    assert abs(e.value.resets_at - (time.time() + 2 * 3600 + 5 * 60)) < 60
    h = await codex.health_check()
    assert h.state == ModelState.COOLDOWN  # routed around until the reset


async def test_a_failed_turn_is_an_error(codex, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_SCENARIO", "fail")
    events = await _events(codex, RunRequest(prompt="x", cwd=tmp_path, tools=["Read"]))
    assert events[-1].kind == "error" and events[-1].data["text"] == "model error"


async def test_a_model_outside_the_plan_falls_back_to_the_default(codex, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_SCENARIO", "nomodel")
    req = RunRequest(prompt="x", cwd=tmp_path, tools=["Read"], model="gpt-6-astra")
    events = await _events(codex, req)
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert "-m" in calls[0]["args"] and "-m" not in calls[1]["args"]
    assert any("bu planda yok" in ev.data.get("text", "") for ev in events if ev.kind == "log")
    assert events[-1].kind == "result"
