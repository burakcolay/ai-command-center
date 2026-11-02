"""Gemini via Antigravity CLI, against a fake `agy` that prints what the real one printed on
the user's Mac (one JSON object, status SUCCESS)."""

import json
import sys

import pytest

from acc.adapters.antigravity import AntigravityAdapter
from acc.adapters.base import ModelState, QuotaExceeded, RunRequest
from acc.routing import Router
from tests.test_routing import fake

FAKE = r"""#!{python}
import json, os, sys
args = sys.argv[1:]
if args[:1] == ["models"]:
    sys.exit(0 if os.environ.get("FAKE_LOGGED_IN", "1") == "1" else 1)
with open(os.environ["FAKE_LOG"], "w") as f:
    json.dump({{"args": args, "cwd": os.getcwd(), "stdin_tty": sys.stdin.isatty(),
               "gemini_key": "GEMINI_API_KEY" in os.environ}}, f)
mode = os.environ.get("FAKE_MODE", "text")
if mode == "quota":
    print(json.dumps({{"status": "ERROR", "error": "Quota exceeded for this account"}}))
    sys.exit(1)
if mode == "fail":
    print(json.dumps({{"status": "ERROR", "error": "model overloaded"}}))
    sys.exit(1)
response = "Merhaba!"
if mode == "schema":
    response = "```json\n" + json.dumps({{"ozet": "iyi", "sorunlar": []}}) + "\n```"
print("bilgi satırı")
print(json.dumps({{"conversation_id": "c1", "status": "SUCCESS", "response": response,
                  "duration_seconds": 1.2, "num_turns": 1, "usage": {{"total_tokens": 10}}}}))
"""


@pytest.fixture
def agy(tmp_path, monkeypatch):
    cli = tmp_path / "agy"
    cli.write_text(FAKE.format(python=sys.executable))
    cli.chmod(0o755)
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "run.json"))
    monkeypatch.setenv("GEMINI_API_KEY", "should-never-arrive")
    a = AntigravityAdapter(binary=str(cli))
    a.log = tmp_path / "run.json"
    return a


async def _events(a, req):
    return [ev async for ev in a.run(req, "r1")]


async def test_health(agy, monkeypatch, tmp_path):
    assert (await agy.health_check()).state == ModelState.AVAILABLE
    monkeypatch.setenv("FAKE_LOGGED_IN", "0")
    assert (await agy.health_check()).state == ModelState.AUTH_REQUIRED
    missing = AntigravityAdapter(binary=str(tmp_path / "yok"))
    h = await missing.health_check()
    assert h.state == ModelState.NOT_CONFIGURED and "antigravity-cli" in h.detail


async def test_a_review_runs_headless_sandboxed_and_returns_the_schema(agy, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_MODE", "schema")
    req = RunRequest(
        prompt="İncele",
        cwd=tmp_path,
        system_prompt="Sen inceleyicisin.",
        tools=["Read"],
        json_schema={"type": "object"},
        effort="high",
    )
    events = await _events(agy, req)
    sent = json.loads(agy.log.read_text())
    args = sent["args"]
    assert args[args.index("--print") + 1].startswith("TALİMATLAR:\nSen inceleyicisin.")
    assert args[args.index("--output-format") + 1] == "json" and "--sandbox" in args
    assert args[args.index("--effort") + 1] == "high" and "--json-schema" in args
    assert "--dangerously-skip-permissions" not in args
    assert sent["cwd"] == str(tmp_path) and sent["stdin_tty"] is False
    assert sent["gemini_key"] is False  # only the signed-in Google account can be used
    assert events[-1].data["structured"] == {"ozet": "iyi", "sorunlar": []}


async def test_a_summary_never_runs_in_the_home_folder(agy, tmp_path):
    events = await _events(agy, RunRequest(prompt="Özetle", tools=[]))
    sent = json.loads(agy.log.read_text())
    assert "orbit-agy-" in sent["cwd"]
    assert events[-1].kind == "result" and events[-1].data["text"] == "Merhaba!"


async def test_quota_waits_and_errors_are_reported(agy, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_MODE", "quota")
    with pytest.raises(QuotaExceeded):
        await _events(agy, RunRequest(prompt="x", cwd=tmp_path))
    assert (await agy.health_check()).state == ModelState.COOLDOWN
    agy._cooldown_until = None
    monkeypatch.setenv("FAKE_MODE", "fail")
    events = await _events(agy, RunRequest(prompt="x", cwd=tmp_path))
    assert events[-1].kind == "error" and "model overloaded" in events[-1].data["text"]


async def test_gemini_reviews_claudes_work_and_never_writes_it(client):
    from acc.adapters import Registry

    claude, gemini = fake("claude_code"), AntigravityAdapter(binary=sys.executable)
    gemini.health_check = lambda: _ok()  # type: ignore[method-assign]
    router = Router(Registry([claude, gemini]))
    review = await router.pick("review", needs_tools=True, avoid=frozenset({"claude_code"}))
    assert review.adapter is gemini
    assert (await router.pick("assistant", needs_tools=True)).adapter is claude
    # Claude gone: Gemini still isn't made the author.
    only = Router(Registry([gemini]))
    assert (await only.pick("assistant", needs_tools=True)).adapter is None


async def _ok():
    from acc.adapters.base import Health

    return Health(ModelState.AVAILABLE, "test")
