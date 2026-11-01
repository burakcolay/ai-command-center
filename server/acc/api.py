import re
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from acc import config, gitops, serialize
from acc.adapters import registry
from acc.agents import AGENTS
from acc.chat import ChatService, transcript
from acc.db import session
from acc.models import Approval, ApprovalStatus, AuditLog, Chat, Message, Project, Task, TaskEvent
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
    mode: Literal["chat", "task"] = "task"


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
        if body.mode == "chat" and s.scalar(
            select(Message.id).where(Message.chat_id == chat_id, Message.status == "streaming")
        ):
            raise HTTPException(409, "Önceki yanıt hâlâ yazılıyor.")
        if c.title == "Yeni sohbet":
            c.title = content[:60]
        user_msg = Message(chat_id=chat_id, role="user", content=content)
        s.add(user_msg)
        s.flush()
        task = None
        if body.mode == "chat":
            reply = Message(chat_id=chat_id, role="assistant", content="", status="streaming")
        else:
            # The conversation so far travels with the task to the planner and the agents.
            context = transcript(s, chat_id, before_id=user_msg.id) or None
            task = Task(
                chat_id=chat_id,
                project_id=c.project_id,
                request=content,
                context=context,
                title=content[:80],
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
    if task:
        orchestrator.start_planning(result["task"]["id"])
    else:
        chat_service.start_reply(result["messages"][1]["id"])
    return result


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
    return [a.__dict__ for a in AGENTS.values()]


@router.get("/system")
def system_info():
    return {"demo_mode": config.DEMO_MODE, "paid_api_allowed": config.ALLOW_PAID_API}
