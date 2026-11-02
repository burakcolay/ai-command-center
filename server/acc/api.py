import base64
import binascii
import contextlib
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from acc import (
    attachments,
    card,
    catalog,
    checks,
    config,
    designs,
    gitops,
    memory,
    notify,
    prefs,
    serialize,
    sessions,
    templates,
    tiers,
)
from acc.adapters import registry
from acc.chat import ChatService
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
    Template,
)
from acc.routing import WORK_KINDS, Router, overrides
from acc.sessions import InvalidTransition

router = APIRouter(prefix="/api")
chat_service = ChatService(registry)
model_router = Router(registry)


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


@router.get("/projects/{project_id}/card")
async def project_card(project_id: int):
    """The Project Card: the newest version, even if it is still waiting to be merged."""
    with session() as s:
        p = s.get(Project, project_id)
        if p is None:
            raise HTTPException(404)
        path = Path(p.path)
        pending = s.scalar(
            select(Task.worktree)
            .where(
                Task.project_id == project_id,
                Task.kind == TaskKind.SESSION,
                Task.status.not_in(sessions.OPEN),
                Task.worktree.is_not(None),
            )
            .order_by(Task.id.desc())
        )
    places: list[tuple[Path, str]] = []
    if pending:
        with contextlib.suppress(gitops.GitError):
            places.append((Path(pending) / (await gitops.repo_info(path)).rel, "pending"))
    places.append((path, "merged"))
    for folder, state in places:
        if text := card.read(folder):
            team = [
                {"name": a.name, "tech": a.tech, "folder": a.folder, "builder": a.builder}
                for a in card.team(text)
            ]
            return {"content": text, "state": state, "team": team}
    return {"content": None, "state": None, "team": []}


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
async def delete_project(project_id: int):
    """Removes the project from the app only. Files on disk are never deleted."""
    with session() as s:
        if s.get(Project, project_id) is None:
            raise HTTPException(404)
        open_ids = s.scalars(
            select(Task.id).where(
                Task.project_id == project_id,
                Task.kind == TaskKind.SESSION,
                Task.status.not_in(sessions.OPEN),
            )
        ).all()
    for task_id in open_ids:  # unmerged copies of this project go with it
        await sessions.close(task_id)
    with session() as s:
        s.delete(s.get(Project, project_id))
        s.add(AuditLog(actor="user", action="project.remove", target=f"project:{project_id}"))


# ---------- chats & messages ----------


class ChatIn(BaseModel):
    project_id: int | None = None


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)  # long specs can be pasted
    project_id: int | None = None
    attachments: list[str] = Field(default_factory=list, max_length=6)
    # The lead's model for this chat: Orbit decides ("auto") or "<provider>/<model id>".
    model_choice: str | None = Field(default=None, max_length=120)
    effort_choice: Literal["low", "medium", "high", "xhigh", "max", "ultra"] | None = None


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
async def delete_chat(chat_id: int):
    """Deletes the chat and its unmerged changes. The user's project is never touched."""
    with session() as s:
        if s.get(Chat, chat_id) is None:
            raise HTTPException(404)
        if s.scalar(
            select(Message.id).where(Message.chat_id == chat_id, Message.status == "streaming")
        ):
            raise HTTPException(409, "Yanıt yazılırken sohbet silinemez; önce durdur.")
    if (task_id := sessions.open_session_id(chat_id)) is not None:
        await sessions.close(task_id)
    with session() as s:
        s.delete(s.get(Chat, chat_id))
    shutil.rmtree(config.DATA_DIR / "chats" / str(chat_id), ignore_errors=True)


