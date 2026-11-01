"""Conversation mode: think things through with the assistant before turning them into a task.

The assistant can read the project and search the web but never changes files. The
conversation is resent each turn as text, which keeps this provider-independent; once it
gets long, older messages are folded into a rolling summary (preferably by a free local
model) so every turn doesn't resend — and pay quota for — the whole history.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from acc import config, memory, serialize
from acc.adapters import Registry
from acc.adapters.base import AdapterError, RunRequest
from acc.agents import AGENTS, CHAT_SYSTEM
from acc.db import session
from acc.events import broker
from acc.models import Chat, Message, Project, Task

TRANSCRIPT_LIMIT = 150_000  # chars of history a task snapshot may carry
COMPACT_AT = 30_000  # unsummarised history longer than this gets summarised
KEEP_RECENT = 6  # newest messages always sent verbatim
SUMMARIZERS = ["ollama", "claude_code", "mock"]  # free local model first
WEB_ONLY = ["WebSearch", "WebFetch"]
NO_TOOLS_NOTE = (
    "(Not: Bu yanıtı yerel bir model veriyor; proje dosyalarına ve web'e erişimi yok. "
    "Kod incelemesi gerekiyorsa kullanıcıya Claude'a geçmesini öner.)\n\n"
)

SUMMARY_SYSTEM = """Sen bir konuşma özetleyicisisin. Konuşmayı, sonraki turlarda bağlam olarak
kullanılacak şekilde Türkçe ve madde madde özetle. Alınan kararlar, gereksinimler, tercih edilen
teknolojiler, açık sorular ve önemli ayrıntılar (dosya adları, isimler, sayılar) eksiksiz kalsın.
Giriş cümlesi yazma, yorum ekleme."""


def transcript(
    s: Session,
    chat_id: int,
    before_id: int,
    after_id: int = 0,
    limit: int = TRANSCRIPT_LIMIT,
) -> str:
    """Messages with after_id < id < before_id, oldest first, trimmed from the oldest end."""
    rows = s.scalars(
        select(Message)
        .where(Message.chat_id == chat_id, Message.id < before_id, Message.id > after_id)
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


def conversation(s: Session, chat: Chat, before_id: int) -> str:
    """Summary of older messages (if any) followed by the recent ones verbatim."""
    recent = transcript(s, chat.id, before_id, after_id=chat.summary_until or 0)
    if not chat.summary:
        return recent
    return f"ÖNCEKİ KONUŞMANIN ÖZETİ:\n{chat.summary}\n\nSON MESAJLAR:\n{recent}"


def context_for_task(s: Session, chat: Chat, before_id: int) -> str | None:
    """What a new task carries: the full conversation if it fits, else summary + recent."""
    full = transcript(s, chat.id, before_id, limit=TRANSCRIPT_LIMIT * 2)
    if len(full) <= TRANSCRIPT_LIMIT or not chat.summary:
        return transcript(s, chat.id, before_id) or None
    return conversation(s, chat, before_id)


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

    def _finish(self, message_id: int, content: str, status: str, adapter_id: str | None = None):
        with session() as s:
            m = s.get(Message, message_id)
            m.content = content
            m.status = status
            if adapter_id:
                m.adapter_id = adapter_id
            payload = serialize.message(m)
        broker.publish({"type": "message", "message": payload})

    # ---------- summarising ----------

    async def _maybe_compact(self, chat_id: int, before_id: int) -> None:
        with session() as s:
            chat = s.get(Chat, chat_id)
            after = chat.summary_until or 0
            if len(transcript(s, chat_id, before_id, after_id=after)) <= COMPACT_AT:
                return
            ids = s.scalars(
                select(Message.id)
                .where(Message.chat_id == chat_id, Message.id < before_id, Message.id > after)
                .order_by(Message.id)
            ).all()
            if len(ids) <= KEEP_RECENT:
                return
            cutoff = ids[-KEEP_RECENT - 1]
            older = transcript(s, chat_id, cutoff + 1, after_id=after, limit=TRANSCRIPT_LIMIT)
            previous = chat.summary or "(yok)"
        prompt = (
            f"MEVCUT ÖZET:\n{previous}\n\nÖZETE EKLENECEK MESAJLAR:\n{older}\n\n"
            "Bunları tek ve güncel bir özette birleştir."
        )
        adapter, _ = await self.registry.pick(SUMMARIZERS)
        if adapter is None:
            return
        req = RunRequest(prompt=prompt, system_prompt=SUMMARY_SYSTEM, tools=[])
        try:
            async for ev in adapter.run(req, uuid.uuid4().hex):
                if ev.kind == "result" and (text := (ev.data.get("text") or "").strip()):
                    with session() as s:
                        chat = s.get(Chat, chat_id)
                        chat.summary, chat.summary_until = text, cutoff
                    return
                if ev.kind == "error":
                    return
        except AdapterError:
            return  # no summary this turn; the plain transcript still works

    # ---------- replying ----------

    async def _reply(self, message_id: int) -> None:
        with session() as s:
            m = s.get(Message, message_id)
            chat_id, requested = m.chat_id, m.adapter_id
            user = s.scalars(
                select(Message)
                .where(Message.chat_id == chat_id, Message.id < message_id, Message.role == "user")
                .order_by(Message.id.desc())
            ).first()
            user_id, question = user.id, user.content

        await self._maybe_compact(chat_id, user_id)

        with session() as s:
            chat = s.get(Chat, chat_id)
            history = conversation(s, chat, user_id)
            project = s.get(Project, chat.project_id) if chat.project_id else None
            project_dir = Path(project.path) if project and Path(project.path).is_dir() else None
            project_name = project.name if project else None
            project_path = project.path if project else None

        agent = AGENTS["assistant"]
        adapter, skipped = await self.registry.pick([requested] if requested else agent.adapters)
        if adapter is None:
            reason = "; ".join(skipped) or "kayıtlı model yok"
            self._finish(message_id, f"Yanıt verecek model yok ({reason}).", "error")
            return

        if not adapter.capabilities.tools:
            cwd, tools, note = None, [], NO_TOOLS_NOTE
        elif project_dir:
            cwd, tools, note = project_dir, agent.tools, ""
        else:  # no project: nothing on disk to read, only the web
            cwd = config.DATA_DIR / "chat-empty"
            cwd.mkdir(parents=True, exist_ok=True)
            tools, note = WEB_ONLY, ""

        prompt = note
        if project_dir:
            prompt += f"PROJE: {project_name} ({project_path})\n\n"
        prompt += memory.prompt_block(project_name)
        if history:
            prompt += f"SOHBET GEÇMİŞİ:\n{history}\n\n"
        prompt += f"KULLANICININ SON MESAJI:\n{question}"

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
                    text = ev.data.get("text") or "".join(buf)
                    self._finish(message_id, text, "done", adapter.info.id)
                    return
                elif ev.kind == "error":
                    raise AdapterError(ev.data.get("text") or "Bilinmeyen hata")
            raise AdapterError("Model yanıtı tamamlamadan durdu.")
        except AdapterError as e:
            partial = "".join(buf).strip()
            if message_id in self._cancelling:
                stopped = (partial + "\n\n" if partial else "") + "_(durduruldu)_"
                self._finish(message_id, stopped, "cancelled", adapter.info.id)
                return
            failed = (partial + "\n\n" if partial else "") + f"⚠ {e}"
            self._finish(message_id, failed, "error", adapter.info.id)
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
