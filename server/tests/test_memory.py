import pytest

from acc import chat as chat_module
from acc.adapters import registry
from acc.adapters.ollama import OllamaAdapter
from tests.test_chat import _Recorder, _say, _wait_msg
from tests.test_execution import _project, _to_review, _wait
from tests.test_ollama import fake_ollama


@pytest.fixture
def rec():
    original = registry._adapters
    r = _Recorder()
    registry._adapters = {"mock": r}
    registry._health.clear()
    yield r
    registry._adapters = original


def test_memory_roundtrip_and_prompts(client, rec):
    p = _project(client)
    m = client.get(f"/api/projects/{p['id']}/memory").json()
    assert "## Karar Günlüğü" in m["content"] and m["path"].endswith(".md")
    text = m["content"].replace(
        "## Notlar\n", "## Notlar\n- Arayüz dili Türkçe, tasarım siyah-beyaz.\n"
    )
    assert client.put(f"/api/projects/{p['id']}/memory", json={"content": text}).status_code == 200

    chat = client.post("/api/chats", json={"project_id": p["id"]}).json()
    out = _say(client, chat["id"], "Merhaba", project_id=p["id"])
    _wait_msg(client, chat["id"], out["messages"][1]["id"], "done")
    assert "PROJE HAFIZASI" in rec.requests[-1].prompt
    assert "siyah-beyaz" in rec.requests[-1].prompt

    # The planner and every agent step see it too.
    _, task_id, _ = _to_review(client, p)
    prompts = [r.prompt for r in rec.requests if r.json_schema or not r.stream_text]
    assert all("siyah-beyaz" in pr for pr in prompts[-4:])


def test_merge_appends_decision_log(client, rec):
    p = _project(client)
    chat_id, task_id, _ = _to_review(client, p)
    client.post(f"/api/tasks/{task_id}/decision", json={"decision": "approve"})
    _wait(client, chat_id, task_id, "completed")
    content = client.get(f"/api/projects/{p['id']}/memory").json()["content"]
    log = content.split("## Karar Günlüğü", 1)[1]
    assert f"Görev #{task_id}" in log and "ORBIT_DEMO.md" in log


def test_long_chat_is_summarised(client, rec, monkeypatch):
    monkeypatch.setattr(chat_module, "COMPACT_AT", 300)
    monkeypatch.setattr(chat_module, "KEEP_RECENT", 2)
    chat = client.post("/api/chats", json={}).json()
    for i in range(4):
        out = _say(client, chat["id"], f"Mesaj {i}: " + "uzun ayrıntı " * 10)
        _wait_msg(client, chat["id"], out["messages"][1]["id"], "done")
    last_prompt = rec.requests[-1].prompt
    assert "ÖNCEKİ KONUŞMANIN ÖZETİ" in last_prompt
    assert "Mesaj 0:" not in last_prompt  # folded into the summary, not resent
    assert "Mesaj 3:" in last_prompt
    summaries = [r for r in rec.requests if r.tools == [] and not r.stream_text]
    assert summaries, "a summarising run happened"


def test_chat_with_local_model_gets_no_tools(client):
    seen = []
    original = registry._adapters
    registry._adapters = {"ollama": OllamaAdapter(transport=fake_ollama(seen=seen))}
    registry._health.clear()
    try:
        p = _project(client)
        chat = client.post("/api/chats", json={"project_id": p["id"]}).json()
        r = client.post(
            f"/api/chats/{chat['id']}/messages",
            json={"content": "Selam", "mode": "chat", "model": "ollama", "project_id": p["id"]},
        )
        msg = _wait_msg(client, chat["id"], r.json()["messages"][1]["id"], "done")
        assert msg["content"] == "Merhaba!" and msg["adapter_id"] == "ollama"
        user_turn = seen[-1]["messages"][-1]["content"]
        assert "yerel bir model" in user_turn  # it is told it can't read files
        bad = client.post(
            f"/api/chats/{chat['id']}/messages",
            json={"content": "x", "mode": "chat", "model": "yok"},
        )
        assert bad.status_code == 400
    finally:
        registry._adapters = original
