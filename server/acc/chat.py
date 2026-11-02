"""One chat, one assistant. Each user message is a turn: the assistant answers, researches,
designs or edits — whatever the message asks for — and Orbit turns the results into
something reviewable (rendered designs, saved reports, a diff with checks).

The assistant keeps its own conversation across turns (Claude Code session resume). When
that isn't possible — first turn, lost session, another model — the history is sent as text,
with older messages folded into a rolling summary so long chats don't burn the quota.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from acc import (
    assistant,
    attachments,
    card,
    config,
    designs,
    memory,
    notify,
    review,
    security,
    serialize,
    sessions,
)
from acc.adapters import Registry
from acc.adapters.base import AdapterError, ModelState, QuotaExceeded, RunRequest, SessionLost
from acc.db import session
from acc.events import broker
from acc.gitops import GitError
from acc.gitops import discard as discard_uncommitted
from acc.mcp_codex import FULL_NAME as CODEX_TOOL
from acc.models import Chat, Message, Project, Task
from acc.routing import Router

TRANSCRIPT_LIMIT = 150_000  # chars of history sent when a conversation must be rebuilt
COMPACT_AT = 30_000  # unsummarised history longer than this gets summarised
KEEP_RECENT = 6  # newest messages always sent verbatim
TEAM_ADAPTERS = ("claude_code", "mock")  # leads that can delegate to subagents
NOTIFY_AFTER_S = 45  # long turns (research, big edits) end with a desktop notification
RESUME_MARGIN_S = 60  # wait this long past the quota reset before continuing
BACKUP_NOTE = (
    "(Not: Claude şu an kullanılamıyor; bu yanıtı yedek model ({name}) veriyor. Proje "
    "dosyalarına erişimi yok, değişiklik yapamaz.)\n\n"
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
            line = f"[Değişiklikler #{t.id} — durum: {t.status}]"
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


def save_report(text: str, question: str, project_name: str | None) -> Path:
    """Research reports are kept as plain markdown next to project memory (Obsidian-friendly)."""
    folder = config.MEMORY_DIR / "Araştırmalar"
    folder.mkdir(parents=True, exist_ok=True)
    first = next((ln for ln in text.splitlines() if ln.startswith("# ")), "")
    title = first[2:].strip() or question.strip().splitlines()[0][:80] or "rapor"
    slug = re.sub(r"[^\w\-]+", "-", title.lower(), flags=re.UNICODE).strip("-")[:60] or "rapor"
    path = folder / f"{date.today().isoformat()}-{slug}.md"
    n = 2
    while path.exists():
        path = folder / f"{date.today().isoformat()}-{slug}-{n}.md"
        n += 1
    header = f"> Orbit araştırması · {date.today().isoformat()}"
    if project_name:
        header += f" · Proje: {project_name}"
    header += f"\n> Soru: {question.strip()[:500]}\n\n"
    path.write_text(header + text.strip() + "\n", encoding="utf-8")
    return path


class ChatService:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.router = Router(registry)
        self._runs: dict[int, tuple[str, str]] = {}  # message_id -> (adapter_id, run_id)
        self._cancelling: set[int] = set()
        self._codex_wrote: set[int] = set()  # turns in which Codex built something via the bridge
        self._jobs: set[asyncio.Task[None]] = set()

    def _spawn(self, coro) -> None:
        job = asyncio.create_task(coro)
        self._jobs.add(job)
        job.add_done_callback(self._jobs.discard)

    def start_reply(self, message_id: int) -> None:
        self._spawn(self._reply(message_id))

    def _finish(
        self,
        message_id: int,
        content: str,
        status: str,
        adapter_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ):
        with session() as s:
            m = s.get(Message, message_id)
            m.content = content
            m.status = status
            if adapter_id:
                m.adapter_id = adapter_id
            if meta is not None:
                m.meta = {**(m.meta or {}), **meta}
            payload = serialize.message(m)
        broker.publish({"type": "message", "message": payload})

    def _activity(self, message_id: int, name: str, detail: str = "") -> None:
        broker.publish(
            {
                "type": "message_activity",
                "message_id": message_id,
                "tool": {"name": name, "input": {"query": detail} if detail else {}},
            }
        )

    # ---------- summarising (only when the conversation has to be rebuilt as text) ----------

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
        adapter = (await self.router.pick("summarize")).adapter  # free local model first
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

    # ---------- a turn ----------

    async def _reply(self, message_id: int) -> None:
        started = time.monotonic()
        with session() as s:
            m = s.get(Message, message_id)
            chat_id = m.chat_id
            user = s.scalars(
                select(Message)
                .where(Message.chat_id == chat_id, Message.id < message_id, Message.role == "user")
                .order_by(Message.id.desc())
            ).first()
            user_id, question = user.id, user.content
            attached = (user.meta or {}).get("attachments") or []
            chat = s.get(Chat, chat_id)
            project = s.get(Project, chat.project_id) if chat.project_id else None
            project_name = project.name if project else None
            project_path = Path(project.path) if project else None
            claude_session = chat.claude_session
            earlier = s.scalars(
                select(Message.id)
                .where(
                    Message.chat_id == chat_id, Message.id < message_id, Message.role == "assistant"
                )
                .order_by(Message.id.desc())
            ).all()

        choice = await self.router.pick("assistant", needs_tools=True)
        adapter, local = choice.adapter, False
        if adapter is None:  # Claude unavailable: a local model can still talk
            adapter, local = (await self.router.pick("summarize")).adapter, True
        if adapter is None:
            reason = "; ".join(choice.skipped) or "kayıtlı model yok"
            self._finish(message_id, f"Yanıt verecek model yok ({reason}).", "error")
            return

        # Where the assistant works: the chat's isolated project copy, or a private folder.
        ws = None
        note = ""
        if local:
            cwd, tools = None, []
        elif project_path and project_path.is_dir():
            try:
                ws = await sessions.workspace(chat_id)
                cwd, tools = ws.cwd, assistant.PROJECT_TOOLS
            except GitError as e:
                cwd, tools = project_path, assistant.READ_ONLY_TOOLS
                note = (
                    f"(Not: Proje salt okunur açıldı, değişiklik yapamazsın: {e} Değişiklik "
                    "istenirse kullanıcıya proje klasöründe `git init` ve ilk commit'i öner.)\n\n"
                )
        else:
            cwd = config.DATA_DIR / "chats" / str(chat_id)
            cwd.mkdir(parents=True, exist_ok=True)
            tools = assistant.SCRATCH_TOOLS
        out_dir = config.DATA_DIR / "outputs" / str(message_id)
        out_dir.mkdir(parents=True, exist_ok=True)

        # The Project Card, if the project has one: the lead and every specialist work from it.
        card_text = card.read(cwd) if project_path and not local else None
        if adapter.info.id in TEAM_ADAPTERS and not local:
            # Also when there is no card yet: the lead must know Codex is there while writing it.
            codex = await self._codex_ready() if ws else False
            plan = assistant.setup(tools, card_text, codex, cwd)
            lead_tools, lead_system, team, mcp = plan.tools, plan.system, plan.agents, plan.mcp
        else:
            lead_tools, lead_system, team, mcp = tools, assistant.SYSTEM, None, None

        def build(with_history: bool) -> str:
            parts = [BACKUP_NOTE.format(name=adapter.info.name) if local else note]
            if project_name:
                where = f"\nÇALIŞMA KOPYASI: {cwd}" if ws else ""
                parts.append(f"PROJE: {project_name} ({project_path}){where}\n\n")
            parts.append(memory.prompt_block(project_name))
            parts.append(card.lead_block(card_text))
            if ws:
                parts.append(_checks_block(sessions.checks_config(ws.task_id, ws.cwd)))
                parts.append(sessions.failed_checks_block(ws.task_id))
            if not local:
                parts.append(f"ÇIKTI KLASÖRÜ (raporlar ve tasarım dosyaları): {out_dir}\n\n")
                rounds = [mid for mid in earlier if designs.folder(mid).is_dir()][:2]
                parts.append(designs.previous_block(list(reversed(rounds))))
                parts.append(attachments.prompt_block(attached))
            if with_history and history:
                parts.append(f"SOHBET GEÇMİŞİ:\n{history}\n\n")
            parts.append(f"KULLANICININ MESAJI:\n{question}")
            return "".join(parts)

        resume = claude_session if adapter.info.id == "claude_code" else None
        history = ""
        if not resume:
            await self._maybe_compact(chat_id, user_id)
            with session() as s:
                history = conversation(s, s.get(Chat, chat_id), user_id)

        def request(
            resume_id: str | None, new_session: str | None, prompt: str | None = None
        ) -> RunRequest:
            return RunRequest(
                prompt=prompt or build(with_history=resume_id is None),
                cwd=cwd,
                system_prompt=lead_system,
                tools=lead_tools,
                agents=team,
                mcp_servers=mcp,
                permission_mode="dontAsk",
                settings=assistant.settings(tools),
                stream_text=True,
                effort=assistant.effort(),
                read_dirs=[] if local else attachments.read_dirs(),
                output_dir=None if local else out_dir,
                session_id=new_session,
                resume=resume_id,
            )

        def fix_request(instructions: str) -> RunRequest:
            """The lead's follow-up after a review: same conversation when it can resume."""
            if sid := new_session or resume:
                return request(sid, None, prompt=instructions)
            return request(None, None, prompt=build(with_history=True) + "\n\n" + instructions)

        new_session = None if (resume or adapter.info.id != "claude_code") else str(uuid.uuid4())
        buf: list[str] = []
        try:
            try:
                text = await self._run(message_id, adapter, request(resume, new_session), buf)
            except SessionLost:
                # The saved conversation is gone (e.g. the working folder changed): rebuild it.
                buf.clear()
                await self._maybe_compact(chat_id, user_id)
                with session() as s:
                    history = conversation(s, s.get(Chat, chat_id), user_id)
                new_session = str(uuid.uuid4())
                text = await self._run(message_id, adapter, request(None, new_session), buf)
            if new_session:
                with session() as s:
                    s.get(Chat, chat_id).claude_session = new_session
            meta = await self._collect_outputs(message_id, out_dir, question, project_name)
            if ws:
                self._activity(message_id, "Değişiklikler", "kontrol ediliyor")
                if await sessions.finish_turn(ws, question, text, adapter.info.id):
                    meta["task_id"] = ws.task_id
                    text, reviewed = await self._review(
                        message_id, ws, question, text, adapter, fix_request
                    )
                    if reviewed:
                        meta["review"] = reviewed
            self._finish(message_id, text, "done", adapter.info.id, meta)
            if time.monotonic() - started > NOTIFY_AFTER_S:
                notify.send("Orbit yanıt verdi", question.strip().splitlines()[0][:120])
        except QuotaExceeded as e:
            self._pause(message_id, e, buf)
            await self._close_turn(ws)
        except AdapterError as e:
            partial = "".join(buf).strip()
            if message_id in self._cancelling:
                stopped = (partial + "\n\n" if partial else "") + "_(durduruldu)_"
                self._finish(message_id, stopped, "cancelled", adapter.info.id)
            else:
                failed = (partial + "\n\n" if partial else "") + f"⚠ {e}"
                self._finish(message_id, failed, "error", adapter.info.id)
            await self._close_turn(ws)
        except Exception as e:
            self._finish(message_id, f"⚠ Beklenmeyen hata: {e!r}", "error")
            await self._close_turn(ws)
        finally:
            self._runs.pop(message_id, None)
            self._cancelling.discard(message_id)
            self._codex_wrote.discard(message_id)

    async def _run(self, message_id: int, adapter, req: RunRequest, buf: list[str]) -> str:
        run_id = uuid.uuid4().hex
        self._runs[message_id] = (adapter.info.id, run_id)
        async for ev in adapter.run(req, run_id):
            if ev.kind == "delta":
                buf.append(ev.data["text"])
                broker.publish(
                    {"type": "message_delta", "message_id": message_id, "text": ev.data["text"]}
                )
            elif ev.kind == "tool":
                if ev.data.get("name") == CODEX_TOOL:
                    self._codex_wrote.add(message_id)
                tool = security.redact_data(ev.data)
                broker.publish({"type": "message_activity", "message_id": message_id, "tool": tool})
            elif ev.kind == "result":
                return ev.data.get("text") or "".join(buf)
            elif ev.kind == "error":
                raise AdapterError(ev.data.get("text") or "Bilinmeyen hata")
        raise AdapterError("Model yanıtı tamamlamadan durdu.")

    async def _codex_ready(self) -> bool:
        if self.registry.get("codex") is None:
            return False
        return (await self.registry.health("codex")).state == ModelState.AVAILABLE

    async def _result(self, message_id: int, adapter, req: RunRequest, who: str) -> dict:
        """Run to completion and return the result event (e.g. structured output)."""
        run_id = uuid.uuid4().hex
        self._runs[message_id] = (adapter.info.id, run_id)
        async for ev in adapter.run(req, run_id):
            if ev.kind == "tool":
                tool = security.redact_data({**ev.data, "agent": ev.data.get("agent") or who})
                broker.publish({"type": "message_activity", "message_id": message_id, "tool": tool})
            elif ev.kind == "result":
                return ev.data
            elif ev.kind == "error":
                raise AdapterError(ev.data.get("text") or "Bilinmeyen hata")
        raise AdapterError("Model yanıtı tamamlamadan durdu.")

    def _append(self, message_id: int, text: str) -> None:
        broker.publish({"type": "message_delta", "message_id": message_id, "text": text})

    async def _review(
        self,
        message_id: int,
        ws: sessions.Workspace,
        question: str,
        text: str,
        author,
        fix_request,
    ) -> tuple[str, dict[str, Any] | None]:
        """Another model reviews the change; the lead fixes what is serious (one round)."""
        if assistant.quality() == "economy":
            return text, None
        # The reviewer is someone who didn't write it: neither the lead nor Codex if it built.
        authors = {author.info.id} | ({"codex"} if message_id in self._codex_wrote else set())
        avoid = frozenset(authors)
        reviewer = (await self.router.pick("review", needs_tools=True, avoid=avoid)).adapter
        if reviewer is None:
            return text, None
        independent = reviewer.info.id not in authors
        diff = await sessions.diff(ws.task_id)
        if not review.wanted(independent, diff):
            return text, None
        name = reviewer.info.name if independent else f"{reviewer.info.name} (ayrı oturum)"
        with session() as s:
            results = s.get(Task, ws.task_id).checks or []
        self._activity(message_id, name, "değişiklikleri inceliyor")
        sessions.log(ws.task_id, f"Bağımsız inceleme: {name}")
        req = RunRequest(
            prompt=review.prompt(question, diff, results, card.read(ws.cwd)),
            cwd=ws.cwd,
            system_prompt=review.SYSTEM,
            json_schema=review.SCHEMA,
            tools=review.READ_ONLY,
            permission_mode="dontAsk",
            settings=assistant.settings(review.READ_ONLY),
            effort=assistant.effort(),
        )
        try:
            data = await self._result(message_id, reviewer, req, name)
        except AdapterError as e:  # incl. quota: the change stays, just unreviewed
            if message_id in self._cancelling:
                return text + "\n\n_(inceleme durduruldu)_", None
            sessions.log(ws.task_id, f"İnceleme yapılamadı: {e}")
            return text, None
        finally:
            await discard_uncommitted(ws.wt)  # a reviewer never leaves changes behind
        r = review.parse(name, data.get("structured"))
        if r is None:
            sessions.log(ws.task_id, f"{name} incelemesi okunamadı.")
            return text, None
        sessions.log(ws.task_id, f"{name}: {r.summary} ({len(r.issues)} bulgu)")
        note = review.report(r)
        self._append(message_id, note)
        text += note
        if not r.serious:
            return text, r.as_meta(fixed=False)

        self._activity(message_id, author.info.name, "inceleme bulgularını düzeltiyor")
        buf: list[str] = []
        try:
            fix_text = await self._run(message_id, author, fix_request(review.fix_prompt(r)), buf)
        except AdapterError as e:
            partial = "".join(buf).strip()
            if message_id in self._cancelling:
                return text + partial + "\n\n_(düzeltme durduruldu)_", r.as_meta(fixed=False)
            sessions.log(ws.task_id, f"İnceleme düzeltmesi yapılamadı: {e}")
            return text + partial + f"\n\n⚠ Düzeltme yapılamadı: {e}", r.as_meta(fixed=False)
        text += fix_text
        title = f"İnceleme düzeltmeleri ({r.by})"
        fixed = await sessions.finish_turn(ws, title, fix_text, author.info.id)
        return text, r.as_meta(fixed=fixed)

    async def _collect_outputs(
        self, message_id: int, out_dir: Path, question: str, project_name: str | None
    ) -> dict[str, Any]:
        """Designs the assistant drew are rendered; reports it wrote are kept."""
        meta: dict[str, Any] = {}
        if variants := designs.collect(out_dir):
            self._activity(message_id, "Tasarımlar", f"{len(variants)} ekran çiziliyor")
            meta["variants"] = await designs.render(message_id, variants)
        reports = [
            str(
                save_report(p.read_text(encoding="utf-8", errors="replace"), question, project_name)
            )
            for p in sorted(out_dir.glob("*.md"))
        ]
        if reports:
            meta["reports"] = reports
        return meta

    async def _close_turn(self, ws: sessions.Workspace | None) -> None:
        """A turn that ended early still leaves the session reviewable."""
        if ws is None:
            return
        with contextlib.suppress(GitError):
            await sessions.to_review(ws.task_id)

    # ---------- quota: wait for the reset, then continue the same turn ----------

    def _pause(self, message_id: int, e: QuotaExceeded, buf: list[str]) -> None:
        resume_at = e.resets_at + RESUME_MARGIN_S if e.resets_at else int(time.time()) + 30 * 60
        at = datetime.fromtimestamp(resume_at).strftime("%H:%M")
        partial = "".join(buf).strip()
        text = (partial + "\n\n" if partial else "") + (
            f"⏸ Claude kotası doldu. {at} civarında bu yanıta kendiliğinden devam edeceğim; "
            "ücretli kullanıma geçilmez."
        )
        self._finish(message_id, text, "waiting", None, {"resume_at": resume_at})
        notify.send("Kota doldu", f"Orbit {at} civarında devam edecek.")
        self._schedule(message_id, resume_at)

    def _schedule(self, message_id: int, resume_at: int) -> None:
        async def later() -> None:
            await asyncio.sleep(max(0.0, resume_at - time.time()))
            self.resume_now(message_id)

        self._spawn(later())

    def resume_now(self, message_id: int) -> bool:
        with session() as s:
            m = s.get(Message, message_id)
            if m is None or m.status != "waiting":
                return False
            busy = s.scalar(
                select(Message.id).where(
                    Message.chat_id == m.chat_id, Message.status == "streaming"
                )
            )
            if busy:  # another reply is being written in this chat; try again shortly
                self._schedule(message_id, int(time.time()) + 60)
                return False
            m.status, m.content = "streaming", ""
            payload = serialize.message(m)
        broker.publish({"type": "message", "message": payload})
        self.start_reply(message_id)
        return True

    # ---------- stop / lifecycle ----------

    async def cancel(self, message_id: int) -> dict[str, Any]:
        with session() as s:
            m = s.get(Message, message_id)
            if m is None:
                raise LookupError(message_id)
            payload = serialize.message(m)
        if payload["status"] == "waiting":
            self._finish(message_id, payload["content"] + "\n\n_(durduruldu)_", "cancelled")
            return payload
        if payload["status"] != "streaming":
            return payload
        run = self._runs.get(message_id)
        if run and (adapter := self.registry.get(run[0])):
            # The turn sees the flag, saves the partial answer and marks it cancelled
            # in one write, so nobody ever sees a cancelled message without its text.
            self._cancelling.add(message_id)
            await adapter.cancel(run[1])
        else:
            self._finish(message_id, "_(durduruldu)_", "cancelled")
        return payload

    def recover(self) -> None:
        sessions.recover()
        with session() as s:
            for m in s.scalars(select(Message).where(Message.status == "streaming")):
                m.status = "error"
                m.content = (
                    "⚠ Sunucu yeniden başlatıldı; yanıt yarıda kaldı. "
                    "Mesajını tekrar gönderebilirsin."
                )
            waiting = [
                (m.id, (m.meta or {}).get("resume_at") or 0)
                for m in s.scalars(select(Message).where(Message.status == "waiting"))
            ]
        for message_id, resume_at in waiting:
            self._schedule(message_id, resume_at)

    async def shutdown(self) -> None:
        for adapter_id, run_id in list(self._runs.values()):
            if adapter := self.registry.get(adapter_id):
                await adapter.cancel(run_id)


def _checks_block(cfg: dict[str, Any]) -> str:
    """Tell the assistant which commands Orbit will verify its changes with."""
    if not cfg.get("commands"):
        return ""
    lines = [f"- {c['name']}: {c['command']}" for c in cfg["commands"]]
    if cfg.get("setup"):
        lines.insert(0, f"- (kurulum) {cfg['setup']}")
    return (
        "KALİTE KONTROLLERİ (değişikliklerinden sonra Orbit bunları çalıştırır; işini bunlarla "
        "doğrula):\n" + "\n".join(lines) + "\n\n"
    )
