from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from acc.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class TaskStatus(StrEnum):
    PLANNING = "planning"
    WAITING_APPROVAL = "waiting_approval"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStage(StrEnum):
    PLAN = "plan"  # producing / approving the plan
    EXECUTE = "execute"  # agents working in the task's worktree
    MERGE = "merge"  # diff ready, waiting for the user's merge decision
    DONE = "done"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    REVERTED = "reverted"  # its commit was undone by the user


class TaskKind(StrEnum):
    PLAN = "plan"  # plan → approve → execute → review → merge
    SESSION = "session"  # quick edits: each message is applied right away, then reviewed


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    CANCELLED = "cancelled"


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    path: Mapped[str] = mapped_column(Text)
    # Quality gates: {"setup": str|None, "commands": [{"name", "command"}]}; None = auto-detect
    checks: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Chat(Base):
    __tablename__ = "chats"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="Yeni sohbet")
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    # Rolling summary of older messages, so long chats don't resend everything each turn.
    summary: Mapped[str | None] = mapped_column(Text)
    summary_until: Mapped[int | None] = mapped_column()  # last message id folded into summary
    # The assistant's own conversation id (Claude Code session), resumed on every turn.
    claude_session: Mapped[str | None] = mapped_column(String(64))
    # The model picked under the composer: "auto" or "<provider>/<model id>", and its effort.
    model_choice: Mapped[str | None] = mapped_column(String(120))
    effort_choice: Mapped[str | None] = mapped_column(String(16))
    # Last message Claude's own session has seen; turns by other models after it are replayed.
    claude_seen_until: Mapped[int | None] = mapped_column()
    # Otopilot: how many more turns may start on their own (0 = off). See acc.autopilot.
    autopilot_left: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    request: Mapped[str] = mapped_column(Text)
    # Conversation that led to this task (snapshot), passed to the planner and the agents.
    context: Mapped[str | None] = mapped_column(Text)
    # Attachment ids (images, chosen designs) the agents should look at.
    attachments: Mapped[list[str] | None] = mapped_column(JSON)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.PLANNING)
    kind: Mapped[str] = mapped_column(String(16), default=TaskKind.PLAN, server_default="plan")
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    adapter_id: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(16), default=TaskStage.PLAN, server_default="plan")
    # Execution workspace: an isolated git worktree on its own branch.
    branch: Mapped[str | None] = mapped_column(String(200))
    base_branch: Mapped[str | None] = mapped_column(String(200))
    base_commit: Mapped[str | None] = mapped_column(String(64))
    worktree: Mapped[str | None] = mapped_column(Text)
    merged_commit: Mapped[str | None] = mapped_column(String(64))
    # Pull request opened on GitHub for this branch (the user pressed "PR aç").
    pr_url: Mapped[str | None] = mapped_column(Text)
    # Last preview of the app in the copy (screenshots, browser errors, or why it failed).
    preview: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Results of the last quality-gate run (list of {name, command, status, exit_code, ...}).
    checks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    # Paused for subscription quota: resumes automatically at this time.
    resume_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TaskStep(Base):
    """One unit of execution: a plan step, or a revision requested at review time."""

    __tablename__ = "task_steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column()
    step_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(300))
    agent: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(16), default="plan")  # plan | revision | edit
    status: Mapped[str] = mapped_column(String(16), default=StepStatus.PENDING)
    summary: Mapped[str | None] = mapped_column(Text)
    commit: Mapped[str | None] = mapped_column(String(64))
    adapter_id: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | task
    content: Mapped[str] = mapped_column(Text)
    # assistant replies: streaming -> done | error | cancelled | waiting (for quota reset)
    status: Mapped[str] = mapped_column(String(16), default="done", server_default="done")
    adapter_id: Mapped[str | None] = mapped_column(String(64))  # who wrote an assistant reply
    # e.g. {"kind": "research", "report_path": "..."}
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskEvent(Base):
    """Append-only log of everything that happened in a task (also streamed to the UI)."""

    __tablename__ = "task_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # plan | merge | ...
    status: Mapped[str] = mapped_column(String(32), default=ApprovalStatus.PENDING)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(64))  # user | system | <adapter id>
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(128))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Preference(Base):
    """Small user settings (e.g. which local model to use)."""

    __tablename__ = "preferences"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class Template(Base):
    """A reusable request the user saved (built-in templates live in code)."""

    __tablename__ = "templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(8), default="task")  # chat | task
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
