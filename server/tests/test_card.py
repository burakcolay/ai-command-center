"""Project Card, area specialists, the Codex bridge, and spec files as attachments."""

import base64
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from acc import assistant, card, mcp_codex, prefs
from acc.adapters import registry
from acc.adapters.base import AdapterEvent, Health, ModelState
from acc.adapters.mock import MockAdapter
from tests.helpers import Recorder, git, new_chat, project, turn, use, wait_msg

CARD = """# Sayaç

## Amaç
Basit bir sayaç.

## Ekip
| Alan | Teknoloji | Klasör | Yapan |
|---|---|---|---|
| Backend | FastAPI (Python) | `server/` | Codex |
| Frontend | React + TypeScript | web/ | Claude |

## API sözleşmesi
GET /sayac -> {"deger": int}
"""

FAKE_CODEX = r"""#!{python}
import json, os, sys
args = sys.argv[1:]
if args[:2] == ["login", "status"]:
    print("Logged in using ChatGPT"); sys.exit(0)
task = sys.stdin.read()
cwd = args[args.index("-C") + 1]
if os.environ.get("FAKE_CODEX_LOG"):
    open(os.environ["FAKE_CODEX_LOG"], "a").write(json.dumps(args) + "\n")
def out(o): print(json.dumps(o), flush=True)
out({{"type": "thread.started", "thread_id": "t"}})
if os.environ.get("FAKE_CODEX_QUOTA"):
    out({{"type": "error", "message": "You've hit your usage limit. Try again in 1 hours."}})
    sys.exit(1)
open(os.path.join(cwd, "codex_yazdi.txt"), "w").write(task[-200:])
out({{"type": "item.completed", "item": {{"id": "f", "type": "file_change",
     "changes": [{{"path": "codex_yazdi.txt", "kind": "add"}}]}}}})
out({{"type": "item.completed", "item": {{"id": "m", "type": "agent_message", "text": "Yaptım."}}}})
out({{"type": "turn.completed", "usage": {{}}}})
"""


@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    cli = tmp_path / "codex"
    cli.write_text(FAKE_CODEX.format(python=sys.executable))
    cli.chmod(0o755)
    monkeypatch.setenv("ACC_CODEX", str(cli))
    return cli


@pytest.fixture
def quality(client):
    yield lambda v: prefs.put("quality", v)
    prefs.put("quality", "balanced")


# ---------- spec files ----------


def _upload(client, data: bytes, name: str):
    return client.post("/api/uploads", json={"name": name, "data": base64.b64encode(data).decode()})


def test_a_markdown_spec_can_be_attached(client):
    spec = "# Uygulama fikri\n\nSu içmeyi hatırlatan bir iOS uygulaması.\n".encode()
    r = _upload(client, spec, "fikir.md")
    assert r.status_code == 201 and r.json()["mime"] == "text/markdown"
    got = client.get(f"/api/uploads/{r.json()['id']}")
    assert got.content == spec
    assert got.headers["content-type"].startswith("text/plain")  # never rendered as a page
    assert got.headers["x-content-type-options"] == "nosniff"

    assert _upload(client, b"\x00\x01binary", "kotu.md").status_code == 400
    assert _upload(client, b"x" * (1024 * 1024 + 1), "buyuk.md").status_code == 400
    assert _upload(client, b"echo hi", "betik.sh").status_code == 400


def test_the_spec_reaches_the_assistant(client, rec):
    upload_id = _upload(client, b"# Fikir\nSayac", "fikir.md").json()["id"]
    chat_id = new_chat(client)
    r = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": "Bu fikirle başlayalım", "attachments": [upload_id]},
    )
    assert r.json()["messages"][0]["meta"]["files"] == [
        {"id": upload_id, "kind": "text", "name": "fikir.md"}
    ]
    wait_msg(client, chat_id, r.json()["messages"][1]["id"])
    assert "metin dosyası" in rec.requests[-1].prompt


# ---------- the card ----------


def test_team_table_is_read():
    areas = card.team(CARD)
    assert [(a.name, a.tech, a.folder, a.builder) for a in areas] == [
        ("Backend", "FastAPI (Python)", "server/", "codex"),
        ("Frontend", "React + TypeScript", "web/", "claude"),
    ]
    assert card.team("# Kart\nEkip tablosu yok") == []
    assert card.team(None) == []


def test_no_card_means_no_area_specialists(quality):
    plan = assistant.setup(assistant.PROJECT_TOOLS, None, codex=True, cwd=Path("/tmp"))
    assert not any(n.endswith(("-gelistirici", "-codex")) for n in plan.agents)
    assert plan.mcp is None
    assert "PROJE.md" in plan.system  # but the lead knows to write one for big work


