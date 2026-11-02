"""Changes made in a chat, kept reviewable.

Each chat with a project gets one isolated git worktree (on branch orbit/task-<id>). Every
assistant turn that changes files becomes a commit there; Orbit then runs the project's
checks in the sandbox and shows the diff. The user merges, undoes the last change, or
discards everything. Nothing reaches the real project without that merge.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from acc import checks, config, github, gitops, memory, security, serialize
from acc.db import session
from acc.events import broker
from acc.gitops import GitError
from acc.models import (
    Approval,
    ApprovalStatus,
    AuditLog,
    Chat,
    Project,
    StepStatus,
    Task,
    TaskEvent,
    TaskKind,
    TaskStage,
    TaskStatus,
    TaskStep,
)
from acc.models import utcnow as _now

OPEN = (TaskStatus.COMPLETED, TaskStatus.CANCELLED)


class InvalidTransition(Exception):
    pass


@dataclass
class Workspace:
    task_id: int
    root: Path  # the user's repository
    wt: Path  # the isolated worktree
    cwd: Path  # project folder inside the worktree


def _publish(task_id: int) -> dict[str, Any]:
    with session() as s:
        payload = serialize.task_full(s, s.get(Task, task_id))
    broker.publish({"type": "task", "task": payload})
    return payload


def _update(task_id: int, **fields: Any) -> dict[str, Any]:
    with session() as s:
        t = s.get(Task, task_id)
        for k, v in fields.items():
            setattr(t, k, v)
    return _publish(task_id)


def log(task_id: int, text: str, kind: str = "log") -> None:
    with session() as s:
        ev = TaskEvent(task_id=task_id, kind=kind, data={"text": security.redact(text)})
        s.add(ev)
        s.flush()
        payload = serialize.event(ev)
    broker.publish({"type": "event", "event": payload})


def worktree_path(chat_id: int) -> Path:
    # One path per chat: the assistant's conversation (tied to its working folder) survives
    # merges, which replace the worktree with a fresh one from the updated branch.
    return config.WORKTREES_DIR / f"chat-{chat_id}"


def open_session_id(chat_id: int) -> int | None:
    with session() as s:
        return s.scalar(
            select(Task.id)
            .where(Task.chat_id == chat_id, Task.kind == TaskKind.SESSION, Task.status.not_in(OPEN))
            .order_by(Task.id.desc())
        )


async def workspace(chat_id: int) -> Workspace:
    """The chat's isolated project copy, created on first use. Raises GitError if impossible."""
    with session() as s:
        chat = s.get(Chat, chat_id)
        project = s.get(Project, chat.project_id)
        project_path = Path(project.path)
    info = await gitops.repo_info(project_path)
    task_id = open_session_id(chat_id)
    if task_id is None:
        if info.branch is None:
            raise GitError("Projede HEAD detached durumda; önce bir branch'e geç.")
        with session() as s:
            t = Task(
                chat_id=chat_id,
                project_id=chat.project_id,
                kind=TaskKind.SESSION,
                request="",
                title="Değişiklikler",
                stage=TaskStage.EXECUTE,
                status=TaskStatus.RUNNING,
                base_branch=info.branch,
                base_commit=info.head,
                worktree=str(worktree_path(chat_id)),
            )
            s.add(t)
            s.flush()
            task_id = t.id
            t.branch = f"orbit/task-{task_id}"
        if info.dirty:
            log(task_id, "Projede commitlenmemiş değişiklikler var; çalışma son commit üzerinden.")
    with session() as s:
        t = s.get(Task, task_id)
        wt, branch, base = Path(t.worktree), t.branch, t.base_commit
    await gitops.ensure_worktree(info.root, wt, branch, base)
    _update(task_id, status=TaskStatus.RUNNING, stage=TaskStage.EXECUTE, error=None)
    return Workspace(task_id, info.root, wt, wt / info.rel)


