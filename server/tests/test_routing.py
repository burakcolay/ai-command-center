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
from tests.test_execution import _project, _to_review


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


async def test_only_claude_does_everything_but_summaries_go_local():
    adapters = [fake("claude_code"), fake("ollama", LOCAL)]
    for kind in ("plan", "chat", "research", "design", "code", "review"):
        assert (await _pick(adapters, kind)).adapter.info.id == "claude_code", kind
    assert (await _pick(adapters, "summarize")).adapter.info.id == "ollama"


async def test_codex_arrives_and_takes_reviews_without_any_config():
    adapters = [fake("claude_code"), fake("codex")]
    assert (await _pick(adapters, "code")).adapter.info.id == "claude_code"
    assert (await _pick(adapters, "review")).adapter.info.id == "codex"


async def test_local_model_never_writes_code():
    assert (await _pick([fake("ollama", LOCAL)], "code")).adapter is None
    # Even if it were pinned (bypassing the API's own check), the capability check refuses.
    prefs.put("routing", {"code": "ollama"})
    choice = await _pick([fake("ollama", LOCAL)], "code")
    assert choice.adapter is None
    assert any("gereken yetenek yok" in s for s in choice.skipped)


async def test_second_opinion_avoids_the_author():
    adapters = [fake("claude_code"), fake("codex")]
    prefs.put("routing", {"review": "claude_code"})  # pinned...
    assert (await _pick(adapters, "review")).adapter.info.id == "claude_code"
    prefs.put("routing", {})
    choice = await _pick([fake("codex"), fake("claude_code")], "review", avoid={"codex"})
    assert choice.adapter.info.id == "claude_code" and "ikinci görüş" in choice.reason
    # If the author is the only option, it still reviews rather than nothing happening.
    assert (await _pick([fake("claude_code")], "review", avoid={"claude_code"})).adapter


async def test_quota_pressure_moves_work_and_unhealthy_models_are_skipped():
    busy = [fake("claude_code", use=0.95), fake("codex", use=0.2)]
    choice = await _pick(busy, "code")
    assert choice.adapter.info.id == "codex" and "kotası %95" in choice.reason
    # Nowhere to go: stay on the busy one rather than stall.
    assert (await _pick([fake("claude_code", use=0.95)], "code")).adapter.info.id == "claude_code"
    down = [fake("claude_code", state=ModelState.COOLDOWN), fake("codex")]
    assert (await _pick(down, "code")).adapter.info.id == "codex"


async def test_paid_api_is_never_routed_to():
    paid = fake("codex")
    paid.info = replace(paid.info, billing=Billing.PAID_API)
    choice = await _pick([paid], "code")
    assert choice.adapter is None and any("ücretli" in s for s in choice.skipped)


def test_routing_api(client):
    kinds = {k["id"]: k for k in client.get("/api/routing").json()}
    assert set(kinds) == set(routing.WORK_KINDS)
    assert kinds["code"]["current"] == "mock" and kinds["code"]["override"] == "auto"
    r = client.put("/api/routing/code", json={"adapter": "mock"})
    assert r.status_code == 200
    assert {k["id"]: k for k in r.json()}["code"]["override"] == "mock"
    assert client.put("/api/routing/code", json={"adapter": "yok"}).status_code == 400
    assert client.put("/api/routing/uydurma", json={"adapter": "auto"}).status_code == 404
    agents = {a["id"]: a for a in client.get("/api/agents").json()}
    assert agents["reviewer"]["work_label"] == "İnceleme ve test"


@pytest.fixture
def two_models():
    original = registry._adapters
    registry._adapters = {"claude_code": fake("claude_code"), "codex": fake("codex")}
    registry._health.clear()
    yield
    registry._adapters = original
    registry._health.clear()


def test_task_review_step_goes_to_a_different_model(client, two_models):
    p = _project(client)
    _, task_id, task = _to_review(client, p)
    by_agent = {s["agent"]: s["adapter_id"] for s in task["steps"]}
    assert by_agent["developer"] == "claude_code"
    assert by_agent["qa"] == "codex"  # independent second pair of eyes
    logs = [e["data"].get("text", "") for e in client.get(f"/api/tasks/{task_id}/events").json()]
    assert any("Model: Codex" in t for t in logs)
