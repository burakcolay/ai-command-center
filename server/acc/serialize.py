from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from acc.models import Approval, Chat, Message, Project, Task, TaskEvent, TaskStep


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def project(p: Project) -> dict[str, Any]:
    return {"id": p.id, "name": p.name, "path": p.path, "created_at": _ts(p.created_at)}


def chat(c: Chat) -> dict[str, Any]:
    return {
        "id": c.id,
        "title": c.title,
        "project_id": c.project_id,
        "created_at": _ts(c.created_at),
    }


def message(m: Message) -> dict[str, Any]:
    return {
        "id": m.id,
        "chat_id": m.chat_id,
        "role": m.role,
        "content": m.content,
        "status": m.status,
        "task_id": m.task_id,
        "created_at": _ts(m.created_at),
    }


def step(st: TaskStep) -> dict[str, Any]:
    return {
        "id": st.id,
        "step_id": st.step_id,
        "seq": st.seq,
        "title": st.title,
        "agent": st.agent,
        "description": st.description,
        "kind": st.kind,
        "status": st.status,
        "summary": st.summary,
        "commit": st.commit,
        "adapter_id": st.adapter_id,
        "started_at": _ts(st.started_at),
        "finished_at": _ts(st.finished_at),
    }


def task_full(s: Session, t: Task) -> dict[str, Any]:
    steps = s.scalars(select(TaskStep).where(TaskStep.task_id == t.id).order_by(TaskStep.seq))
    return {**task(t), "steps": [step(st) for st in steps]}


def task(t: Task) -> dict[str, Any]:
    return {
        "id": t.id,
        "chat_id": t.chat_id,
        "project_id": t.project_id,
        "title": t.title,
        "request": t.request,
        "status": t.status,
        "plan": t.plan,
        "adapter_id": t.adapter_id,
        "error": t.error,
        "stage": t.stage,
        "branch": t.branch,
        "base_branch": t.base_branch,
        "merged_commit": t.merged_commit,
        "created_at": _ts(t.created_at),
        "updated_at": _ts(t.updated_at),
    }


def event(e: TaskEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "task_id": e.task_id,
        "kind": e.kind,
        "data": e.data,
        "created_at": _ts(e.created_at),
    }


def approval(a: Approval) -> dict[str, Any]:
    return {
        "id": a.id,
        "task_id": a.task_id,
        "kind": a.kind,
        "status": a.status,
        "note": a.note,
        "created_at": _ts(a.created_at),
        "decided_at": _ts(a.decided_at),
    }