def failed_checks_block(task_id: int) -> str:
    """Checks that failed after the last change, so "düzelt" needs no copy-pasting."""
    with session() as s:
        results = s.get(Task, task_id).checks or []
    failed = [r for r in results if r.get("status") == "failed"]
    if not failed:
        return ""
    parts = [
        f"### {r['name']} ({r.get('command', '')})\n{(r.get('output') or '')[-1500:]}"
        for r in failed
    ]
    return (
        "BAŞARISIZ KONTROLLER (son değişiklikten sonra; kullanıcı düzeltmeni isterse bunlara bak, "
        "testleri silerek ya da gevşeterek geçirme):\n" + "\n\n".join(parts) + "\n\n"
    )


def checks_config(task_id: int, cwd: Path) -> dict[str, Any]:
    with session() as s:
        configured = s.get(Project, s.get(Task, task_id).project_id).checks
    return checks.effective(configured, cwd)


async def finish_turn(ws: Workspace, request: str, summary: str, adapter_id: str | None) -> bool:
    """Commit what the turn changed, check it, and put the session up for review."""
    commit = await gitops.commit_all(ws.wt, f"orbit: {request.strip().splitlines()[0][:72]}")
    if commit:
        with session() as s:
            last = s.scalar(select(func.max(TaskStep.seq)).where(TaskStep.task_id == ws.task_id))
            seq = 0 if last is None else last + 1
            s.add(
                TaskStep(
                    task_id=ws.task_id,
                    seq=seq,
                    step_id=f"d{seq + 1}",
                    title=request[:300],
                    agent="assistant",
                    description=request,
                    kind="edit",
                    status=StepStatus.DONE,
                    summary=summary[:4000],
                    commit=commit,
                    adapter_id=adapter_id,
                    started_at=_now(),
                    finished_at=_now(),
                )
            )
        await run_checks(ws)
    await to_review(ws.task_id)
    return commit is not None


async def run_checks(ws: Workspace) -> None:
    cfg = checks_config(ws.task_id, ws.cwd)
    if not cfg["commands"]:
        _update(ws.task_id, checks=[])
        return
    log(
        ws.task_id,
        "Kalite kontrolleri çalışıyor (sandbox): " + ", ".join(c["name"] for c in cfg["commands"]),
    )
    results = await checks.run(cfg, ws.wt, ws.cwd, ws.task_id)
    await gitops.discard(ws.wt)  # checks never leave changes behind
    _update(ws.task_id, checks=results)
    log(ws.task_id, f"Kalite kontrolleri: {checks.summary(results)}")


async def to_review(task_id: int) -> None:
    with session() as s:
        t = s.get(Task, task_id)
        wt, base = Path(t.worktree), t.base_commit
        for a in s.scalars(
            select(Approval).where(
                Approval.task_id == task_id, Approval.status == ApprovalStatus.PENDING
            )
        ):
            a.status, a.decided_at = ApprovalStatus.CANCELLED, _now()
    d = await gitops.diff(wt, base)
    if d["files"]:
        with session() as s:
            s.add(Approval(task_id=task_id, kind="merge"))
    _update(task_id, status=TaskStatus.WAITING_APPROVAL, stage=TaskStage.MERGE)
    broker.publish({"type": "approvals_changed"})


async def diff(task_id: int) -> dict[str, Any]:
    with session() as s:
        t = s.get(Task, task_id)
        if t is None:
            raise LookupError(task_id)
        wt, base, branch = t.worktree, t.base_commit, t.branch
    if not (wt and base and Path(wt).is_dir()):
        raise InvalidTransition("Bu sohbet için incelenecek değişiklik yok.")
    return {**await gitops.diff(Path(wt), base), "branch": branch}


async def _workspace_of(task_id: int) -> Workspace:
    with session() as s:
        t = s.get(Task, task_id)
        project = s.get(Project, t.project_id)
        wt, path = Path(t.worktree), Path(project.path)
    info = await gitops.repo_info(path)
    return Workspace(task_id, info.root, wt, wt / info.rel)


