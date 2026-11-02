"""Common contract every model provider implements.

Mapping to the interface in the project document:
  connect() + authenticate()  -> health_check()   (login is always done by the user in the
                                                   provider's own CLI; we never handle passwords)
  get_capabilities()          -> .capabilities
  get_usage_status()          -> usage_status()
  execute_task() + get_result -> run()            (async stream of events, last one is "result")
  cancel_task()               -> cancel()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal


class Billing(StrEnum):
    SUBSCRIPTION = "subscription"  # covered by an existing paid membership (Claude, ChatGPT)
    LOCAL_FREE = "local_free"  # runs on this machine (Ollama, demo)
    FREE_TIER = "free_tier"  # provider's free access, may disappear (Grok Build)
    PAID_API = "paid_api"  # per-token billing -> always blocked by the cost guard


class ModelState(StrEnum):
    AVAILABLE = "available"
    LIMITED = "limited"
    COOLDOWN = "cooldown"
    AUTH_REQUIRED = "auth_required"
    MEMBERSHIP_REQUIRED = "membership_required"
    PAID_ACCESS_REQUIRED = "paid_access_required"
    NOT_CONFIGURED = "not_configured"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


# Where a number came from. The UI must never show an estimate as a measurement.
DataSource = Literal["verified", "estimated", "user", "unknown"]


@dataclass(frozen=True)
class Capabilities:
    chat: bool = False
    tools: bool = False  # can read/edit files, run commands, search the web
    planning: bool = False
    coding: bool = False
    review: bool = False
    headless: bool = False
    structured_output: bool = False
    mcp: bool = False
    skills: bool = False
    web_search: bool = False


@dataclass(frozen=True)
class AdapterInfo:
    id: str
    name: str
    provider: str
    billing: Billing
    auth_method: str
    requires_membership: bool
    requires_api_key: bool
    notes: str = ""


@dataclass
class Health:
    state: ModelState
    detail: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageWindow:
    name: str  # e.g. "five_hour", "seven_day"
    utilization: float | None  # 0..1
    resets_at: int | None  # unix seconds
    status: str | None


@dataclass
class Usage:
    source: DataSource
    detail: str
    windows: list[UsageWindow] = field(default_factory=list)
    observed_at: int | None = None


@dataclass
class RunRequest:
    prompt: str
    cwd: Path | None = None
    system_prompt: str | None = None
    json_schema: dict[str, Any] | None = None
    tools: list[str] | None = None  # None = provider default, [] = no tools
    permission_mode: str | None = None
    model: str | None = None
    settings: dict[str, Any] | None = None  # extra provider settings (e.g. sandbox policy)
    stream_text: bool = False  # emit "delta" events while the answer is being written
    effort: str | None = None  # how hard to think: low | medium | high | xhigh | max
    read_dirs: list[Path] = field(default_factory=list)  # extra folders the model may read
    output_dir: Path | None = None  # where reports and design files go (also readable)
    session_id: str | None = None  # start a resumable conversation with this id
    resume: str | None = None  # continue an earlier conversation


EventKind = Literal["text", "delta", "tool", "log", "usage", "result", "error"]


@dataclass
class AdapterEvent:
    kind: EventKind
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdapterError(Exception):
    """Raised when a run cannot start or must be aborted (auth, cost guard, crash)."""


class SessionLost(AdapterError):
    """A conversation to resume no longer exists (e.g. after cleanup); start a fresh one."""


class QuotaExceeded(AdapterError):
    """The subscription's usage window is used up. Work should wait, never switch to paid."""

    def __init__(self, resets_at: int | None) -> None:
        self.resets_at = resets_at
        when = (
            datetime.fromtimestamp(resets_at).strftime("%d.%m %H:%M") if resets_at else "bilinmiyor"
        )
        super().__init__(f"Claude abonelik kotası doldu (sıfırlanma: {when}).")


class ModelAdapter(ABC):
    info: AdapterInfo
    capabilities: Capabilities

    @abstractmethod
    async def health_check(self) -> Health: ...

    async def usage_status(self) -> Usage:
        return Usage(source="unknown", detail="Bu sağlayıcı kullanım bilgisi sunmuyor.")

    @abstractmethod
    def run(self, req: RunRequest, run_id: str) -> AsyncIterator[AdapterEvent]: ...

    @abstractmethod
    async def cancel(self, run_id: str) -> None: ...
