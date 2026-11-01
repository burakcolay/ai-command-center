import base64
import struct
import time

import pytest

from acc import attachments, config
from tests.test_chat import _wait_msg
from tests.test_execution import _project, _wait
from tests.test_memory import rec  # noqa: F401  (fixture)

# Smallest valid PNG (1x1, transparent).
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _upload(client, data: bytes, name="ekran.png"):
    return client.post("/api/uploads", json={"name": name, "data": base64.b64encode(data).decode()})


def test_uploads_accept_only_real_images(client):
    r = _upload(client, PNG)
    assert r.status_code == 201 and r.json()["mime"] == "image/png"
    assert client.get(f"/api/uploads/{r.json()['id']}").content == PNG
    # A text file named .png is refused: the bytes decide, not the name.
    assert _upload(client, b"<script>alert(1)</script>", "kotu.png").status_code == 400
    assert _upload(client, b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024)).status_code == 400
    # Path traversal never reaches Orbit's database: plain "../" is normalised away by the
    # client (and lands on the UI page), encoded slashes fail the id check.
    assert b"SQLite format" not in client.get("/api/uploads/../../acc.db").content
    assert client.get("/api/uploads/..%2F..%2Facc.db").status_code == 404
    assert client.get("/api/designs/1/..%2F..%2Facc.db.png").status_code == 404
    assert client.get("/api/uploads/" + "0" * 32).status_code == 404


def test_chat_attachment_reaches_the_model(client, rec):  # noqa: F811
    upload_id = _upload(client, PNG).json()["id"]
    chat = client.post("/api/chats", json={}).json()
    r = client.post(
        f"/api/chats/{chat['id']}/messages",
        json={"content": "Bu ekranı yorumla", "mode": "chat", "attachments": [upload_id]},
    )
    assert r.status_code == 201
    assert r.json()["messages"][0]["meta"] == {"attachments": [upload_id]}
    _wait_msg(client, chat["id"], r.json()["messages"][1]["id"], "done")
    req = rec.requests[-1]
    assert str(attachments.upload_path(upload_id)) in req.prompt
    assert "Read" in req.tools and config.UPLOADS_DIR in req.read_dirs
    bad = client.post(
        f"/api/chats/{chat['id']}/messages",
        json={"content": "x", "mode": "chat", "attachments": ["yok"]},
    )
    assert bad.status_code == 400


def _png_size(path):
    w, h = struct.unpack(">II", path.read_bytes()[16:24])
    return w, h


def test_design_mode_renders_variants_and_feeds_an_edit(client):
    p = _project(client)
    chat = client.post("/api/chats", json={"project_id": p["id"]}).json()
    r = client.post(
        f"/api/chats/{chat['id']}/messages",
        json={"content": "Giriş ekranı için 3 fikir", "mode": "design", "project_id": p["id"]},
    )
    msg = _wait_msg(client, chat["id"], r.json()["messages"][1]["id"], "done", timeout=30)
    variants = msg["meta"]["variants"]
    assert [v["title"] for v in variants] == ["Sade", "Kartlı", "Yoğun"]
    assert "1. **Sade**" in msg["content"]  # kept in history so "2'yi seç" makes sense later
    if variants[0]["image"] is None:
        pytest.skip("Chromium not available for rendering")
    png = client.get(variants[0]["image"])
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    shot = config.DESIGNS_DIR / str(msg["id"]) / "v1.png"
    assert _png_size(shot) == (393 * 2, 852 * 2)

    # Picking a variant: it travels to the edit session as an attachment (PNG + HTML).
    edit = client.post(
        f"/api/chats/{chat['id']}/messages",
        json={
            "content": "Tasarım 2'yi uygula",
            "mode": "edit",
            "attachments": [variants[1]["attachment"]],
        },
    ).json()["task"]
    assert edit["kind"] == "session"
    time.sleep(0.05)
    _wait(client, chat["id"], edit["id"], "waiting_approval", "merge")


def test_second_design_round_sees_the_first(client, rec):  # noqa: F811
    chat = client.post("/api/chats", json={}).json()
    first = client.post(
        f"/api/chats/{chat['id']}/messages", json={"content": "3 fikir", "mode": "design"}
    ).json()
    _wait_msg(client, chat["id"], first["messages"][1]["id"], "done", timeout=30)
    second = client.post(
        f"/api/chats/{chat['id']}/messages",
        json={"content": "2'nin düzeni 1'in renkleri", "mode": "design"},
    ).json()
    _wait_msg(client, chat["id"], second["messages"][1]["id"], "done", timeout=30)
    prompt = [
        r for r in rec.requests if r.json_schema and "variants" in r.json_schema["properties"]
    ][-1].prompt
    assert "ÖNCEKİ TASARIMLAR" in prompt and f"tur #{first['messages'][1]['id']}" in prompt