async def decide(task_id: int, decision: str) -> dict[str, Any]:
    with session() as s:
        t = s.get(Task, task_id)
        if t is None or t.kind != TaskKind.SESSION:
            raise LookupError(task_id)
        status = TaskStatus(t.status)
    if status != TaskStatus.WAITING_APPROVAL:
        raise InvalidTransition("Asistan çalışırken değişiklikler üzerinde işlem yapılamaz.")
    ws = await _workspace_of(task_id)

    if decision == "approve":
        with session() as s:
            t = s.get(Task, task_id)
            branch, into = t.branch, t.base_branch
        try:
            merged = await gitops.merge(ws.root, branch, into, "Orbit: sohbetten değişiklikler")
        except GitError as e:
            raise InvalidTransition(str(e)) from None
        _resolve(task_id, ApprovalStatus.APPROVED)
        _record_decision(task_id, merged)
        payload = _update(
            task_id, status=TaskStatus.COMPLETED, stage=TaskStage.DONE, merged_commit=merged
        )
        log(task_id, f"Projeye birleştirildi ({merged[:8]}).")
        await cleanup(task_id, merged=True)
        return payload

    if decision == "reject":
        _resolve(task_id, ApprovalStatus.REJECTED)
        payload = _update(task_id, status=TaskStatus.CANCELLED)
        log(task_id, "Değişiklikler atıldı.")
        if payload.get("pr_url"):
            log(task_id, f"GitHub'daki PR açık kaldı; kapatmak için: {payload['pr_url']}")
        await cleanup(task_id, merged=False)
        return payload

    if decision == "undo_last":
        with session() as s:
            last = s.scalars(
                select(TaskStep)
                .where(
                    TaskStep.task_id == task_id,
                    TaskStep.status == StepStatus.DONE,
                    TaskStep.commit.is_not(None),
                )
                .order_by(TaskStep.seq.desc())
            ).first()
            if last is None:
                raise InvalidTransition("Geri alınacak değişiklik yok.")
            commit, step_pk, title = last.commit, last.id, last.title
        try:
            await gitops.undo_commit(ws.wt, commit)
        except GitError as e:
            raise InvalidTransition(str(e)) from None
        with session() as s:
            s.get(TaskStep, step_pk).status = StepStatus.REVERTED
        log(task_id, f"Geri alındı: {title[:120]}")
        await run_checks(ws)
        await to_review(task_id)
        return _publish(task_id)

    if decision == "rerun_checks":
        await run_checks(ws)
        await to_review(task_id)
        return _publish(task_id)

    if decision == "open_pr":
        return await _open_pr(task_id, ws)

    raise InvalidTransition(f"Bilinmeyen karar: {decision}")


async def github_status(task_id: int) -> dict[str, Any]:
    ws = await _workspace_of(task_id)
    st = await github.status(ws.root)
    return {"repo": st.repo, "ready": st.ready, "reason": st.reason}


def _pr_text(titles: list[str], results: list[dict[str, Any]]) -> tuple[str, str]:
    first = titles[0].strip().splitlines()[0]
    title = first[:72] + (f" (+{len(titles) - 1})" if len(titles) > 1 else "")
    body = ["Orbit sohbetinden hazırlanan değişiklikler.", "", "## İstekler"]
    body += [f"- {t.strip().splitlines()[0][:200]}" for t in titles]
    if results:
        mark = {"passed": "✓", "failed": "✗"}
        body += ["", "## Kalite kontrolleri (sandbox'ta ölçüldü)"]
        body += [f"- {mark.get(r.get('status'), '–')} {r['name']}" for r in results]
    return title, "\n".join(body)


