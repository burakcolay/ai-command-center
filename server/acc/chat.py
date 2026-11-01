"""Conversation mode: think things through with the assistant before turning them into a task.

The assistant can read the project and search the web but never changes files. The
conversation is resent as a transcript each turn, which keeps this provider-independent.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from acc import config, serialize
from acc.adapters import Registry
from acc.adapters.base import AdapterError, RunRequest
from acc.agents import AGENTS, CHAT_SYSTEM
from acc.db import session
from acc.events import broker
from acc.models import Chat, Message, Project, Task

TRANSCRIPT_LIMIT = 150_000  # chars of history sent with each turn (newest kept)
WEB_ONLY = ["WebSearch", "WebFetch"]


def transcript(s: Session, chat_id: int, before_id: int, limit: int = TRANSCRIPT_LIMIT) -> str:
    """The conversation before `before_id`, oldest first, trimmed from the oldest end."""
    rows = s.scalars(
        select(Message)
        .where(Message.chat_id == chat_id, Message.id < before_id)
        .order_by(Message.id.desc())
    ).all()
    parts: list[str] = []
    used = 0
    for m in rows:
        if m.role == "user":
            line = f"Kullanıcı: {m.content}"
        elif m.role == "assistant" and m.content.strip():
            line = f"Asistan: {m.content}"
        elif m.role == "task" and m.task_id and (t := s.get(Task, m.task_id)):
            line = f"[Görev #{t.id}: {t.title} — durum: {t.status}]"
        else:
            continue
        if used + len(line) > limit:
            parts.append("[… daha eski mesajlar kısaltıldı …]")
            break
        parts.append(line)
        used += len(line)
    return "\n\n".join(reversed(parts))


class ChatService:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self._runs: dict[int, tuple[str, str]] = {}  # message_id -> (adapter_id, run_id)
        self._cancelling: set[int] = set()
        self._jobs: set[asyncio.Task[None]] = set()

    def start_reply(self, message_id: int) -> None:
        job = asyncio.create_task(self._reply(message_id))
        self._jobs.add(job)
        job.add_done_callback(self._jobs.discard)

    def _finish(self, message_id: int, content: str, status: str) -> None:
        with session() as s:
            m = s.get(Message, message_id)
            m.content = content
            m.status = status
            payload = serialize.message(m)
        broker.publish({"type": "message", "message": payload})

    async def _reply(self, message_id: int) -> None:
        with session() as s:
            m = s.get(Message, message_id)
            chat = s.get(Chat, m.chat_id)
            project = s.get(Project, chat.project_id) if chat.project_id else None
            user = s.scalars(
                select(Message)
                .where(Message.chat_id == chat.id, Message.id < message_id, Message.role == "user")
                .order_by(Message.id.desc())
            ).first()
            history = transcript(s, chat.id, before_id=user.id)
            question = user.content
            project_dir = Path(project.path) if project and Path(project.path).is_dir() else None
            project_line = f"PROJE: {project.name} ({project.path})\n\n" if project_dir else ""

        agent = AGENTS["assistant"]
        if project_dir:
            cwd, tools = project_dir, agent.tools
        else:  # no project: nothing on disk to read, only the web
            cwd = config.DATA_DIR / "chat-empty"
            cwd.mkdir(parents=True, exist_ok=True)
            tools = WEB_ONLY
        prompt = project_line
        if history:
            prompt += f"SOHBET GEÇMİŞİ:\n{history}\n\n"
        prompt += f"KULLANICININ SON MESAJI:\n{question}"

        adapter, skipped = await self.registry.pick(agent.adapters)
        if adapter is None:
            reason = "; ".join(skipped) or "kayıtlı model yok"
            self._finish(message_id, f"Yanıt verecek model yok ({reason}).", "error")
            return

        req = RunRequest(
            prompt=prompt,
            cwd=cwd,
            system_prompt=CHAT_SYSTEM,
            tools=tools,
            permission_mode="dontAsk",
            stream_text=True,
        )
        run_id = uuid.uuid4().hex
        self._runs[message_id] = (adapter.info.id, run_id)
        buf: list[str] = []
        try:
            async for ev in adapter.run(req, run_id):
                if ev.kind == "delta":
                    buf.append(ev.data["text"])
                    broker.publish(
                        {"type": "message_delta", "message_id": message_id, "text": ev.data["text"]}
                    )
                elif ev.kind == "tool":
                    broker.publish(
                        {"type": "message_activity", "message_id": message_id, "tool": ev.data}
                    )
                elif ev.kind == "result":
                    self._finish(message_id, ev.data.get("text") or "".join(buf), "done")
                    return
                elif ev.kind == "error":
                    raise AdapterError(ev.data.get("text") or "Bilinmeyen hata")
            raise AdapterError("Model yanıtı tamamlamadan durdu.")
        except AdapterError as e:
            partial = "".join(buf).strip()
            if message_id in self._cancelling:
                stopped = (partial + "\n\n" if partial else "") + "_(durduruldu)_"
                self._finish(message_id, stopped, "cancelled")
                return
            self._finish(message_id, (partial + "\n\n" if partial else "") + f"⚠ {e}", "error")
        except Exception as e:
            self._finish(message_id, f"⚠ Beklenmeyen hata: {e!r}", "error")
        finally:
            self._runs.pop(message_id, None)
            self._cancelling.discard(message_id)

    async def cancel(self, message_id: int) -> dict[str, Any]:
        with session() as s:
            m = s.get(Message, message_id)
            if m is None:
                raise LookupError(message_id)
            payload = serialize.message(m)
        if payload["status"] != "streaming":
            return payload
        run = self._runs.get(message_id)
        if run and (adapter := self.registry.get(run[0])):
            # The reply loop sees the flag, saves the partial answer and marks it cancelled
            # in one write, so nobody ever sees a cancelled message without its text.
            self._cancelling.add(message_id)
            await adapter.cancel(run[1])
        else:
            self._finish(message_id, "_(durduruldu)_", "cancelled")
        return payload

    def recover(self) -> None:
        with session() as s:
            for m in s.scalars(select(Message).where(Message.status == "streaming")):
                m.status = "error"
                m.content = "⚠ Sunucu yeniden başlatıldı; yanıt yarıda kaldı."

    async def shutdown(self) -> None:
        for adapter_id, run_id in list(self._runs.values()):
            if adapter := self.registry.get(adapter_id):
                await adapter.cancel(run_id)