def test_specialists_come_from_the_card_and_read_it_first(quality):
    plan = assistant.setup(assistant.PROJECT_TOOLS, CARD, codex=False, cwd=Path("/tmp/wt"))
    backend = plan.agents["backend-gelistirici"]
    assert "FastAPI (Python)" in backend["prompt"] and "server/" in backend["prompt"]
    assert "Projeyi anlamadan tek satır" in backend["prompt"]
    assert "GET /sayac" in backend["prompt"]  # the card itself is in its instructions
    assert backend["model"] == "sonnet"  # builders: lighter on the quota on "balanced"
    assert "backend-codex" not in plan.agents and plan.mcp is None
    assert "Codex kurulunca" in plan.system

    quality("best")
    best = assistant.setup(assistant.PROJECT_TOOLS, CARD, codex=False, cwd=Path("/tmp/wt"))
    assert best.agents["backend-gelistirici"]["model"] == "opus"  # güçlü · medium
    assert best.agents["backend-gelistirici"]["effort"] == "medium"
    quality("economy")
    assert assistant.setup(assistant.PROJECT_TOOLS, CARD).agents is None
    quality("balanced")
    read_only = assistant.setup(assistant.READ_ONLY_TOOLS, CARD)
    assert not any(n.endswith("-gelistirici") for n in read_only.agents)


def test_codex_builds_its_area_through_the_bridge(quality):
    wt = Path("/tmp/wt")
    plan = assistant.setup(assistant.PROJECT_TOOLS, CARD, codex=True, cwd=wt)
    coordinator = plan.agents["backend-codex"]
    assert coordinator["tools"] == ["Read", "Glob", "Grep", mcp_codex.FULL_NAME]
    assert "backend-gelistirici" in plan.agents  # Claude can take over if Codex can't
    assert "frontend-codex" not in plan.agents
    assert mcp_codex.FULL_NAME in plan.tools and "aynı anda" in plan.system
    server = plan.mcp["mcpServers"]["orbit"]
    assert server["command"] == sys.executable
    assert server["args"][server["args"].index("--root") + 1] == str(wt)


# ---------- the bridge (MCP over stdio) ----------


