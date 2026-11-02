"""Plain talk runs light (no tokens spent deciding); work gets the full plan; the user can pick."""

from dataclasses import replace

from acc import intent
from acc.adapters import registry
from acc.adapters.base import AdapterEvent
from acc.adapters.mock import MockAdapter
from acc.events import broker
from tests.helpers import Recorder, chat_state, new_chat, project, turn, use


def test_talk_or_work():
    talk = [
        "Aklımda bir uygulama fikri var, birlikte netleştirelim",
        "Merhaba, nasılsın?",
        "Bu fikir sence tutar mı?",
        "Giriş ekranı nasıl olmalı sence?",
        "2 3",
    ]
    work = [
        "tamam",
        "olur başla",
        "evet",
        "README'ye kurulum ekle",
        "Rakipleri araştır",
        "Uygulamayı yapalım",
        "x" * 700,  # a pasted spec
    ]
    assert all(intent.is_light(t) for t in talk)
    assert not any(intent.is_light(t) for t in work)
    assert not intent.is_light("Merhaba", attachments=["abc"])  # attachments are work


def test_plain_talk_is_light(client, rec):
    chat_id = new_chat(client)
    m = turn(client, chat_id, "Aklımda bir uygulama fikri var, birlikte netleştirelim")
    req = rec.requests[-1]
    assert (req.model, req.effort) == ("sonnet", "low")
    assert req.agents is None and "Agent" not in req.tools and "Write" not in req.tools
    assert "HAFİF SOHBET TURU" in req.prompt
    assert m["meta"]["team"]["lead"]["model"] == "Sonnet"


def test_work_gets_the_full_plan(client, rec):
    chat_id = new_chat(client)
    turn(client, chat_id, "Rakipleri araştır")
    req = rec.requests[-1]
    assert (req.model, req.effort) == ("opus", "high") and "Agent" in req.tools
    assert "HAFİF SOHBET TURU" not in req.prompt


def test_the_users_pick_is_kept_for_the_chat(client, rec):
    chat_id = new_chat(client)
    r = client.post(
        f"/api/chats/{chat_id}/messages", json={"content": "Merhaba", "model_choice": "haiku"}
    )
    assert r.json()["chat"]["model_choice"] == "haiku"
    from tests.helpers import wait_msg

    wait_msg(client, chat_id, r.json()["messages"][1]["id"])
    turn(client, chat_id, "Rakipleri araştır")  # no pick sent: the chat's pick stays
    for req in rec.requests:
        assert (req.model, req.effort) == ("haiku", "low")
    assert "Agent" in rec.requests[-1].tools  # a pick changes the model, not the abilities
    assert chat_state(client, chat_id)["chat"]["model_choice"] == "haiku"
    assert (
        client.post(
            f"/api/chats/{chat_id}/messages", json={"content": "x", "model_choice": "gpt"}
        ).status_code
        == 422
    )


class HandsBack(Recorder):
    """A light turn that decides the message really is work."""

    info = replace(MockAdapter.info, id="claude_code", name="Claude")

    async def run(self, req, run_id):
        if "HAFİF SOHBET TURU" in req.prompt:
            self.requests.append(req)
            for part in ("[[ORBIT", ":TAM_GUC]]"):
                yield AdapterEvent("delta", {"text": part})
            yield AdapterEvent("result", {"text": intent.ESCALATE})
            return
        async for ev in super().run(req, run_id):
            yield ev


def test_a_misjudged_turn_is_redone_at_full_power_without_showing_the_marker(client):
    lead = HandsBack()
    original = use(lead)
    seen = broker.subscribe()
    try:
        p = project(client)
        chat_id = new_chat(client, p["id"])
        m = turn(client, chat_id, "Şunu bir halledelim mi", p["id"])
        light, full = lead.requests
        assert light.model == "sonnet" and full.model == "opus"
        assert full.resume == light.session_id  # same conversation
        assert "Agent" in full.tools and "HAFİF SOHBET TURU" not in full.prompt
        assert intent.ESCALATE not in m["content"]
        deltas = []
        while not seen.empty():
            ev = seen.get_nowait()
            if ev["type"] == "message_delta" and ev["message_id"] == m["id"]:
                deltas.append(ev["text"])
        assert "ORBIT" not in "".join(deltas) and deltas  # the marker never reached the screen
    finally:
        broker.unsubscribe(seen)
        registry._adapters = original
        registry._health.clear()
