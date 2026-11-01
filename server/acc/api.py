import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from acc import config, serialize
from acc.adapters import registry
from acc.agents import AGENTS
from acc.db import session
from acc.models import Approval, ApprovalStatus, AuditLog, Chat, Message, Project, Task, TaskEvent
from acc.orchestrator import Decision, InvalidTransition, Orchestrator

router = APIRouter(prefix="/api")
orchestrator = Orchestrator(registry)


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
def create_project(body: ProjectIn):
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
        subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=False)
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
    content: str = Field(min_length=1, max_length=20000)
    project_id: int | None = None


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
            "tasks": [serialize.task(t) for t in tasks],
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
        if c.title == "Yeni sohbet":
            c.title = content[:60]
        user_msg = Message(chat_id=chat_id, role="user", content=content)
        t = Task(chat_id=chat_id, project_id=c.project_id, request=content, title=content[:80])
        s.add_all([user_msg, t])
        s.flush()
        task_msg = Message(chat_id=chat_id, role="task", content="", task_id=t.id)
        s.add(task_msg)
        s.flush()
        result = {
            "chat": serialize.chat(c),
            "messages": [serialize.message(user_msg), serialize.message(task_msg)],
            "task": serialize.task(t),
        }
    orchestrator.start_planning(result["task"]["id"])
    return result


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
