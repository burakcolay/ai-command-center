import json

import httpx
import pytest

from acc import prefs
from acc.adapters.base import AdapterError, ModelState, RunRequest
from acc.adapters.ollama import OllamaAdapter

TAGS = {
    "models": [
        {
            "name": "qwen2.5:7b",
            "size": 4_700_000_000,
            "details": {"parameter_size": "7.6B", "quantization_level": "Q4_K_M"},
        },
        {"name": "llama3.2:3b", "size": 2_000_000_000, "details": {"parameter_size": "3.2B"}},
    ]
}


def fake_ollama(tags=TAGS, chunks=("Mer", "haba", "!"), seen=None):
    """A stand-in for the Ollama HTTP API (/api/tags, /api/ps, /api/chat NDJSON)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=tags)
        if request.url.path == "/api/ps":
            return httpx.Response(
                200, json={"models": [{"name": "qwen2.5:7b", "size": 5_000_000_000}]}
            )
        if request.url.path == "/api/chat":
            body = json.loads(request.content)
            if seen is not None:
                seen.append(body)
            lines = [
                json.dumps({"message": {"role": "assistant", "content": c}, "done": False})
                for c in chunks
            ]
            lines.append(json.dumps({"message": {"content": ""}, "done": True}))
            return httpx.Response(200, content="\n".join(lines).encode())
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def offline():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    return httpx.MockTransport(handler)


async def test_offline_and_empty_states():
    assert (await OllamaAdapter(transport=offline()).health_check()).state == ModelState.OFFLINE
    empty = OllamaAdapter(transport=fake_ollama(tags={"models": []}))
    assert (await empty.health_check()).state == ModelState.NOT_CONFIGURED


async def test_model_choice_follows_preference(client):
    a = OllamaAdapter(transport=fake_ollama())
    h = await a.health_check()
    assert h.state == ModelState.AVAILABLE and h.data["selected"] == "qwen2.5:7b"
    assert h.data["models"][0]["size_gb"] == 4.4
    prefs.put("ollama_model", "llama3.2:3b")
    assert (await a.health_check()).data["selected"] == "llama3.2:3b"
    prefs.put("ollama_model", "olmayan:model")  # stale preference falls back to first
    assert (await a.health_check()).data["selected"] == "qwen2.5:7b"


async def test_streams_deltas_and_result(client):
    seen = []
    a = OllamaAdapter(transport=fake_ollama(seen=seen))
    req = RunRequest(prompt="selam", system_prompt="sistem", tools=[], stream_text=True)
    events = [e async for e in a.run(req, "r1")]
    assert [e.data["text"] for e in events if e.kind == "delta"] == ["Mer", "haba", "!"]
    assert events[-1].kind == "result" and events[-1].data["text"] == "Merhaba!"
    body = seen[0]
    assert body["messages"][0] == {"role": "system", "content": "sistem"}
    assert body["stream"] is True and body["keep_alive"]


async def test_structured_output_uses_format(client):
    seen = []
    a = OllamaAdapter(transport=fake_ollama(chunks=('{"a":', " 1}"), seen=seen))
    schema = {"type": "object", "properties": {"a": {"type": "number"}}}
    events = [e async for e in a.run(RunRequest(prompt="x", json_schema=schema), "r2")]
    assert events[-1].data["structured"] == {"a": 1}
    assert seen[0]["format"] == schema


async def test_never_gets_tools():
    a = OllamaAdapter(transport=fake_ollama())
    with pytest.raises(AdapterError):
        [e async for e in a.run(RunRequest(prompt="x", tools=["Read"]), "r3")]
    assert not a.capabilities.tools


async def test_usage_reports_loaded_models():
    u = await OllamaAdapter(transport=fake_ollama()).usage_status()
    assert u.source == "verified" and "qwen2.5:7b" in u.detail
