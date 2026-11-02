from dataclasses import replace

import pytest

from acc import prefs, routing
from acc.adapters import Registry, registry
from acc.adapters.base import (
    AdapterInfo,
    Billing,
    Capabilities,
    Health,
    ModelState,
    Usage,
    UsageWindow,
)
from acc.adapters.mock import MockAdapter
from tests.helpers import new_chat, turn


def fake(adapter_id: str, caps: Capabilities | None = None, state=ModelState.AVAILABLE, use=None):
    """A mock adapter wearing another adapter's id (e.g. a future Codex)."""

    class Fake(MockAdapter):
        info = AdapterInfo(
            adapter_id, adapter_id.title(), "test", Billing.SUBSCRIPTION, "-", True, False
        )
        capabilities = caps or MockAdapter.capabilities

        async def health_check(self):
            return Health(state, "test")

        async def usage_status(self):
            if use is None:
                return Usage(source="unknown", detail="")
            return Usage(
                source="verified",
                detail="",
                windows=[UsageWindow("five_hour", use, None, "allowed")],
            )

    return Fake(delay=0.01)


LOCAL = Capabilities(chat=True, structured_output=True)  # what Ollama offers


@pytest.fixture(autouse=True)
def clean_routing():
    prefs.put("routing", {})
    yield
    prefs.put("routing", {})


async def _pick(adapters, kind, **kw):
    return await routing.Router(Registry(adapters)).pick(kind, **kw)


async def test_claude_is_the_assistant_and_summaries_go_local():
    adapters = [fake("claude_code"), fake("ollama", LOCAL)]
    assert (await _pick(adapters, "assistant", needs_tools=True)).adapter.info.id == "claude_code"
    assert (await _pick(adapters, "summarize")).adapter.info.id == "ollama"


async def test_codex_is_the_backup_assistant_without_any_config():
    adapters = [fake("claude_code", state=ModelState.COOLDOWN), fake("codex")]
    assert (await _pick(adapters, "assistant", needs_tools=True)).adapter.info.id == "codex"


async def test_local_model_is_never_the_assistant():
    assert (await _pick([fake("ollama", LOCAL)], "assistant", needs_tools=True)).adapter is None
    # Even if it were pinned (bypassing the API's own check), the capability check refuses.
    prefs.put("routing", {"assistant": "ollama"})
    choice = await _pick([fake("ollama", LOCAL)], "assistant", needs_tools=True)
    assert choice.adapter is None
    assert any("gereken yetenek yok" in s for s in choice.skipped)


async def test_a_second_opinion_comes_from_someone_else():
    adapters = [fake("codex"), fake("claude_code")]
    choice = await _pick(adapters, "review", avoid=frozenset({"codex"}))
    assert choice.adapter.info.id == "claude_code" and "ikinci göz" in choice.reason
    # Nobody else around: the author's model still reviews (in a separate context).
    alone = await _pick([fake("claude_code")], "review", avoid=frozenset({"claude_code"}))
    assert alone.adapter.info.id == "claude_code"


async def test_a_pinned_model_wins():
    adapters = [fake("claude_code"), fake("codex")]
    prefs.put("routing", {"assistant": "codex"})
    choice = await _pick(adapters, "assistant")
    assert choice.adapter.info.id == "codex" and choice.reason == "elle seçildi"


async def test_quota_pressure_moves_work_and_unhealthy_models_are_skipped():
    busy = [fake("claude_code", use=0.95), fake("codex", use=0.2)]
    choice = await _pick(busy, "assistant")
    assert choice.adapter.info.id == "codex" and "kotası %95" in choice.reason
    # Nowhere to go: stay on the busy one rather than stall.
    alone = [fake("claude_code", use=0.95)]
    assert (await _pick(alone, "assistant")).adapter.info.id == "claude_code"
    down = [fake("claude_code", state=ModelState.COOLDOWN), fake("codex")]
    assert (await _pick(down, "assistant")).adapter.info.id == "codex"


async def test_paid_api_is_never_routed_to():
    paid = fake("codex")
    paid.info = replace(paid.info, billing=Billing.PAID_API)
    choice = await _pick([paid], "assistant")
    assert choice.adapter is None and any("ücretli" in s for s in choice.skipped)


def test_routing_api(client):
    kinds = {k["id"]: k for k in client.get("/api/routing").json()}
    assert set(kinds) == {"assistant", "review", "summarize"}
    assert kinds["assistant"]["current"] == "mock" and kinds["assistant"]["override"] == "auto"
    r = client.put("/api/routing/assistant", json={"adapter": "mock"})
    assert r.status_code == 200
    assert {k["id"]: k for k in r.json()}["assistant"]["override"] == "mock"
    assert client.put("/api/routing/assistant", json={"adapter": "yok"}).status_code == 400
    assert client.put("/api/routing/uydurma", json={"adapter": "auto"}).status_code == 404
    assert client.get("/api/agents").status_code == 404  # no agents or modes any more


@pytest.fixture
def two_models():
    original = registry._adapters
    registry._adapters = {
        "claude_code": fake("claude_code", use=0.97),
        "codex": fake("codex", use=0.1),
    }
    registry._health.clear()
    yield
    registry._adapters = original
    registry._health.clear()


def test_a_chat_turn_moves_to_the_backup_when_claude_is_nearly_used_up(client, two_models):
    chat_id = new_chat(client)
    assert turn(client, chat_id, "Selam")["adapter_id"] == "codex"