async def _open_pr(task_id: int, ws: Workspace) -> dict[str, Any]:
    """Push Orbit's branch and open (or update) a pull request. Runs only on the user's click."""
    with session() as s:
        t = s.get(Task, task_id)
        branch, base, pr_url, results = t.branch, t.base_branch, t.pr_url, t.checks or []
        titles = s.scalars(
            select(TaskStep.title)
            .where(TaskStep.task_id == task_id, TaskStep.status == StepStatus.DONE)
            .order_by(TaskStep.seq)
        ).all()
    if not titles:
        raise InvalidTransition("GitHub'a gönderilecek değişiklik yok.")
    st = await github.status(ws.root)
    if not st.ready:
        raise InvalidTransition(st.reason)
    try:
        await github.push(ws.root, branch)
        if pr_url is None:
            title, body = _pr_text(list(titles), results)
            pr_url = await github.create_pr(ws.root, st.repo, branch, base, title, body)
            log(task_id, f"GitHub'da PR açıldı: {pr_url}")
        else:
            log(task_id, f"PR güncellendi: {pr_url}")
    except github.GitHubError as e:
        raise InvalidTransition(str(e)) from None
    with session() as s:
        s.add(AuditLog(actor="user", action="session.pr", target=f"task:{task_id} {pr_url}"))
    return _update(task_id, pr_url=pr_url)


def _resolve(task_id: int, status: ApprovalStatus) -> None:
    with session() as s:
        for a in s.scalars(
            select(Approval).where(
                Approval.task_id == task_id, Approval.status == ApprovalStatus.PENDING
            )
        ):
            a.status, a.decided_at = status, _now()
        s.add(AuditLog(actor="user", action=f"session.{status}", target=f"task:{task_id}"))
    broker.publish({"type": "approvals_changed"})


def _record_decision(task_id: int, merged: str) -> None:
    """Merged work goes into the project's decision log (project memory)."""
    with session() as s:
        project = s.get(Project, s.get(Task, task_id).project_id)
        steps = s.scalars(
            select(TaskStep.title).where(
                TaskStep.task_id == task_id, TaskStep.status == StepStatus.DONE
            )
        ).all()
        name = project.name
    if steps:
        what = "; ".join(t.strip().splitlines()[0][:80] for t in steps[:5])
        memory.append_decision(name, f"Sohbetten birleştirildi: {what} · `{merged[:8]}`")


async def cleanup(task_id: int, merged: bool) -> None:
    """Remove the worktree and its branch. Never touches the user's working tree."""
    with session() as s:
        t = s.get(Task, task_id)
        project = s.get(Project, t.project_id) if t.project_id else None
        wt, branch = t.worktree, t.branch
    if not (wt and branch and project):
        return
    try:
        info = await gitops.repo_info(Path(project.path))
        await gitops.remove_worktree(info.root, Path(wt), branch, merged)
    except GitError as e:
        log(task_id, f"Çalışma kopyası temizlenemedi: {e}")
        return
    _update(task_id, worktree=None)


def has_changes(task_id: int) -> bool:
    with session() as s:
        return (
            s.scalar(
                select(TaskStep.id).where(
                    TaskStep.task_id == task_id,
                    TaskStep.status == StepStatus.DONE,
                    TaskStep.commit.is_not(None),
                )
            )
            is not None
        )


async def close(task_id: int) -> None:
    """Close a session without merging (chat deleted, project switched, nothing to keep)."""
    _resolve(task_id, ApprovalStatus.CANCELLED)
    _update(task_id, status=TaskStatus.CANCELLED)
    await cleanup(task_id, merged=False)


async def close_if_empty(chat_id: int) -> bool:
    """True if the chat has no session with changes left (an empty one is closed)."""
    task_id = open_session_id(chat_id)
    if task_id is None:
        return True
    if has_changes(task_id):
        return False
    await close(task_id)
    return True


def recover() -> None:
    """At startup a session can't still be running; put it back up for review."""
    with session() as s:
        ids = s.scalars(
            select(Task.id).where(
                Task.kind == TaskKind.SESSION,
                Task.status.in_([TaskStatus.RUNNING, TaskStatus.QUEUED]),
            )
        ).all()
        for task_id in ids:
            t = s.get(Task, task_id)
            t.status, t.stage = TaskStatus.WAITING_APPROVAL, TaskStage.MERGE
