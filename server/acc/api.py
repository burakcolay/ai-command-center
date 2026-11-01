import base64
import binascii
import re
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from acc import (
    attachments,
    checks,
    config,
    designs,
    gitops,
    memory,
    notify,
    prefs,
    routing,
    serialize,
    templates,
)
from acc.adapters import registry
from acc.agents import AGENTS
from acc.chat import ChatService, context_for_task
from acc.db import session
from acc.models import (
    Approval,
    ApprovalStatus,
    AuditLog,
    Chat,
    Message,
    Project,
    Task,
    TaskEvent,
    TaskKind,
    TaskStage,
    TaskStatus,
    Template,
)
from acc.orchestrator import Decision, ExecError, InvalidTransition, Orchestrator

router = APIRouter(prefix="/api")
orchestrator = Orchestrator(registry)
chat_service = ChatService(registry)


# ---------- projects ----------


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    path: str | None = None  # existing folder; empty = create new under workspace/projects


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "proje"


@router.get("/projects")
def list_projects():
    with session() as s:
        return [serialize.project(p) for p in s.scalars(select(Project).order_by(Project.name))]


@router.post("/projects", status_code=201)
async def create_project(body: ProjectIn):
    name = body.name.strip()
    if body.path:
        path = Path(body.path).expanduser().resolve()
        if not path.is_dir():
            raise HTTPException(400, f"Klasör bulunamadı: {path}")
    else:
        path = (config.WORKSPACE_DIR / _slug(name)).resolve()
        if path.exists():
            raise HTTPException(409, f"Bu klasör zaten var: {path}")
        path.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
        await gitops.initial_commit(path)  # worktrees need at least one commit
    with session() as s:
        if s.scalar(select(Project).where(Project.name == name)):
            raise HTTPException(409, "Bu isimde bir proje zaten var.")
        p = Project(name=name, path=str(path))
        s.add(p)
        s.flush()
        s.add(
            AuditLog(
                actor="user",
                action="project.create",
                target=f"project:{p.id}",
                data={"path": str(path)},
            )
        )
        return serialize.project(p)


class MemoryIn(BaseModel):
    content: str = Field(max_length=500_000)


def _project_name(project_id: int) -> str:
    with session() as s:
        p = s.get(Project, project_id)
        if p is None:
            raise HTTPException(404)
        return p.name


@router.get("/projects/{project_id}/memory")
def get_memory(project_id: int):
    name = _project_name(project_id)
    return {"path": str(memory.path_for(name)), "content": memory.read(name)}


@router.put("/projects/{project_id}/memory")
def put_memory(project_id: int, body: MemoryIn):
    name = _project_name(project_id)
    path = memory.write(name, body.content)
    with session() as s:
        s.add(AuditLog(actor="user", action="memory.update", target=f"project:{project_id}"))
    return {"path": str(path), "content": memory.read(name)}


class CheckCommand(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    command: str = Field(min_length=1, max_length=1000)


class ChecksConfig(BaseModel):
    setup: str | None = Field(default=None, max_length=1000)
    commands: list[CheckCommand] = Field(default_factory=list, max_length=20)


class ChecksIn(BaseModel):
    config: ChecksConfig | None = None  # None = back to auto-detection


@router.get("/projects/{project_id}/checks")
def get_checks(project_id: int):
    with session() as s:
        p = s.get(Project, project_id)
        if p is None:
            raise HTTPException(404)
        path, configured = Path(p.path), p.checks
    detected = checks.detect(path) if path.is_dir() else {"setup": None, "commands": []}
    return {
        "configured": configured,
        "detected": detected,
        "effective": configured if configured is not None else detected,
        "sandbox": checks.sandbox_available(),
    }


@router.put("/projects/{project_id}/checks")
def put_checks(project_id: int, body: ChecksIn):
    cfg = None
    if body.config is not None:
        cfg = body.config.model_dump()
        cfg["setup"] = (cfg["setup"] or "").strip() or None
    with session() as s:
        p = s.get(Project, project_id)
        if p is None:
            raise HTTPException(404)
        p.checks = cfg
        s.add(
            AuditLog(
                actor="user",
                action="checks.update",
                target=f"project:{project_id}",
                data={"config": cfg},
            )
        )
    return get_checks(project_id)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int):
    """Removes the project from the app only. Files on disk are never deleted."""
    with session() as s:
        p = s.get(Project, project_id)
        if p is None:
            raise HTTPException(404)
        s.delete(p)
        s.add(AuditLog(actor="user", action="project.remove", target=f"project:{project_id}"))


