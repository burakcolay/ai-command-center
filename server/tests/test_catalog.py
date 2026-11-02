"""Picking any provider's model and effort under the composer."""

from dataclasses import replace

from acc import catalog
from acc.adapters import registry
from acc.adapters.base import AdapterEvent, Health, ModelState
from acc.adapters.mock import MockAdapter
from tests.helpers import Recorder, new_chat, project, use, wait_msg


class As(Recorder):
    """A recorder wearing another provider's id."""

    def __init__(self, adapter_id, name, reply="Tamam."):
        super().__init__()
        self.info = replace(MockAdapter.info, id=adapter_id, name=name)
        self.reply = reply

    async def health_check(self):
        return Health(ModelState.AVAILABLE, "test")

    async def run(self, req, run_id):
        self.requests.append(req)
        yield AdapterEvent("result", {"text": self.reply})


def _say(client, chat_id, text, model=None, effort=None, project_id=None):
    body = {"content": text, "project_id": project_id}
    if model:
        body |= {"model_choice": model, "effort_choice": effort}
    r = client.post(f"/api/chats/{chat_id}/messages", json=body)
    assert r.status_code == 201, r.text
    return wait_msg(client, chat_id, r.json()["messages"][1]["id"])


def test_catalog_lists_providers_models_and_efforts(client):
    got = client.get("/api/catalog").json()
    demo = next(p for p in got if p["id"] == "mock")
    assert demo["available"] and {m["id"] for m in demo["models"]} >= {"claude-opus-5-5"}
    opus = next(m for m in demo["models"] if m["id"] == "claude-opus-5-5")
    assert opus["efforts"] == ["low", "medium", "high", "xhigh", "max"]


def test_provider_outputs_are_parsed():
    codex = '{"models": [{"slug": "gpt-6.1-sol", "display_name": "GPT-6.1-Sol", "visibility": "list", "priority": 1, "default_reasoning_level": "low", "supported_reasoning_levels": [{"effort": "low"}, {"effort": "ultra"}]}, {"slug": "hidden", "visibility": "hide"}]}'  # noqa: E501
    assert catalog.parse_codex(codex) == [
        {
            "id": "gpt-6.1-sol",
            "label": "GPT-6.1-Sol",
            "efforts": ["low", "ultra"],
            "effort": "low",
            "note": "",
        }  # noqa: E501
    ]
    agy = "gemini-3.8-flash-high     Gemini 3.8 Flash (High)\nclaude-sonnet-4-6   Claude Sonnet 4.6"
    assert [m["id"] for m in catalog.parse_agy(agy)] == [
        "gemini-3.8-flash-high",
        "claude-sonnet-4-6",
    ]


def test_gemini_answers_read_only_at_the_picked_model_and_effort(client):
    gemini = As("gemini", "Gemini")
    original = use(MockAdapter(delay=0.01), gemini)
    try:
        p = project(client)
        chat_id = new_chat(client, p["id"])
        m = _say(
            client, chat_id, "Bu proje ne yapıyor?", "gemini/gemini-3.8-flash-high", "low", p["id"]
        )
        req = gemini.requests[-1]
        assert (req.model, req.effort) == ("gemini-3.8-flash-high", "low")
        assert "Write" not in req.tools and "Edit" not in req.tools and req.agents is None
        assert "Gemini seçili" in req.prompt
        assert m["adapter_id"] == "gemini" and m["meta"]["team"]["lead"]["vendor"] == "Gemini"
    finally:
        registry._adapters = original
        registry._health.clear()


def test_back_to_claude_it_hears_what_was_said_meanwhile(client):
    claude = As("claude_code", "Claude", "Claude burada.")
    gemini = As("gemini", "Gemini", "Gemini'nin görüşü: mavi tema.")
    original = use(claude, gemini)
    try:
        chat_id = new_chat(client)
        _say(client, chat_id, "Rakipleri araştır", "claude_code/claude-opus-5-5", "high")
        first = claude.requests[-1]
        _say(client, chat_id, "Renk ne olsun?", "gemini/gemini-3.8-flash-high", "medium")
        _say(client, chat_id, "Peki buna ne dersin?", "claude_code/claude-sonnet-5-5", "low")
        back = claude.requests[-1]
        assert back.resume == first.session_id  # its own conversation goes on…
        assert "ARADA BAŞKA MODELLERLE KONUŞULANLAR" in back.prompt  # …plus what it missed
        assert "mavi tema" in back.prompt and "Renk ne olsun?" in back.prompt
        assert (back.model, back.effort) == ("claude-sonnet-5-5", "low")
    finally:
        registry._adapters = original
        registry._health.clear()


def test_a_picked_local_model_knows_it_has_no_tools(client):
    local = As("ollama", "Ollama")
    original = use(MockAdapter(delay=0.01), local)
    try:
        chat_id = new_chat(client)
        _say(client, chat_id, "Merhaba", "ollama/qwen2.5:7b")
        req = local.requests[-1]
        assert req.model == "qwen2.5:7b" and req.tools == [] and req.cwd is None
        assert "yerel model seçili" in req.prompt and "kullanılamıyor" not in req.prompt
    finally:
        registry._adapters = original
        registry._health.clear()
