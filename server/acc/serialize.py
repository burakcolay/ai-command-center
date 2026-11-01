from typing import Any

from acc.models import Approval, Chat, Message, Project, Task, TaskEvent


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
        "task_id": m.task_id,
        "created_at": _ts(m.created_at),
    }


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
