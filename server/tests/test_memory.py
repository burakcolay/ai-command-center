"""Project memory, the decision log, long-chat summaries and the local fallback."""

from acc import chat as chat_module
from acc.adapters.ollama import OllamaAdapter
from tests.helpers import (  # noqa: F401
    decide,
    new_chat,
    project,
    send,
    turn,
    use,
    wait_msg,
)
from tests.test_ollama import fake_ollama


def test_memory_roundtrip_and_prompts(client, rec):
    p = project(client)
    m = client.get(f"/api/projects/{p['id']}/memory").json()
    assert "## Karar Günlüğü" in m["content"] and m["path"].endswith(".md")
    text = m["content"].replace(
        "## Notlar\n", "## Notlar\n- Arayüz dili Türkçe, tasarım siyah-beyaz.\n"
    )
    assert client.put(f"/api/projects/{p['id']}/memory", json={"content": text}).status_code == 200
    chat_id = new_chat(client, p["id"])
    turn(client, chat_id, "Merhaba", p["id"])
    turn(client, chat_id, "Bir satır ekle")
    assert all("PROJE HAFIZASI" in r.prompt and "siyah-beyaz" in r.prompt for r in rec.requests)


def test_merge_appends_decision_log(client):
    p = project(client)
    chat_id = new_chat(client, p["id"])
    task_id = turn(client, chat_id, "Karşılama satırı ekle", p["id"])["meta"]["task_id"]
    assert decide(client, task_id, "approve").status_code == 200
    log = client.get(f"/api/projects/{p['id']}/memory").json()["content"]
    log = log.split("## Karar Günlüğü", 1)[1]
    assert "Karşılama satırı ekle" in log


def test_long_chat_is_summarised(client, rec, monkeypatch):
    monkeypatch.setattr(chat_module, "COMPACT_AT", 300)
    monkeypatch.setattr(chat_module, "KEEP_RECENT", 2)
    chat_id = new_chat(client)
    for i in range(4):
        turn(client, chat_id, f"Mesaj {i}: " + "uzun ayrıntı " * 10)
    last_prompt = rec.requests[-1].prompt
    assert "ÖNCEKİ KONUŞMANIN ÖZETİ" in last_prompt
    assert "Mesaj 0:" not in last_prompt  # folded into the summary, not resent
    assert "Mesaj 3:" in last_prompt
    assert any(r.tools == [] for r in rec.requests), "a summarising run happened"


def test_without_claude_a_local_model_keeps_talking(client):
    from acc.adapters import registry

    seen = []
    original = use(OllamaAdapter(transport=fake_ollama(seen=seen)))
    try:
        p = project(client)
        chat_id = new_chat(client, p["id"])
        msg = turn(client, chat_id, "Selam, bir satır ekle", p["id"])
        assert msg["content"] == "Merhaba!" and msg["adapter_id"] == "ollama"
        assert "yerel model" in seen[-1]["messages"][-1]["content"]  # told it can't edit
        assert client.get(f"/api/chats/{chat_id}").json()["tasks"] == []  # no copy opened
    finally:
        registry._adapters = original
        registry._health.clear()


def test_no_model_at_all_is_a_clear_error(client):
    from acc.adapters import registry

    original = use()
    try:
        chat_id = new_chat(client)
        m = wait_msg(client, chat_id, send(client, chat_id, "Selam"), "error")
        assert "Yanıt verecek model yok" in m["content"]
    finally:
        registry._adapters = original
        registry._health.clear()
