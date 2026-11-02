"""Uploads and design variants, both arriving through the normal chat."""

import base64
import struct
import zlib

import pytest

from acc import attachments, config, designs
from tests.helpers import new_chat, project, send, task, turn, wait_msg  # noqa: F401

# Smallest valid PNG (1x1, transparent).
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _upload(client, data: bytes, name="ekran.png"):
    return client.post("/api/uploads", json={"name": name, "data": base64.b64encode(data).decode()})


def _png_size(path):
    w, h = struct.unpack(">II", path.read_bytes()[16:24])
    return w, h


def _top_left_rgb(path):
    """First pixel of a PNG. Every row filter leaves the very first pixel unchanged."""
    data, pos, idat = path.read_bytes(), 8, b""
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        if data[pos + 4 : pos + 8] == b"IDAT":
            idat += data[pos + 8 : pos + 8 + length]
        pos += 12 + length
    raw = zlib.decompressobj().decompress(idat, 16)
    return tuple(raw[1:4])  # skip the row's filter byte


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


def test_attachment_reaches_the_model(client, rec):
    upload_id = _upload(client, PNG).json()["id"]
    chat_id = new_chat(client)
    r = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": "Bu ekranı yorumla", "attachments": [upload_id]},
    )
    assert r.status_code == 201
    meta = r.json()["messages"][0]["meta"]
    assert meta["attachments"] == [upload_id]
    assert meta["files"] == [{"id": upload_id, "kind": "image", "name": "ekran.png"}]
    wait_msg(client, chat_id, r.json()["messages"][1]["id"])
    turn(client, chat_id, "Peki ya renkler?")
    first = rec.requests[0]
    assert str(attachments.upload_path(upload_id)) in first.prompt
    assert "Read" in first.tools and config.UPLOADS_DIR in first.read_dirs
    bad = client.post(
        f"/api/chats/{chat_id}/messages", json={"content": "x", "attachments": ["yok"]}
    )
    assert bad.status_code == 400


def test_header_comment_gives_title_idea_and_viewport(tmp_path):
    (tmp_path / "tasarim-1.html").write_text(
        "<!-- başlık: Kartlar | fikir: Göz atmak için. | görünüm: tablet -->\n<p>x</p>"
    )
    (tmp_path / "tasarim-2.html").write_text("<title>Liste</title><p>y</p>")
    (tmp_path / "tasarim-3.html").write_text("<!-- görünüm: tv --><p>z</p>")
    v = designs.collect(tmp_path)
    assert [(x["title"], x["viewport"]) for x in v] == [
        ("Kartlar", "tablet"),
        ("Liste", "phone"),
        ("Tasarım 3", "phone"),
    ]
    assert v[0]["idea"] == "Göz atmak için."


def test_asking_for_designs_renders_them_and_one_can_be_applied(client):
    p = project(client)
    chat_id = new_chat(client, p["id"])
    msg = turn(client, chat_id, "Giriş ekranı için 3 farklı tasarım", p["id"])
    variants = msg["meta"]["variants"]
    assert [v["title"] for v in variants] == ["Sade", "Kartlı", "Yoğun"]
    assert "task_id" not in msg["meta"]  # designs live outside the project copy
    if variants[0]["image"] is None:
        pytest.skip("Chromium not available for rendering")
    png = client.get(variants[0]["image"])
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    shot = config.DESIGNS_DIR / str(msg["id"]) / "v1.png"
    assert _png_size(shot) == (393 * 2, 852 * 2)
    # JavaScript in a design never runs: the demo page tries to turn the background red.
    assert _top_left_rgb(shot) == (0, 0, 0)

    # Picking one is just another message with the design attached.
    applied = turn(
        client, chat_id, "2. seçeneği projeye ekle", attachments=[variants[1]["attachment"]]
    )
    t = task(client, chat_id, applied["meta"]["task_id"])
    assert t["status"] == "waiting_approval" and t["steps"]


def test_a_second_round_sees_the_first(client, rec):
    chat_id = new_chat(client)
    first = turn(client, chat_id, "Ayarlar ekranı için tasarım")
    turn(client, chat_id, "2'nin düzeni 1'in renkleri olsun, yeni tasarım")
    prompt = rec.requests[-1].prompt
    assert "ÖNCEKİ TASARIMLAR" in prompt and f"tur #{first['id']}" in prompt