def _bridge(root: Path, env_extra: dict | None = None):
    import os

    env = {**os.environ, **(env_extra or {})}
    return subprocess.Popen(
        [sys.executable, "-m", "acc.mcp_codex", "--root", str(root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )


def _ask(proc, msg):
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    if "id" not in msg:
        return None
    return json.loads(proc.stdout.readline())


def test_bridge_speaks_mcp_and_runs_codex_in_the_copy(tmp_path, fake_codex):
    p = _bridge(tmp_path)
    try:
        init = _ask(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["serverInfo"]["name"] == "orbit"
        _ask(p, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = _ask(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        assert [t["name"] for t in tools] == ["codex_gorev"]
        assert set(tools[0]["inputSchema"]["properties"]) == {"gorev"}  # nothing else to set
        call = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "codex_gorev", "arguments": {"gorev": "Sayaç uç noktasını yaz"}},
        }
        res = _ask(p, call)["result"]
        assert res["isError"] is False
        assert "Yaptım." in res["content"][0]["text"]
        assert "Değişen dosyalar: codex_yazdi.txt" in res["content"][0]["text"]
        assert (tmp_path / "codex_yazdi.txt").exists()
        unknown = _ask(p, {"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
        assert unknown["error"]["code"] == -32601
    finally:
        p.stdin.close()
        p.wait(timeout=10)


def test_bridge_reports_a_used_up_codex(tmp_path, fake_codex):
    p = _bridge(tmp_path, {"FAKE_CODEX_QUOTA": "1"})
    try:
        _ask(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        call = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "codex_gorev", "arguments": {"gorev": "x"}},
        }
        res = _ask(p, call)["result"]
        assert res["isError"] is True and res["content"][0]["text"].startswith(
            "CODEX_KULLANILAMADI"
        )
    finally:
        p.stdin.close()
        p.wait(timeout=10)


# ---------- a turn on a project with a card ----------


def _project_with_card(client):
    p = project(client)
    (Path(p["path"]) / card.FILE).write_text(CARD)
    git(p["path"], "add", "-A")
    git(p["path"], "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "kart")
    return p


class Lead(Recorder):
    info = replace(MockAdapter.info, id="claude_code", name="Claude")


class CodexBuilt(Lead):
    """A lead whose turn included Codex building through the bridge."""

    async def run(self, req, run_id):
        if req.tools and not req.json_schema:
            yield AdapterEvent("tool", {"name": mcp_codex.FULL_NAME, "input": {"gorev": "x"}})
        async for ev in super().run(req, run_id):
            yield ev


class Reviewer(Recorder):
    def __init__(self, adapter_id, name):
        super().__init__()
        self.info = replace(MockAdapter.info, id=adapter_id, name=name)

    async def run(self, req, run_id):
        self.requests.append(req)
        yield AdapterEvent("result", {"text": "", "structured": {"ozet": "Tamam.", "sorunlar": []}})

    async def health_check(self):
        return Health(ModelState.AVAILABLE, "test")


def test_the_lead_works_from_the_card(client, rec):
    p = _project_with_card(client)
    chat_id = new_chat(client, p["id"])
    turn(client, chat_id, "Sayacı ekrana ekle", p["id"])
    req = rec.requests[0]
    assert "PROJE KARTI" in req.prompt and "GET /sayac" in req.prompt
    assert {"backend-gelistirici", "frontend-gelistirici"} <= set(req.agents)
    assert req.mcp_servers is None  # Codex isn't set up in this test


def test_with_codex_set_up_the_bridge_is_offered(client, fake_codex):
    from acc.adapters.codex import CodexAdapter

    lead = Lead()
    original = use(lead, CodexAdapter())
    try:
        p = _project_with_card(client)
        chat_id = new_chat(client, p["id"])
        turn(client, chat_id, "Sayacı ekrana ekle", p["id"])
        req = lead.requests[0]
        assert "backend-codex" in req.agents and mcp_codex.FULL_NAME in req.tools
        root = req.mcp_servers["mcpServers"]["orbit"]["args"]
        assert root[root.index("--root") + 1] == str(req.cwd)  # Codex works in the same copy
    finally:
        registry._adapters = original
        registry._health.clear()


def test_when_codex_built_a_third_model_reviews(client):
    lead = CodexBuilt()
    codex, gemini = Reviewer("codex", "Codex"), Reviewer("gemini", "Gemini")
    original = use(lead, codex, gemini)
    try:
        p = _project_with_card(client)
        chat_id = new_chat(client, p["id"])
        m = turn(client, chat_id, "Backend'e bir satır ekle", p["id"])
        assert m["meta"]["review"]["by"] == "Gemini"  # neither of the two who wrote it
        assert codex.requests == [] and len(gemini.requests) == 1
        assert "PROJE KARTI" in gemini.requests[0].prompt  # checked against the plan too
    finally:
        registry._adapters = original
        registry._health.clear()


def test_while_writing_the_card_the_lead_knows_codex_is_there(client, fake_codex):
    from acc.adapters.codex import CodexAdapter

    lead = Lead()
    original = use(lead, CodexAdapter())
    try:
        p = project(client)  # no card yet
        chat_id = new_chat(client, p["id"])
        turn(client, chat_id, "Ekteki fikirle uygulamayı yapalım", p["id"])
        assert assistant.BUILDERS_CODEX in lead.requests[0].system_prompt
        assert lead.requests[0].mcp_servers is None  # no Codex area yet, so no bridge
    finally:
        registry._adapters = original
        registry._health.clear()


def test_the_card_can_be_read_before_and_after_merge(client):
    p = project(client)
    assert client.get(f"/api/projects/{p['id']}/card").json()["content"] is None

    class Writer(Lead):
        async def run(self, req, run_id):
            (req.cwd / card.FILE).write_text(CARD)
            async for ev in super().run(req, run_id):
                yield ev

    original = use(Writer())
    try:
        chat_id = new_chat(client, p["id"])
        task_id = turn(client, chat_id, "Fikirle başlayalım, kartı yaz", p["id"])["meta"]["task_id"]
        got = client.get(f"/api/projects/{p['id']}/card").json()
        assert got["state"] == "pending" and "GET /sayac" in got["content"]
        assert [a["builder"] for a in got["team"]] == ["codex", "claude"]
        client.post(f"/api/tasks/{task_id}/decision", json={"decision": "approve"})
        assert client.get(f"/api/projects/{p['id']}/card").json()["state"] == "merged"
    finally:
        registry._adapters = original
        registry._health.clear()


def test_each_codex_area_runs_at_its_own_model_and_effort(tmp_path, fake_codex):
    log = tmp_path / "codex-args.jsonl"
    areas = {"backend": {"model": "gpt-6.1-sol", "effort": "medium"}}
    import os

    env = {**os.environ, "FAKE_CODEX_LOG": str(log)}
    p = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "acc.mcp_codex",
            "--root",
            str(tmp_path),
            "--areas",
            json.dumps(areas),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        _ask(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        tools = _ask(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        assert tools[0]["inputSchema"]["properties"]["alan"]["enum"] == ["backend"]
        args = {"gorev": "x", "alan": "backend"}
        call = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "codex_gorev", "arguments": args},
        }
        assert _ask(p, call)["result"]["isError"] is False
        sent = json.loads(log.read_text().splitlines()[0])
        assert sent[sent.index("-m") + 1] == "gpt-6.1-sol"
        assert 'model_reasoning_effort="medium"' in sent
    finally:
        p.stdin.close()
        p.wait(timeout=10)


def test_the_lead_sees_each_member_with_its_model_and_effort(quality):
    plan = assistant.setup(assistant.PROJECT_TOOLS, CARD, codex=True, cwd=Path("/tmp/wt"))
    assert (
        "- backend-codex: Backend koordinatörü (Codex yazar) (Codex Orta · medium)" in plan.system
    )
    assert "- kesifci: Keşifçi (Hafif · low)" in plan.system
    assert plan.labels["backend-gelistirici"] == "Backend geliştirici"
    assert plan.codex_areas == {"backend": {"model": "gpt-6.1-sol", "effort": "medium"}}