# ---------- chats & messages ----------


class ChatIn(BaseModel):
    project_id: int | None = None


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)  # long specs can be pasted
    project_id: int | None = None
    # chat: talk it through (nothing changes) · task: plan → approve → execute
    mode: Literal["chat", "task", "research", "edit", "design"] = "task"
    attachments: list[str] = Field(default_factory=list, max_length=6)
    # chat only: which model answers (None = default, Claude). e.g. "ollama"
    model: str | None = Field(default=None, max_length=64)


@router.get("/chats")
def list_chats():
    with session() as s:
        rows = s.scalars(select(Chat).order_by(Chat.id.desc()).limit(100))
        return [serialize.chat(c) for c in rows]


@router.post("/chats", status_code=201)
def create_chat(body: ChatIn):
    with session() as s:
        c = Chat(project_id=body.project_id)
        s.add(c)
        s.flush()
        return serialize.chat(c)


@router.get("/chats/{chat_id}")
def get_chat(chat_id: int):
    with session() as s:
        c = s.get(Chat, chat_id)
        if c is None:
            raise HTTPException(404)
        msgs = s.scalars(select(Message).where(Message.chat_id == chat_id).order_by(Message.id))
        tasks = s.scalars(select(Task).where(Task.chat_id == chat_id))
        return {
            "chat": serialize.chat(c),
            "messages": [serialize.message(m) for m in msgs],
            "tasks": [serialize.task_full(s, t) for t in tasks],
        }


@router.delete("/chats/{chat_id}", status_code=204)
def delete_chat(chat_id: int):
    with session() as s:
        c = s.get(Chat, chat_id)
        if c is None:
            raise HTTPException(404)
        s.delete(c)


