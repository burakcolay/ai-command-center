"""The orchestra: Claude's subagents, and an independent review by another model whose
serious findings the lead fixes."""

import json
from dataclasses import replace

import pytest

from acc import assistant, prefs, review
from acc.adapters import registry
from acc.adapters.base import AdapterEvent, RunRequest
from acc.adapters.claude_code import ClaudeCodeAdapter
from acc.adapters.mock import MockAdapter
from tests.helpers import Recorder, diff_lines, git, new_chat, project, task, turn, use

ISSUE = {"onem": "yuksek", "dosya": "ORBIT_DEMO.md", "sorun": "Satır eksik", "oneri": "Ekle"}


class Lead(Recorder):
    """The lead assistant, wearing Claude Code's id so it resumes its own conversation."""

    info = replace(MockAdapter.info, id="claude_code", name="Claude")


class Critic(Recorder):
    """A different model (Codex) that reviews; `findings` is what it reports each time."""

    info = replace(MockAdapter.info, id="codex", name="Codex")

    def __init__(self, findings=None, write=False, fail=False):
        super().__init__()
        self.findings = list(findings or [])
        self.write = write
        self.fail = fail

    async def run(self, req, run_id):
        self.requests.append(req)
        if self.write:  # a reviewer must not be able to leave changes behind
            (req.cwd / "kotu.txt").write_text("inceleyici yazdı")
        if self.fail:
            yield AdapterEvent("error", {"text": "bağlantı koptu"})
            return
        issues = self.findings.pop(0) if self.findings else []
        yield AdapterEvent(
            "result", {"text": "", "structured": {"ozet": "Baktım.", "sorunlar": issues}}
        )


@pytest.fixture
def quality(client):  # client: the database must exist before preferences are written
    def set_(value):
        prefs.put("quality", value)

    yield set_
    prefs.put("quality", "balanced")


@pytest.fixture
def team():
    original = registry._adapters

    def make(*adapters):
        use(*adapters)
        return adapters

    yield make
    registry._adapters = original
    registry._health.clear()


def _edit(client):
    p = project(client)
    chat_id = new_chat(client, p["id"])
    m = turn(client, chat_id, "Karşılama satırı ekle", p["id"])
    return p, chat_id, m


# ---------- Claude's own subagents ----------


def test_economy_means_one_assistant_and_no_team(quality):
    quality("economy")
    plan = assistant.setup(assistant.PROJECT_TOOLS)
    assert "Agent" not in plan.tools and plan.agents is None and "EKİP" not in plan.system


def test_subagents_reach_claude_code(quality):
    plan = assistant.setup(assistant.PROJECT_TOOLS)
    tools, system, agents = plan.tools, plan.system, plan.agents
    args = ClaudeCodeAdapter()._args(RunRequest(prompt="x", tools=tools, agents=agents))
    defined = json.loads(args[args.index("--agents") + 1])
    assert set(defined) == {"arastirmaci", "tasarimci", "test-yazari", "inceleyici"}
    assert defined["inceleyici"]["tools"] == ["Read", "Glob", "Grep", "Bash"]
    assert all(a["model"] == "inherit" and "label" not in a for a in defined.values())
    assert "Agent" in args[args.index("--allowedTools") + 1]
    assert "- tasarimci: Tasarımcı" in system
    assert "--strict-mcp-config" in args  # the user's own MCP servers never load


def test_subagent_steps_are_labelled_and_their_words_stay_inside():
    a = ClaudeCodeAdapter()
    delegate = {
        "type": "assistant",
        "parent_tool_use_id": None,
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "Agent",
                    "input": {"subagent_type": "arastirmaci", "description": "Rakipler"},
                }
            ]
        },
    }
    [ev] = a._translate(delegate)
    assert ev.data["agent"] == "arastirmaci"
    inner = {
        "type": "assistant",
        "parent_tool_use_id": "t1",
        "message": {
            "content": [
                {"type": "text", "text": "ara sonuç"},
                {"type": "tool_use", "id": "t2", "name": "WebSearch", "input": {"query": "q"}},
            ]
        },
    }
    [ev] = a._translate(inner)
    assert ev.kind == "tool" and ev.data == {
        "name": "WebSearch",
        "input": {"query": "q"},
        "agent": "arastirmaci",
    }
    sub_delta = {
        "type": "stream_event",
        "parent_tool_use_id": "t1",
        "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "x"}},
    }
    assert a._translate(sub_delta) == []


# ---------- independent review ----------


