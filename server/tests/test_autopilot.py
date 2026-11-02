"""Otopilot: the team moves through the card's phases on its own, and stops for good reasons."""

import time
from pathlib import Path

from acc import autopilot, card
from acc.db import session
from acc.models import Chat
from tests.helpers import chat_state, git, new_chat, project

CARD = """# Sayaç

## Ekip
| Alan | Teknoloji | Klasör | Yapan |
|---|---|---|---|
| Web | HTML | web/ | Claude |

## Aşamalar
- [ ] 1. İskelet — kabul: sayfa açılır
- [ ] 2. Sayaç — kabul: artır düğmesi çalışır
- [ ] 3. Kayıt — kabul: yenileyince sayı kalır

## Kararlar
- [ ] bu bir karar, aşama değil
"""

P = [{"title": "a", "done": True}, {"title": "b", "done": False}, {"title": "c", "done": False}]
NONE = [{**p, "done": False} for p in P]


def go(**kw):
    args = {
        "changed": True,
        "checks": [{"name": "test", "status": "passed"}],
        "review": None,
        "before": NONE,
        "after": P,
        "quota": 0.3,
    }
    return autopilot.decide(**{**args, **kw})


def test_it_goes_on_only_when_the_turn_measurably_finished_a_phase():
    d = go()
    assert d.go and d.phase == "2/3"
    assert not go(changed=False).go
    failed = go(checks=[{"name": "lint", "status": "failed"}])
    assert not failed.go and "lint" in failed.reason
    assert go(checks=[{"name": "test", "status": "skipped"}]).go  # no sandbox is not a failure
    serious = {"issues": [{"onem": "yuksek"}], "fixed": False}
    assert not go(review=serious).go
    assert go(review={**serious, "fixed": True}).go
    assert go(review={"issues": [{"onem": "dusuk"}], "fixed": False}).go
    assert not go(before=P).go  # no new box ticked: the lead is waiting for the user
    assert "tamamlandı" in go(after=[{**p, "done": True} for p in P]).reason
    assert not go(after=[]).go
    assert "kota" in go(quota=0.9).reason
    assert go(quota=None).go  # unknown quota doesn't block


def test_phases_are_the_top_level_boxes_of_the_phase_section():
    got = card.phases(CARD + "\n## AŞAMALAR 2\n")
    assert [p["title"][:2] for p in got] == ["1.", "2.", "3."]
    nested = "## Aşamalar\n- [x] a\n  - [ ] alt adım\n#### not\n- [ ] b\n## Son\n- [ ] c\n"
    assert card.phases(nested) == [{"title": "a", "done": True}, {"title": "b", "done": False}]
    assert card.phases(None) == [] and card.phases("## Aşamalar\n1. düz liste\n") == []


def _project_with_card(client) -> dict:
    p = project(client)
    (Path(p["path"]) / "PROJE.md").write_text(CARD)
    git(p["path"], "add", "-A")
    git(p["path"], "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "kart")
    return p


def _settle(client, chat_id, timeout=30) -> list[dict]:
    """Waits until no reply is being written and none is about to start."""
    deadline = time.time() + timeout
    calm = 0
    while time.time() < deadline:
        msgs = chat_state(client, chat_id)["messages"]
        calm = calm + 1 if not any(m["status"] == "streaming" for m in msgs) else 0
        if calm >= 3:
            return msgs
        time.sleep(0.3)
    raise AssertionError("sohbet durulmadı")


def _left(chat_id) -> int:
    with session() as s:
        return s.get(Chat, chat_id).autopilot_left


def test_otopilot_runs_the_phases_and_stops_when_the_card_is_done(client):
    p = _project_with_card(client)
    chat_id = new_chat(client, p["id"])
    r = client.put(f"/api/chats/{chat_id}/autopilot", json={"on": True})
    assert r.json()["autopilot_left"] == autopilot.TURNS
    client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": "Kart onaylı, başla", "project_id": p["id"]},
    )
    msgs = _settle(client, chat_id)
    auto = [m for m in msgs if m["role"] == "user" and (m["meta"] or {}).get("autopilot")]
    assert [m["meta"]["phase"] for m in auto] == ["2/3", "3/3"]
    replies = [m for m in msgs if m["role"] == "assistant"]
    assert all(m["status"] == "done" for m in replies)
    assert replies[0]["meta"]["autopilot"]["go"] is True
    last = replies[-1]["meta"]["autopilot"]
    assert last["go"] is False and "tamamlandı" in last["reason"]
    assert _left(chat_id) == 0  # switched itself off
    phases = client.get(f"/api/projects/{p['id']}/card").json()["phases"]
    assert all(ph["done"] for ph in phases) and len(phases) == 3


def test_otopilot_keeps_to_its_turn_budget(client):
    p = _project_with_card(client)
    chat_id = new_chat(client, p["id"])
    with session() as s:
        s.get(Chat, chat_id).autopilot_left = 1  # one automatic turn left
    client.post(f"/api/chats/{chat_id}/messages", json={"content": "başla", "project_id": p["id"]})
    msgs = _settle(client, chat_id)
    replies = [m for m in msgs if m["role"] == "assistant"]
    assert len(replies) == 2  # the user's turn and exactly one automatic one
    assert "sınırı doldu" in replies[-1]["meta"]["autopilot"]["reason"]
    assert _left(chat_id) == 0


def test_without_otopilot_nothing_starts_by_itself(client):
    p = _project_with_card(client)
    chat_id = new_chat(client, p["id"])
    client.post(
        f"/api/chats/{chat_id}/messages", json={"content": "Bir satır ekle", "project_id": p["id"]}
    )
    msgs = _settle(client, chat_id)
    assert len(msgs) == 2 and "autopilot" not in (msgs[1]["meta"] or {})
    r = client.put(f"/api/chats/{chat_id}/autopilot", json={"on": False})
    assert r.json()["autopilot_left"] == 0
    assert client.put("/api/chats/999999/autopilot", json={"on": True}).status_code == 404


def test_stopping_sends_a_notification(client, monkeypatch):
    from acc import notify

    sent = []
    monkeypatch.setattr(notify, "send", lambda title, body, force=False: sent.append(body))
    p = _project_with_card(client)
    chat_id = new_chat(client, p["id"])
    client.put(f"/api/chats/{chat_id}/autopilot", json={"on": True})
    client.post(f"/api/chats/{chat_id}/messages", json={"content": "başla", "project_id": p["id"]})
    _settle(client, chat_id)
    assert len(sent) == 1 and "tamamlandı" in sent[0]  # once, when it stopped


def test_a_restart_breaks_the_chain_and_clears_leftovers(client):
    from acc import config
    from acc.api import chat_service
    from acc.models import Message

    chat_id = new_chat(client)
    runs = config.DATA_DIR / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "1-codex.jsonl").write_text("{}")
    with session() as s:
        s.get(Chat, chat_id).autopilot_left = 4
        s.add(Message(chat_id=chat_id, role="assistant", content="", status="streaming"))
    chat_service.recover()
    assert _left(chat_id) == 0 and not runs.exists()
