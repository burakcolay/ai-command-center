"""Claude Code CLI adapter (headless `claude -p`, subscription login only).

Verified against Claude Code 2.1.x stream-json output:
  - system/init carries `apiKeySource`; "none" means the claude.ai subscription is used.
  - rate_limit_event carries real 5-hour / 7-day utilization and overage flags.
  - result carries `structured_output` when --json-schema is given.
  - total_cost_usd is a notional figure on subscriptions and is NOT shown as spend.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from collections.abc import AsyncIterator
from typing import Any

from acc import prefs, security
from acc.adapters.base import (
    AdapterError,
    AdapterEvent,
    AdapterInfo,
    Billing,
    Capabilities,
    Health,
    ModelAdapter,
    ModelState,
    QuotaExceeded,
    RunRequest,
    SessionLost,
    Usage,
    UsageWindow,
)
from acc.cost_guard import CostBlocked, sanitized_env

# authMethod values from `claude auth status --json` that mean subscription login.
# Anything else (API key, helper scripts, unknown values) is blocked by default.
SUBSCRIPTION_AUTH_METHODS = frozenset({"claude.ai", "oauth_token", "oauth"})


class ClaudeCodeAdapter(ModelAdapter):
    info = AdapterInfo(
        id="claude_code",
        name="Claude Code",
        provider="Anthropic",
        billing=Billing.SUBSCRIPTION,
        auth_method="claude.ai aboneliği (claude auth login)",
        requires_membership=True,
        requires_api_key=False,
        notes="Planlama, kodlama, mimari ve inceleme için ana ajan.",
    )
    capabilities = Capabilities(
        chat=True,
        tools=True,
        planning=True,
        coding=True,
        review=True,
        headless=True,
        structured_output=True,
        mcp=True,
        skills=True,
        web_search=True,
    )

    def __init__(self, binary: str = "claude") -> None:
        self.binary = binary
        self._procs: dict[str, asyncio.subprocess.Process] = {}
        self._last_usage: Usage | None = None

    async def _exec(self, *args: str, timeout: float = 20) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            self.binary,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=sanitized_env(),
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            proc.kill()
            raise
        return proc.returncode or 0, out.decode(errors="replace")

    async def health_check(self) -> Health:
        if shutil.which(self.binary) is None:
            return Health(ModelState.NOT_CONFIGURED, "Claude Code CLI bulunamadı (claude).")
        try:
            code, out = await self._exec("auth", "status", "--json")
            status = json.loads(out)
        except (TimeoutError, json.JSONDecodeError, OSError) as e:
            return Health(ModelState.UNKNOWN, f"Kimlik durumu okunamadı: {e}")
        if code != 0 or not status.get("loggedIn"):
            return Health(
                ModelState.AUTH_REQUIRED, "Giriş yapılmamış. Terminalde: claude auth login"
            )
        method = status.get("authMethod")
        provider = status.get("apiProvider")
        if method not in SUBSCRIPTION_AUTH_METHODS or provider != "firstParty":
            return Health(
                ModelState.PAID_ACCESS_REQUIRED,
                f"Abonelik dışı kimlik doğrulama algılandı ({method}/{provider}). "
                "Ücretli API'ye geçmemek için kullanım engellendi.",
            )
        if (resets := self._blocked_until()) is not None:
            return Health(
                ModelState.COOLDOWN,
                str(QuotaExceeded(resets)),
                {"auth": method, "resets_at": resets},
            )
        return Health(ModelState.AVAILABLE, "Abonelik ile giriş yapıldı.", {"auth": method})

    def _blocked_until(self) -> int | None:
        """Reset time of a used-up window that hasn't reset yet, from the last real reading."""
        usage = self._last_usage
        if not usage:
            return None
        now = time.time()
        blocked = [
            w.resets_at
            for w in usage.windows
            if w.status == "rejected" and w.resets_at and w.resets_at > now
        ]
        return min(blocked) if blocked else None

    async def usage_status(self) -> Usage:
        return self._last_usage or Usage(
            source="unknown", detail="Henüz bir çalıştırma yapılmadı; limit bilgisi yok."
        )

    def _args(self, req: RunRequest) -> list[str]:
        args = ["-p", "--output-format", "stream-json", "--verbose"]
        if req.resume:
            args += ["--resume", req.resume]
        elif req.session_id:
            args += ["--session-id", req.session_id]
        else:
            args += ["--no-session-persistence"]
        # Project-level .claude/settings.json inside a repo is untrusted (it can define hooks
        # that run commands). Only the user's own settings plus ours are loaded.
        args += ["--setting-sources", "user"]
        # Secret-file deny rules always apply; agent settings (e.g. sandbox) are added on top.
        args += [
            "--settings",
            json.dumps({**security.claude_base_settings(), **(req.settings or {})}),
        ]
        if req.tools is not None:
            args += ["--tools", ",".join(req.tools)]
            if req.tools:
                args += ["--allowedTools", ",".join(req.tools)]
        if req.permission_mode:
            args += ["--permission-mode", req.permission_mode]
        if req.json_schema:
            args += ["--json-schema", json.dumps(req.json_schema)]
        if req.system_prompt:
            args += ["--append-system-prompt", req.system_prompt]
        model = req.model or prefs.get("claude_model", "default")
        if model and model != "default":
            args += ["--model", model]
        if req.effort:
            args += ["--effort", req.effort]
        for d in [*req.read_dirs, *([req.output_dir] if req.output_dir else [])]:
            args += ["--add-dir", str(d)]
        if req.stream_text:
            args += ["--include-partial-messages"]
        return args

    async def run(self, req: RunRequest, run_id: str) -> AsyncIterator[AdapterEvent]:
        health = await self.health_check()
        if health.state == ModelState.COOLDOWN:
            raise QuotaExceeded(health.data.get("resets_at"))
        if health.state != ModelState.AVAILABLE:
            raise AdapterError(health.detail)

        proc = await asyncio.create_subprocess_exec(
            self.binary,
            *self._args(req),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(req.cwd) if req.cwd else None,
            env=sanitized_env(),
            limit=16 * 1024 * 1024,
        )
        self._procs[run_id] = proc
        assert proc.stdin and proc.stdout and proc.stderr
        proc.stdin.write(req.prompt.encode())
        await proc.stdin.drain()
        proc.stdin.close()

        got_result = False
        try:
            async for raw in proc.stdout:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    if req.resume and b"No conversation found" in raw:
                        raise SessionLost(raw.decode(errors="replace").strip()) from None
                    continue
                for ev in self._translate(msg):
                    if ev.kind in ("result", "error"):
                        got_result = True
                    yield ev
            await proc.wait()
            if not got_result:
                err = (await proc.stderr.read()).decode(errors="replace").strip()
                if proc.returncode in (-15, -9):
                    raise AdapterError("Çalıştırma iptal edildi.")
                raise AdapterError(err[-2000:] or f"Claude Code çıkış kodu {proc.returncode}")
        finally:
            self._procs.pop(run_id, None)
            if proc.returncode is None:
                proc.kill()

    def _translate(self, msg: dict[str, Any]) -> list[AdapterEvent]:
        t = msg.get("type")
        if t == "system" and msg.get("subtype") == "init":
            if msg.get("apiKeySource") not in (None, "none"):
                raise CostBlocked(
                    f"Claude Code API anahtarıyla başladı ({msg.get('apiKeySource')}). "
                    "Ücretli kullanımı önlemek için durduruldu."
                )
            return [AdapterEvent("log", {"text": f"Model: {msg.get('model')}"})]
        if t == "rate_limit_event":
            info = msg.get("rate_limit_info") or {}
            if info.get("isUsingOverage"):
                raise CostBlocked(
                    "Claude ücretli aşım (extra usage) kullanmaya başladı; durduruldu. "
                    "claude.ai ayarlarında ekstra kullanımı kapalı tutun."
                )
            windows = [
                UsageWindow(name, w.get("utilization"), w.get("resetsAt"), w.get("status"))
                for name, w in (info.get("unifiedWindows") or {}).items()
            ]
            self._last_usage = Usage(
                source="verified",
                detail="Claude Code rate_limit_event verisi.",
                windows=windows,
                observed_at=int(time.time()),
            )
            status = info.get("status")
            if status == "rejected":
                raise QuotaExceeded(info.get("resetsAt") or self._blocked_until())
            events = [AdapterEvent("usage", {"windows": [w.__dict__ for w in windows]})]
            if status == "allowed_warning":
                used = max((w.utilization or 0 for w in windows), default=0)
                events.append(
                    AdapterEvent("log", {"text": f"Kota uyarısı: %{round(used * 100)} kullanıldı."})
                )
            return events
        if t == "stream_event":
            ev = msg.get("event") or {}
            delta = ev.get("delta") or {}
            if ev.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                return [AdapterEvent("delta", {"text": delta.get("text", "")})]
            return []
        if t == "assistant":
            out = []
            for block in (msg.get("message") or {}).get("content") or []:
                if block.get("type") == "text" and block.get("text"):
                    out.append(AdapterEvent("text", {"text": block["text"]}))
                elif block.get("type") == "tool_use" and block.get("name") != "StructuredOutput":
                    out.append(
                        AdapterEvent(
                            "tool", {"name": block.get("name"), "input": block.get("input")}
                        )
                    )
            return out
        if t == "result":
            if msg.get("is_error"):
                text = str(msg.get("result") or msg.get("subtype"))
                if "limit" in text.lower() and (resets := self._blocked_until()):
                    raise QuotaExceeded(resets)
                return [AdapterEvent("error", {"text": text})]
            return [
                AdapterEvent(
                    "result",
                    {
                        "text": msg.get("result"),
                        "structured": msg.get("structured_output"),
                        "turns": msg.get("num_turns"),
                        "duration_ms": msg.get("duration_ms"),
                    },
                )
            ]
        return []

    async def cancel(self, run_id: str) -> None:
        proc = self._procs.get(run_id)
        if proc and proc.returncode is None:
            proc.terminate()
