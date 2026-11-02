"""One chat, one assistant: the message alone decides what happens."""

import time
from dataclasses import replace

from acc import assistant
from acc.adapters import registry
from acc.adapters.base import SessionLost
from acc.adapters.mock import MockAdapter
from tests.helpers import (  # noqa: F401
    Recorder,
    chat_state,
    new_chat,
    project,
    send,
    turn,
    use,
    wait_msg,
)


def test_reply_streams_and_completes(client, rec):
    chat_id = new_chat(client)
    m = turn(client, chat_id, "Rakipleri araştır")
    assert m["content"].startswith("Demo yanıtı") and m["adapter_id"] == "mock"
    state = chat_state(client, chat_id)
    assert state["chat"]["title"] == "Rakipleri araştır"
    assert state["tasks"] == []  # just talking creates nothing to review
    req = rec.requests[-1]
    assert req.system_prompt.startswith("Sen Orbit'sin") and "EKİP" in req.system_prompt
    assert req.effort == "high"
    assert req.prompt.endswith("KULLANICININ MESAJI:\nRakipleri araştır")


def test_without_project_the_assistant_gets_web_and_a_scratch_folder(client, rec):
    chat_id = new_chat(client)
    turn(client, chat_id, "Bir rapor yaz")
    req = rec.requests[-1]
    assert req.tools == [*assistant.SCRATCH_TOOLS, "Agent"] and "Bash" not in req.tools
    assert set(req.agents) == {"kesifci", "arastirmaci", "tasarimci"}
    assert req.settings is None  # no shell, so no sandbox needed
    assert req.cwd.name == str(chat_id) and req.cwd.is_dir()
    assert req.output_dir is not None and req.output_dir.is_dir()
    assert "ÇIKTI KLASÖRÜ" in req.prompt


def test_history_is_sent_when_the_model_cannot_resume(client, rec):
    chat_id = new_chat(client)
    turn(client, chat_id, "Uygulamanın adı Kuzey olsun")
    turn(client, chat_id, "Adı neydi?")
    prompt = rec.requests[-1].prompt
    assert "SOHBET GEÇMİŞİ" in prompt and "Kuzey" in prompt
    assert rec.requests[-1].resume is None and rec.requests[-1].session_id is None


def test_cancel_keeps_partial_answer_and_blocks_overlap(client, slow):
    chat_id = new_chat(client)
    msg_id = send(client, chat_id, "Uzun bir yanıt ver")
    time.sleep(0.35)  # a few chunks arrive
    r = client.post(f"/api/chats/{chat_id}/messages", json={"content": "x"})
    assert r.status_code == 409  # one reply at a time
    assert client.post(f"/api/messages/{msg_id}/cancel").status_code == 200
    m = wait_msg(client, chat_id, msg_id, "cancelled")
    assert m["content"].startswith("Demo yanıtı") and m["content"].endswith("_(durduruldu)_")


def test_streaming_chat_cannot_be_deleted(client, slow):
    chat_id = new_chat(client)
    msg_id = send(client, chat_id, "Uzun bir yanıt ver")
    assert client.delete(f"/api/chats/{chat_id}").status_code == 409
    client.post(f"/api/messages/{msg_id}/cancel")
    wait_msg(client, chat_id, msg_id, "cancelled")
    assert client.delete(f"/api/chats/{chat_id}").status_code == 204


def test_unknown_project_is_refused(client):
    chat_id = new_chat(client)
    r = client.post(f"/api/chats/{chat_id}/messages", json={"content": "x", "project_id": 99999})
    assert r.status_code == 400


def test_quality_preference_sets_effort(client, rec):
    assert client.put("/api/preferences/quality", json={"value": "best"}).status_code == 200
    try:
        turn(client, new_chat(client), "Detaylı araştır")
        assert rec.requests[-1].effort == "xhigh"
    finally:
        client.put("/api/preferences/quality", json={"value": "balanced"})
    assert client.put("/api/preferences/quality", json={"value": "turbo"}).status_code == 400


def test_templates_have_no_modes(client):
    items = client.get("/api/templates").json()
    assert {"b-market", "b-design", "b-bug"} <= {t["id"] for t in items}
    assert all("mode" not in t for t in items)


class _Claude(Recorder):
    """Wears Claude Code's id; forgets its conversations when asked to."""

    info = replace(MockAdapter.info, id="claude_code", name="Claude Code")

    def __init__(self):
        super().__init__()
        self.forget = False

    async def run(self, req, run_id):
        if req.resume and self.forget:
            self.requests.append(req)
            raise SessionLost("No conversation found")
        async for ev in super().run(req, run_id):
            yield ev


def test_claude_keeps_its_own_conversation_and_rebuilds_a_lost_one(client):
    claude = _Claude()
    original = use(claude)
    try:
        chat_id = new_chat(client)
        turn(client, chat_id, "Uygulamanın adı Kuzey olsun")
        first = claude.requests[-1]
        assert first.session_id and first.resume is None
        turn(client, chat_id, "Adı neydi?")
        second = claude.requests[-1]
        assert second.resume == first.session_id and second.session_id is None
        assert "SOHBET GEÇMİŞİ" not in second.prompt  # Claude remembers by itself

        claude.forget = True
        m = turn(client, chat_id, "Rengi ne olsun?")
        assert m["content"].startswith("Demo yanıtı")
        rebuilt = claude.requests[-1]
        assert rebuilt.resume is None and rebuilt.session_id != first.session_id
        assert "SOHBET GEÇMİŞİ" in rebuilt.prompt and "Kuzey" in rebuilt.prompt
        claude.forget = False
        turn(client, chat_id, "Tamam")
        assert claude.requests[-1].resume == rebuilt.session_id
    finally:
        registry._adapters = original
        registry._health.clear()


def test_a_turn_that_breaks_early_ends_as_an_error_not_stuck(client, monkeypatch):
    from acc.api import chat_service

    async def boom(*a, **k):
        raise RuntimeError("erken hata")

    monkeypatch.setattr(chat_service.router, "pick", boom)
    chat_id = new_chat(client)
    m = wait_msg(client, chat_id, send(client, chat_id, "Merhaba"), "error")
    assert "erken hata" in m["content"]


def test_picking_a_model_keeps_claudes_own_conversation(client):
    claude = _Claude()
    original = use(claude)
    try:
        chat_id = new_chat(client)
        pick = {"model_choice": "claude_code/claude-opus-5-5", "effort_choice": "high"}
        for text in ("Uygulamanın adı Kuzey olsun", "Adı neydi?"):
            r = client.post(f"/api/chats/{chat_id}/messages", json={"content": text, **pick})
            wait_msg(client, chat_id, r.json()["messages"][1]["id"])
        first, second = claude.requests
        assert second.resume == first.session_id and "SOHBET GEÇMİŞİ" not in second.prompt
    finally:
        registry._adapters = original
        registry._health.clear()
