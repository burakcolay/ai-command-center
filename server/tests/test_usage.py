"""Where the tokens went: every provider's counts in one shape, totals per model and day."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from acc import mcp_codex, usage
from acc.adapters.base import RunRequest, model_usage
from acc.db import session
from acc.models import Message
from acc.orchestra import Orchestra
from tests.helpers import new_chat, turn
from tests.test_codex import _events, codex  # noqa: F401  (fixture)


def test_each_providers_counts_become_one_shape():
    # Codex / OpenAI: the cached part is inside input_tokens.
    got = model_usage("gpt-6.1-sol", {"input_tokens": 1000, "cached_input_tokens": 600})
    assert got == {
        "gpt-6.1-sol": {"inputTokens": 400, "outputTokens": 0, "cacheReadInputTokens": 600}
    }
    # Ollama's last line.
    got = model_usage("qwen3", {"prompt_eval_count": 30, "eval_count": 9}, cached_in_input=False)
    assert got["qwen3"] == {"inputTokens": 30, "outputTokens": 9, "cacheReadInputTokens": 0}
    # Gemini-style names, already split per model.
    gemini = {"gemini-3.8-flash": {"promptTokenCount": 10, "candidatesTokenCount": 4}}
    got = model_usage("x", gemini)
    assert got["gemini-3.8-flash"]["outputTokens"] == 4
    # Shapes we don't know are left out rather than guessed.
    assert model_usage("x", {"foo": 1}) is None and model_usage("x", None) is None
    assert model_usage("x", {"input_tokens": True}) is None


async def test_codex_reports_its_tokens(codex, tmp_path):  # noqa: F811
    req = RunRequest(prompt="x", cwd=tmp_path, tools=["Read"], model="gpt-6.1-sol")
    result = [e for e in await _events(codex, req) if e.kind == "result"][0]
    assert result.data["model_usage"]["gpt-6.1-sol"]["inputTokens"] == 10
    req = RunRequest(prompt="x", cwd=tmp_path, tools=["Read"])
    result = [e for e in await _events(codex, req) if e.kind == "result"][0]
    assert "Codex" in result.data["model_usage"]  # the account's default model


async def test_codex_through_the_bridge_counts_toward_the_turn(codex, tmp_path):  # noqa: F811
    log = tmp_path / "codex-usage.jsonl"
    text, err = await mcp_codex.run_task(
        tmp_path, "bir şey yap", {"model": "gpt-6.1-sol"}, codex, log
    )
    assert not err and json.loads(log.read_text())["gpt-6.1-sol"]["outputTokens"] == 5

    o = Orchestra(1)
    o.set_lead("claude_code", "claude-opus-5-5", "high")
    o.add_usage({"claude-opus-5-5": {"inputTokens": 100, "outputTokens": 7}})
    o.codex_usage_file = log
    team = o.finish()
    assert team["usage"]["Opus 5.5"]["vendor"] == "Claude"
    assert team["usage"]["GPT-6.1 Sol"] == {
        "input": 10,
        "output": 5,
        "cached": 0,
        "vendor": "Codex",
    }
    assert not log.exists()  # read once, then removed


def test_the_bridge_is_told_where_to_write():
    cfg = mcp_codex.config(Path("/tmp/x"), {})
    got = mcp_codex.with_usage_file(cfg, Path("/tmp/u.jsonl"))
    assert got["mcpServers"]["orbit"]["args"][-2:] == ["--usage", "/tmp/u.jsonl"]
    assert "--usage" not in cfg["mcpServers"]["orbit"]["args"]  # original untouched
    assert mcp_codex.with_usage_file(None, Path("/tmp/u")) is None


def _add(chat_id: int, when: datetime, used: dict) -> None:
    with session() as s:
        s.add(
            Message(
                chat_id=chat_id,
                role="assistant",
                content="x",
                meta={"team": {"usage": used}},
                created_at=when,
            )
        )


def test_the_week_in_tokens(client):
    def models(got):
        return {m["model"]: m for m in got["by_model"]}

    before = client.get("/api/usage?days=7").json()  # other tests' turns are in here too
    chat_id = new_chat(client)
    now = datetime.now(UTC)
    _add(chat_id, now, {"Opus 5.5": {"input": 10**9, "output": 200, "cached": 50000}})
    _add(
        chat_id,
        now - timedelta(days=1),
        {
            "Sonnet 5.5": {"input": 300, "output": 30, "cached": 0, "vendor": "Claude"},
            "GPT-6.1 Sol": {"input": 400, "output": 40, "cached": 100},  # saved before vendors
        },
    )
    _add(chat_id, now - timedelta(days=30), {"Opus 5.5": {"input": 9, "output": 9, "cached": 9}})

    got = client.get("/api/usage?days=7").json()
    grew = {k: got["totals"][k] - before["totals"][k] for k in got["totals"]}
    assert grew == {"input": 10**9 + 700, "output": 270, "cached": 50100, "turns": 2}
    assert len(got["by_day"]) == 7
    assert got["by_day"][-1]["input"] - before["by_day"][-1]["input"] == 10**9
    assert got["by_model"][0]["model"] == "Opus 5.5"  # sorted by tokens
    gpt = models(got)["GPT-6.1 Sol"]
    assert (
        gpt["vendor"] == "Codex"
        and gpt["input"] - models(before).get("GPT-6.1 Sol", {"input": 0})["input"] == 400
    )
    top = got["top_turns"][0]
    assert top["input"] == 10**9 and top["chat_id"] == chat_id
    assert client.get("/api/usage?days=0").status_code == 422


def test_a_real_turn_is_counted(client):
    chat_id = new_chat(client)
    turn(client, chat_id, "Merhaba, bir fikrim var")
    got = usage.summary(1)
    assert got["totals"]["turns"] >= 1
    assert any(m["vendor"] == "Demo" for m in got["by_model"])