def test_codex_reviews_and_claude_fixes_what_is_serious(client, team):
    lead, critic = team(Lead(), Critic(findings=[[ISSUE]]))
    p, chat_id, m = _edit(client)
    task_id = m["meta"]["task_id"]

    [rev] = critic.requests
    assert rev.tools == review.READ_ONLY and rev.json_schema == review.SCHEMA
    assert rev.cwd == lead.requests[0].cwd  # reads the same isolated copy
    assert "Karşılama satırı ekle" in rev.prompt and "+Demo adaptörünün" in rev.prompt

    fix = lead.requests[-1]
    assert fix.resume == lead.requests[0].session_id  # same conversation, no history resent
    assert fix.prompt.startswith("BAĞIMSIZ İNCELEME — Codex") and "Satır eksik" in fix.prompt

    assert "**Codex inceledi:** Baktım." in m["content"] and "Düzeltiyorum" in m["content"]
    assert m["meta"]["review"]["by"] == "Codex" and m["meta"]["review"]["fixed"] is True
    t = task(client, chat_id, task_id)
    assert [s["title"] for s in t["steps"]] == [
        "Karşılama satırı ekle",
        "İnceleme düzeltmeleri (Codex)",
    ]
    assert diff_lines(client, task_id) == 2


def test_a_clean_review_changes_nothing(client, team):
    lead, critic = team(Lead(), Critic(findings=[[]]))
    _, chat_id, m = _edit(client)
    assert len(lead.requests) == 1 and len(critic.requests) == 1
    assert "**Codex inceledi:**" in m["content"] and "Düzeltiyorum" not in m["content"]
    assert len(task(client, chat_id, m["meta"]["task_id"])["steps"]) == 1


def test_minor_findings_are_reported_not_fixed(client, team):
    minor = {**ISSUE, "onem": "dusuk", "sorun": "Yazım"}
    lead, _ = team(Lead(), Critic(findings=[[minor]]))
    _, _, m = _edit(client)
    assert len(lead.requests) == 1 and "Yazım" in m["content"]
    assert m["meta"]["review"]["fixed"] is False


def test_review_follows_the_quality_setting(client, team, quality):
    lead, critic = team(Lead(), Critic())
    quality("economy")
    _edit(client)
    assert critic.requests == []  # economy: no second model, no extra quota

    quality("balanced")
    (lead,) = team(Lead())  # only Claude: a small change isn't worth a self-review
    _, _, m = _edit(client)
    assert len(lead.requests) == 1 and "review" not in m["meta"]

    quality("best")  # best: always, Claude in a separate context if nobody else is around
    _, _, m = _edit(client)
    assert m["meta"]["review"]["by"] == "Claude (ayrı oturum)"
    assert lead.requests[-1].json_schema == review.SCHEMA


def test_a_reviewer_cannot_leave_changes_behind(client, team):
    team(Lead(), Critic(findings=[[]], write=True))
    p, chat_id, m = _edit(client)
    files = [
        f["path"] for f in client.get(f"/api/tasks/{m['meta']['task_id']}/diff").json()["files"]
    ]
    assert files == ["ORBIT_DEMO.md"]
    wt = git(p["path"], "worktree", "list")
    assert "chat-" in wt


def test_a_failed_review_keeps_the_change(client, team):
    team(Lead(), Critic(fail=True))
    _, chat_id, m = _edit(client)
    task_id = m["meta"]["task_id"]
    assert m["status"] == "done" and "review" not in m["meta"]
    events = [e["data"].get("text", "") for e in client.get(f"/api/tasks/{task_id}/events").json()]
    assert any("İnceleme yapılamadı" in e for e in events)
    assert task(client, chat_id, task_id)["status"] == "waiting_approval"


async def test_with_background_subagents_the_last_result_is_the_answer(tmp_path):
    """Recorded shape of a real run: three turns (start, one designer done, both done)."""
    lines = [
        {"type": "system", "subtype": "init", "apiKeySource": "none", "model": "m"},
        {"type": "result", "subtype": "success", "result": "İki tasarımcı çalışıyor."},
        {"type": "result", "subtype": "success", "result": "Birincisi hazır."},
        {"type": "result", "subtype": "success", "result": "İkisi de hazır.", "num_turns": 3},
    ]
    script = tmp_path / "claude"
    body = "\n".join(f"echo '{json.dumps(line, ensure_ascii=False)}'" for line in lines)
    status = json.dumps({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"})
    auth = f"if [ \"$1\" = auth ]; then echo '{status}'; exit 0; fi"
    script.write_text(f"#!/bin/sh\n{auth}\ncat >/dev/null\n{body}\n")
    script.chmod(0o755)
    events = [ev async for ev in ClaudeCodeAdapter(binary=str(script)).run(RunRequest("x"), "r")]
    results = [ev for ev in events if ev.kind == "result"]
    assert [r.data["text"] for r in results] == ["İkisi de hazır."]


async def test_restricted_mode_is_used_when_the_cli_has_it(tmp_path):
    status = json.dumps({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"})
    script = tmp_path / "claude"
    script.write_text(
        "#!/bin/sh\n"
        f"if [ \"$1\" = auth ]; then echo '{status}'; exit 0; fi\n"
        'if [ "$1" = --help ]; then echo "  --restricted   Restricted mode"; exit 0; fi\n'
    )
    script.chmod(0o755)
    a = ClaudeCodeAdapter(binary=str(script))
    args = a._args(RunRequest("x"))
    assert "--setting-sources" in args and "--restricted" not in args  # before the check
    await a.health_check()
    args = a._args(RunRequest("x"))
    assert "--restricted" in args and "--setting-sources" not in args
