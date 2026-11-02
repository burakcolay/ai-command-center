"""The live picture of who is working on a turn: the lead, its subagents, Codex, the reviewer.

Built from the adapter's "agent" events (verified against Claude Code 2.1.316 stream-json:
task_started / task_progress with total_tokens / task_notification, each subagent's real model
on its own messages, and per-model token totals in the result). Sent to the UI on every change
and kept on the message afterwards, so the user can see which model did what, at which effort,
and how many tokens it took.
"""

from __future__ import annotations

from typing import Any

from acc import tiers
from acc.events import broker

VENDOR = {
    "claude_code": "Claude",
    "codex": "Codex",
    "gemini": "Gemini",
    "ollama": "Yerel",
    "mock": "Demo",
}


def tool_line(data: dict[str, Any]) -> str:
    """ "Edit server/app.py", "Bash npm test", "WebSearch rakip fiyatları" — short."""
    name = str(data.get("name") or "")
    if name.endswith("__codex_gorev"):
        return "Codex'e görev verdi"
    if name in ("Agent", "Task"):
        return str((data.get("input") or {}).get("description") or "görev verdi")
    i = data.get("input") if isinstance(data.get("input"), dict) else {}
    path = str(i.get("file_path") or i.get("path") or "")
    short = "/".join(path.split("/")[-2:]) if path else ""
    what = str(i.get("command") or i.get("pattern") or i.get("query") or i.get("url") or "")
    return f"{name} {what or short}".strip()[:120]


class Orchestra:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id
        self.lead: dict[str, Any] = {}
        self.members: list[dict[str, Any]] = []
        self.usage: dict[str, dict[str, int]] = {}
        self.roster: dict[str, dict[str, Any]] = {}  # subagent name -> label, model, effort
        self.codex_areas: dict[str, dict[str, str]] = {}

    # ---------- setup ----------

    def set_lead(self, vendor: str, model: str | None, effort: str | None) -> None:
        self.lead = {
            "label": "Lider",
            "vendor": VENDOR.get(vendor, vendor),
            "model": tiers.model_name(model) if model and model != "default" else "",
            "actual": "",
            "effort": effort or "",
            "status": "running",
            "activity": "",
        }
        self.publish()

    def set_roster(
        self,
        agents: dict[str, dict[str, Any]] | None,
        labels: dict[str, str],
        codex_areas: dict[str, dict[str, str]],
    ) -> None:
        self.roster = {
            name: {
                "label": labels.get(name, name),
                "model": a.get("model", ""),
                "effort": a.get("effort", ""),
            }
            for name, a in (agents or {}).items()
        }
        self.codex_areas = codex_areas

    # ---------- events ----------

    def _member(self, member_id: str | None) -> dict[str, Any] | None:
        return next((m for m in self.members if m["id"] == member_id), None)

    def apply(self, data: dict[str, Any]) -> None:
        op = data.get("op")
        if op == "lead":
            self.lead["actual"] = tiers.model_name(data.get("model"))
        elif op == "start":
            info = self.roster.get(data.get("agent") or "", {})
            self.members.append(
                {
                    "id": data.get("id"),
                    "agent": data.get("agent"),
                    "label": info.get("label") or data.get("agent"),
                    "vendor": "Claude",
                    "model": tiers.model_name(info.get("model")),
                    "actual": "",
                    "effort": info.get("effort", ""),
                    "status": "running",
                    "task": data.get("task") or "",
                    "activity": "",
                    "tokens": 0,
                    "tools": 0,
                }
            )
        elif op == "model":
            if m := self._member(data.get("id")):
                m["actual"] = tiers.model_name(data.get("model"))
        elif op == "progress":
            if m := self._member(data.get("id")):
                m["tokens"] = data.get("tokens") or m["tokens"]
                m["tools"] = data.get("tools") or m["tools"]
                m["activity"] = data.get("activity") or m["activity"]
        elif op == "end":
            if m := self._member(data.get("id")):
                m["status"] = "failed" if data.get("status") == "failed" else "done"
                m["tokens"] = data.get("tokens") or m["tokens"]
                m["activity"] = ""
                for c in self.members:  # Codex calls of this coordinator are over too
                    if c.get("parent") == m["id"] and c["status"] == "running":
                        c["status"] = "done"
        elif op == "codex":
            area = data.get("area") or ""
            power = self.codex_areas.get(area) or next(iter(self.codex_areas.values()), {})
            self.members.append(
                {
                    "id": data.get("id"),
                    "parent": data.get("parent"),
                    "agent": "codex",
                    "label": f"Codex · {area}" if area else "Codex",
                    "vendor": "Codex",
                    "model": tiers.model_name(power.get("model")),
                    "actual": "",
                    "effort": power.get("effort", ""),
                    "status": "running",
                    "task": "",
                    "activity": "",
                    "tokens": 0,
                    "tools": 0,
                }
            )
        elif op == "codex_end" and (m := self._member(data.get("id"))):
            m["status"] = "failed" if data.get("error") else "done"
        self.publish()

    def tool(self, data: dict[str, Any]) -> None:
        """A tool step: the lead's own, or a subagent's (it carries the subagent's call id)."""
        line = tool_line(data)
        if (parent := data.get("parent")) and (m := self._member(parent)):
            m["activity"] = line
        elif not data.get("agent"):
            self.lead["activity"] = line
        self.publish()

    def add_usage(self, model_usage: dict[str, Any] | None) -> None:
        for model, u in (model_usage or {}).items():
            self.usage[tiers.model_name(model)] = {
                "input": int(u.get("inputTokens") or 0)
                + int(u.get("cacheCreationInputTokens") or 0),
                "output": int(u.get("outputTokens") or 0),
                "cached": int(u.get("cacheReadInputTokens") or 0),
            }
        self.publish()

    def reviewer(self, label: str, vendor: str, model: str | None, effort: str | None) -> None:
        self.members.append(
            {
                "id": "inceleme",
                "agent": "inceleme",
                "label": label,
                "vendor": VENDOR.get(vendor, vendor),
                "model": tiers.model_name(model),
                "actual": "",
                "effort": effort or "",
                "status": "running",
                "task": "değişiklikleri bağımsız inceliyor",
                "activity": "",
                "tokens": 0,
                "tools": 0,
            }
        )
        self.publish()

    def reviewer_done(self, found: int | None) -> None:
        if m := self._member("inceleme"):
            m["status"] = "failed" if found is None else "done"
            m["activity"] = "" if found is None else f"{found} bulgu"
        self.publish()

    def finish(self) -> dict[str, Any]:
        self.lead["status"] = "done"
        self.lead["activity"] = ""
        for m in self.members:
            if m["status"] == "running":
                m["status"] = "done"
        self.publish()
        return self.snapshot()

    # ---------- output ----------

    def snapshot(self) -> dict[str, Any]:
        return {"lead": self.lead, "members": self.members, "usage": self.usage}

    def publish(self) -> None:
        broker.publish({"type": "team", "message_id": self.message_id, "team": self.snapshot()})