@router.post("/chats/{chat_id}/messages", status_code=201)
async def post_message(chat_id: int, body: MessageIn):
    content = body.content.strip()
    with session() as s:
        c = s.get(Chat, chat_id)
        if c is None:
            raise HTTPException(404)
        if body.project_id is not None:
            if s.get(Project, body.project_id) is None:
                raise HTTPException(400, "Proje bulunamadı.")
            c.project_id = body.project_id
        for attachment_id in body.attachments:
            try:
                attachments.resolve(attachment_id)
            except attachments.AttachmentError as e:
                raise HTTPException(400, str(e)) from None
        if body.mode in ("chat", "research", "design") and s.scalar(
            select(Message.id).where(Message.chat_id == chat_id, Message.status == "streaming")
        ):
            raise HTTPException(409, "Önceki yanıt hâlâ yazılıyor.")
        if c.title == "Yeni sohbet":
            c.title = content[:60]
        user_msg = Message(
            chat_id=chat_id,
            role="user",
            content=content,
            meta={"attachments": body.attachments} if body.attachments else None,
        )
        s.add(user_msg)
        s.flush()
        task = None
        new_edit = None
        if body.mode == "edit":
            if c.project_id is None:
                raise HTTPException(400, "Düzenleme için önce bir proje seç.")
            context = context_for_task(s, c, before_id=user_msg.id)
            task = s.scalars(
                select(Task)
                .where(
                    Task.chat_id == chat_id,
                    Task.kind == TaskKind.SESSION,
                    Task.status.not_in([TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
                )
                .order_by(Task.id.desc())
            ).first()
            if task is None:
                task = Task(
                    chat_id=chat_id,
                    project_id=c.project_id,
                    request=content,
                    context=context,
                    title=content[:80],
                    kind=TaskKind.SESSION,
                    stage=TaskStage.EXECUTE,
                    status=TaskStatus.QUEUED,
                )
                s.add(task)
                s.flush()
            if body.attachments:
                task.attachments = [*(task.attachments or []), *body.attachments]
            new_edit = (task.id, content, context)
            reply = Message(chat_id=chat_id, role="task", content="", task_id=task.id)
        elif body.mode == "design":
            reply = Message(
                chat_id=chat_id,
                role="assistant",
                content="",
                status="streaming",
                meta={"kind": "design"},
            )
        elif body.mode == "research":
            reply = Message(
                chat_id=chat_id,
                role="assistant",
                content="",
                status="streaming",
                meta={"kind": "research"},
            )
        elif body.mode == "chat":
            if body.model and registry.get(body.model) is None:
                raise HTTPException(400, "Bilinmeyen model.")
            reply = Message(
                chat_id=chat_id,
                role="assistant",
                content="",
                status="streaming",
                adapter_id=body.model,
            )
        else:
            # The conversation so far travels with the task to the planner and the agents.
            context = context_for_task(s, c, before_id=user_msg.id)
            task = Task(
                chat_id=chat_id,
                project_id=c.project_id,
                request=content,
                context=context,
                title=content[:80],
                attachments=body.attachments or None,
            )
            s.add(task)
            s.flush()
            reply = Message(chat_id=chat_id, role="task", content="", task_id=task.id)
        s.add(reply)
        s.flush()
        result = {
            "chat": serialize.chat(c),
            "messages": [serialize.message(user_msg), serialize.message(reply)],
            "task": serialize.task_full(s, task) if task else None,
        }
    if new_edit:
        orchestrator.add_edit(*new_edit)
        with session() as s:
            result["task"] = serialize.task_full(s, s.get(Task, new_edit[0]))
    elif task:
        orchestrator.start_planning(result["task"]["id"])
    else:
        chat_service.start_reply(result["messages"][1]["id"])
    return result


class UploadIn(BaseModel):
    name: str = Field(default="görsel", max_length=200)
    data: str = Field(max_length=14_000_000)  # base64; ~10 MB of image


@router.post("/uploads", status_code=201)
def upload(body: UploadIn):
    try:
        raw = base64.b64decode(body.data, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Görsel okunamadı.") from None
    try:
        return attachments.save_upload(raw, body.name)
    except attachments.AttachmentError as e:
        raise HTTPException(400, str(e)) from None


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: str):
    path = attachments.upload_path(upload_id)
    if path is None:
        raise HTTPException(404)
    return FileResponse(path)


@router.get("/designs/{message_id}/{n}.png")
def get_design(message_id: int, n: int):
    path = designs.folder(message_id) / f"v{n}.png"
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/png")


@router.post("/messages/{message_id}/cancel")
async def cancel_message(message_id: int):
    try:
        return await chat_service.cancel(message_id)
    except LookupError:
        raise HTTPException(404) from None


# ---------- tasks & approvals ----------


class DecisionIn(BaseModel):
    decision: Decision
    note: str | None = Field(default=None, max_length=5000)


@router.get("/tasks/{task_id}/events")
def task_events(task_id: int):
    with session() as s:
        rows = s.scalars(
            select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.id)
        )
        return [serialize.event(e) for e in rows]


@router.post("/tasks/{task_id}/decision")
async def decide(task_id: int, body: DecisionIn):
    try:
        return await orchestrator.decide(task_id, body.decision, body.note)
    except LookupError:
        raise HTTPException(404) from None
    except InvalidTransition as e:
        raise HTTPException(409, str(e)) from None


@router.get("/tasks/{task_id}/diff")
async def task_diff(task_id: int):
    try:
        return await orchestrator.diff(task_id)
    except LookupError:
        raise HTTPException(404) from None
    except (ExecError, gitops.GitError) as e:
        raise HTTPException(409, str(e)) from None


@router.get("/approvals")
def list_approvals(status: str = ApprovalStatus.PENDING):
    with session() as s:
        q = select(Approval, Task).join(Task, Task.id == Approval.task_id)
        if status != "all":
            q = q.where(Approval.status == status)
        rows = s.execute(q.order_by(Approval.id.desc()).limit(200)).all()
        return [{**serialize.approval(a), "task": serialize.task(t)} for a, t in rows]


# ---------- models & agents ----------


@router.get("/models")
async def list_models(fresh: bool = False):
    out = []
    for a in registry.all():
        h = await registry.health(a.info.id, fresh=fresh)
        u = await a.usage_status()
        out.append(
            {
                "id": a.info.id,
                "name": a.info.name,
                "provider": a.info.provider,
                "billing": a.info.billing,
                "auth_method": a.info.auth_method,
                "requires_membership": a.info.requires_membership,
                "requires_api_key": a.info.requires_api_key,
                "notes": a.info.notes,
                "capabilities": a.capabilities.__dict__,
                "state": h.state,
                "detail": h.detail,
                "data": h.data,
                "usage": {
                    "source": u.source,
                    "detail": u.detail,
                    "observed_at": u.observed_at,
                    "windows": [w.__dict__ for w in u.windows],
                },
            }
        )
    return out


@router.get("/agents")
def list_agents():
    return [
        {**a.__dict__, "work": routing.AGENT_WORK.get(a.id), "work_label": _work_label(a.id)}
        for a in AGENTS.values()
    ]


def _work_label(agent_id: str) -> str | None:
    kind = routing.WORK_KINDS.get(routing.AGENT_WORK.get(agent_id, ""))
    return kind.label if kind else None


@router.get("/routing")
async def get_routing():
    return await orchestrator.router.describe()


class RouteIn(BaseModel):
    adapter: str = Field(max_length=64)


@router.put("/routing/{kind}")
async def put_routing(kind: str, body: RouteIn):
    if kind not in routing.WORK_KINDS:
        raise HTTPException(404)
    if body.adapter != "auto":
        adapter = registry.get(body.adapter)
        if adapter is None or orchestrator.router.eligible(kind, adapter, False):
            raise HTTPException(400, "Bu model bu işi yapamaz.")
    current = dict(routing.overrides())
    current[kind] = body.adapter
    prefs.put("routing", current)
    return await orchestrator.router.describe()


class PrefIn(BaseModel):
    value: bool | int | str | None


@router.put("/preferences/{key}")
def put_preference(key: str, body: PrefIn):
    try:
        prefs.put(key, body.value)
    except KeyError:
        raise HTTPException(400, "Bilinmeyen ayar.") from None
    except ValueError:
        raise HTTPException(400, "Geçersiz değer.") from None
    if key == "ollama_model":
        registry.invalidate("ollama")
    return {"key": key, "value": body.value}


class TemplateIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=20_000)
    mode: Literal["chat", "task", "research", "design", "edit"] = "task"