@router.post("/chats/{chat_id}/messages", status_code=201)
async def post_message(chat_id: int, body: MessageIn):
    """Every message is a turn for the one assistant; it decides what the message asks for."""
    content = body.content.strip()
    if body.model_choice and not catalog.valid(body.model_choice):
        raise HTTPException(422, "Geçersiz model seçimi.")
    for attachment_id in body.attachments:
        try:
            attachments.resolve(attachment_id)
        except attachments.AttachmentError as e:
            raise HTTPException(400, str(e)) from None
    with session() as s:
        c = s.get(Chat, chat_id)
        if c is None:
            raise HTTPException(404)
        switching = body.project_id is not None and body.project_id != c.project_id
        if switching and s.get(Project, body.project_id) is None:
            raise HTTPException(400, "Proje bulunamadı.")
    if switching and not await sessions.close_if_empty(chat_id):
        raise HTTPException(409, "Bu sohbette bekleyen değişiklikler var; önce birleştir ya da at.")
    with session() as s:
        c = s.get(Chat, chat_id)
        if s.scalar(
            select(Message.id).where(Message.chat_id == chat_id, Message.status == "streaming")
        ):
            raise HTTPException(409, "Önceki yanıt hâlâ yazılıyor.")
        if switching:
            c.project_id = body.project_id
            c.claude_session = None  # a different working folder needs a fresh conversation
        if body.model_choice:
            c.model_choice = body.model_choice
            c.effort_choice = body.effort_choice
        if c.title == "Yeni sohbet":
            c.title = content[:60]
        user_msg = Message(
            chat_id=chat_id,
            role="user",
            content=content,
            meta=(
                {
                    "attachments": body.attachments,
                    "files": [attachments.describe(a) for a in body.attachments],
                }
                if body.attachments
                else None
            ),
        )
        reply = Message(chat_id=chat_id, role="assistant", content="", status="streaming")
        s.add_all([user_msg, reply])
        s.flush()
        result = {
            "chat": serialize.chat(c),
            "messages": [serialize.message(user_msg), serialize.message(reply)],
        }
    chat_service.start_reply(result["messages"][1]["id"])
    return result


class UploadIn(BaseModel):
    name: str = Field(default="görsel", max_length=200)
    data: str = Field(max_length=14_000_000)  # base64; ~10 MB image or 1 MB text


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
    headers = {"X-Content-Type-Options": "nosniff"}
    if attachments.is_text(path):  # shown as plain text, never rendered as a page
        return FileResponse(path, media_type="text/plain; charset=utf-8", headers=headers)
    return FileResponse(path, headers=headers)


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


@router.post("/messages/{message_id}/resume")
async def resume_message(message_id: int):
    """A reply waiting for the quota reset: try again now."""
    if not chat_service.resume_now(message_id):
        raise HTTPException(409, "Bu yanıt beklemede değil.")
    return {"ok": True}


# ---------- changes (the chat's isolated project copy) ----------


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject", "undo_last", "rerun_checks", "open_pr"]


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
        return await sessions.decide(task_id, body.decision)
    except LookupError:
        raise HTTPException(404) from None
    except InvalidTransition as e:
        raise HTTPException(409, str(e)) from None


@router.get("/tasks/{task_id}/github")
async def task_github(task_id: int):
    """Can this chat's changes go to GitHub as a pull request?"""
    try:
        return await sessions.github_status(task_id)
    except (LookupError, AttributeError, gitops.GitError):
        raise HTTPException(404) from None


@router.get("/tasks/{task_id}/diff")
async def task_diff(task_id: int):
    try:
        return await sessions.diff(task_id)
    except LookupError:
        raise HTTPException(404) from None
    except InvalidTransition as e:
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


@router.get("/catalog")
async def model_catalog():
    """Every pickable model per provider, with the efforts each takes."""
    return await catalog.catalog(registry)


@router.get("/routing")
async def get_routing():
    return await model_router.describe()


class RouteIn(BaseModel):
    adapter: str = Field(max_length=64)


@router.put("/routing/{kind}")
async def put_routing(kind: str, body: RouteIn):
    if kind not in WORK_KINDS:
        raise HTTPException(404)
    if body.adapter != "auto":
        adapter = registry.get(body.adapter)
        if adapter is None or model_router.eligible(kind, adapter, False):
            raise HTTPException(400, "Bu model bu işi yapamaz.")
    prefs.put("routing", {**overrides(), kind: body.adapter})
    return await model_router.describe()


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


@router.get("/templates")
def list_templates():
    with session() as s:
        custom = [
            {
                "id": f"u-{t.id}",
                "title": t.title,
                "body": t.body,
                "description": "Kayıtlı şablon",
                "custom": True,
            }
            for t in s.scalars(select(Template).order_by(Template.id.desc()))
        ]
    return custom + [{**t, "custom": False} for t in templates.BUILTIN]


@router.post("/templates", status_code=201)
def create_template(body: TemplateIn):
    with session() as s:
        t = Template(title=body.title.strip(), body=body.body)
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
        "plan": {
            q: {
                role: {
                    "tier": power.tier,
                    "effort": power.effort,
                    "claude": tiers.model_name(tiers.CLAUDE[power.tier]),
                    "codex": tiers.model_name(tiers.CODEX[power.tier]),
                }
                for role, power in roles.items()
            }
            for q, roles in tiers.PRESETS.items()
        },
    }