@router.get("/templates")
def list_templates():
    with session() as s:
        custom = [
            {
                "id": f"u-{t.id}",
                "title": t.title,
                "body": t.body,
                "mode": t.mode,
                "description": "Kayıtlı şablon",
                "custom": True,
            }
            for t in s.scalars(select(Template).order_by(Template.id.desc()))
        ]
    return custom + [{**t, "custom": False} for t in templates.BUILTIN]


@router.post("/templates", status_code=201)
def create_template(body: TemplateIn):
    with session() as s:
        t = Template(title=body.title.strip(), body=body.body, mode=body.mode)
        s.add(t)
        s.flush()
        return {"id": f"u-{t.id}"}


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: str):
    if not template_id.startswith("u-") or not template_id[2:].isdigit():
        raise HTTPException(400, "Hazır şablonlar silinemez.")
    with session() as s:
        t = s.get(Template, int(template_id[2:]))
        if t is None:
            raise HTTPException(404)
        s.delete(t)


@router.post("/notify/test")
async def test_notification():
    return {"sent": notify.send("Orbit", "Bildirimler çalışıyor.", force=True)}


@router.get("/system")
def system_info():
    return {
        "demo_mode": config.DEMO_MODE,
        "paid_api_allowed": config.ALLOW_PAID_API,
        "notifications": prefs.get("notifications", True) is not False,
        "notifications_supported": notify.supported(),
        "sandbox_for_checks": checks.sandbox_available(),
        "memory_dir": str(config.MEMORY_DIR),
        "quality": prefs.get("quality", "balanced"),
        "claude_model": prefs.get("claude_model", "default"),
    }
