"""OpenAI Codex CLI adapter (headless `codex exec --json`, ChatGPT subscription login only).

Checked against codex-cli 0.166: the flags used here, `codex login status`, and the JSONL
envelope (thread.started, turn.started, item.*, error, turn.completed / turn.failed). A real
ChatGPT-backed run could not be made from the build machine, so item contents follow the
documented format and are covered by tests with a fake CLI; the first real run on the user's
Mac is the final check.

Cost safety: API-key variables never reach the CLI, `forced_login_method="chatgpt"` is set on
every run, and an API-key login is reported as blocked instead of used.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
import time
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any

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
    Usage,
)
from acc.cost_guard import sanitized_env

WRITE_TOOLS = {"Write", "Edit", "Bash"}
# Reasoning levels every listed model takes (codex debug models, 0.166).
EFFORTS = {"low", "medium", "high", "xhigh", "max", "ultra"}  # "ultra" only on some models
_NO_MODEL = (
    "not supported",
    "not available",
    "does not exist",
    "not found",
    "no access",
    "unsupported",
)


def _model_unavailable(message: str) -> bool:
    text = message.lower()
    return "model" in text and any(w in text for w in _NO_MODEL)


FALLBACK_COOLDOWN_S = 30 * 60
_RETRY_IN = re.compile(r"try again in\s+(?:(\d+)\s*hours?)?\s*(?:(\d+)\s*min)?", re.I)


def _reset_time(message: str) -> int | None:
    m = _RETRY_IN.search(message)
    if not m or not (m[1] or m[2]):
        return None
    return int(time.time()) + int(m[1] or 0) * 3600 + int(m[2] or 0) * 60


def _is_quota(message: str) -> bool:
    text = message.lower()
    return "usage limit" in text or ("rate limit" in text and "reached" in text)


class CodexAdapter(ModelAdapter):
    info = AdapterInfo(
        id="codex",
        name="Codex",
        provider="OpenAI (ChatGPT aboneliği)",
        billing=Billing.SUBSCRIPTION,
        auth_method="ChatGPT hesabı (codex login)",
        requires_membership=True,
        requires_api_key=False,
        notes="Claude'un değişikliklerini bağımsız inceler; Claude'un kotası dolunca işi devralır.",
    )
    capabilities = Capabilities(
        chat=True,
        tools=True,
        planning=True,
        coding=True,
        review=True,
        headless=True,
        structured_output=True,
        web_search=True,
    )

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or os.environ.get("ACC_CODEX") or "codex"
        self._procs: dict[str, asyncio.subprocess.Process] = {}
        self._cooldown_until: int | None = None

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
            return Health(
                ModelState.NOT_CONFIGURED,
                "Codex CLI kurulu değil. Kurulum: npm install -g @openai/codex, sonra codex login",
            )
        try:
            code, out = await self._exec("login", "status")
        except (TimeoutError, OSError) as e:
            return Health(ModelState.UNKNOWN, f"Giriş durumu okunamadı: {e}")
        if "api key" in out.lower():
            return Health(
                ModelState.PAID_ACCESS_REQUIRED,
                "Codex API anahtarıyla giriş yapmış; ücretli kullanımı önlemek için kapalı. "
                "Terminalde: codex logout, sonra codex login (ChatGPT hesabıyla).",
            )
        if code != 0 or "chatgpt" not in out.lower():
            return Health(
                ModelState.AUTH_REQUIRED, "Giriş yapılmamış. Terminalde: codex login (ChatGPT)"
            )
        if self._cooldown_until and self._cooldown_until > time.time():
            return Health(
                ModelState.COOLDOWN,
                str(QuotaExceeded(self._cooldown_until)),
                {"resets_at": self._cooldown_until},
            )
        return Health(ModelState.AVAILABLE, "ChatGPT aboneliği ile giriş yapıldı.")

    async def usage_status(self) -> Usage:
        return Usage(
            source="unknown",
            detail="Codex kalan kotayı komut satırına bildirmiyor; dolduğunda Orbit bekler.",
        )

    def _args(self, req: RunRequest, schema_file: Path | None) -> list[str]:
        tools = set(req.tools or [])
        writable = bool(tools & WRITE_TOOLS)
        args = [
            "exec",
            "--json",
            "--color",
            "never",
            "--skip-git-repo-check",
            "--ephemeral",
            "-c",
            'forced_login_method="chatgpt"',
            "-c",
            'approval_policy="never"',
            "-s",
            "workspace-write" if writable else "read-only",
        ]
        if req.cwd:
            args += ["-C", str(req.cwd)]
        if writable and req.output_dir:
            args += ["--add-dir", str(req.output_dir)]
        if "WebSearch" in tools:
            args += ["-c", 'web_search="live"']
        if req.model:
            args += ["-m", req.model]
        if req.effort:
            effort = req.effort if req.effort in EFFORTS else "medium"
            args += ["-c", f'model_reasoning_effort="{effort}"']
        if schema_file:
            args += ["--output-schema", str(schema_file)]
        return [*args, "-"]  # the prompt comes on stdin

    @staticmethod
    def _prompt(req: RunRequest) -> str:
        # Codex has no "append system prompt" flag; instructions lead the message instead.
        if not req.system_prompt:
            return req.prompt
        return f"TALİMATLAR:\n{req.system_prompt}\n\n---\n\n{req.prompt}"

    async def run(self, req: RunRequest, run_id: str) -> AsyncIterator[AdapterEvent]:
        health = await self.health_check()
        if health.state == ModelState.COOLDOWN:
            raise QuotaExceeded(health.data.get("resets_at"))
        if health.state != ModelState.AVAILABLE:
            raise AdapterError(health.detail)

        # A model the ChatGPT plan doesn't include fails at once: retry on the plan's default.
        worked = False
        async for ev in self._run_once(req, run_id):
            unavailable = ev.kind == "error" and _model_unavailable(str(ev.data.get("text")))
            if unavailable and req.model and not worked:
                break
            worked = worked or ev.kind in ("tool", "delta")
            yield ev
        else:
            return
        yield AdapterEvent("log", {"text": f"{req.model} bu planda yok; varsayılan modelle devam."})
        async for ev in self._run_once(replace(req, model=None), run_id):
            yield ev

    async def _run_once(self, req: RunRequest, run_id: str) -> AsyncIterator[AdapterEvent]:
        with tempfile.TemporaryDirectory(prefix="orbit-codex-") as tmp:
            schema_file = None
            if req.json_schema:
                schema_file = Path(tmp) / "schema.json"
                schema_file.write_text(json.dumps(req.json_schema))
            proc = await asyncio.create_subprocess_exec(
                self.binary,
                *self._args(req, schema_file),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(req.cwd) if req.cwd else None,
                env=sanitized_env(),
                limit=16 * 1024 * 1024,
            )
            self._procs[run_id] = proc
            assert proc.stdin and proc.stdout and proc.stderr
            proc.stdin.write(self._prompt(req).encode())
            await proc.stdin.drain()
            proc.stdin.close()
            seen: set[str] = set()
            last_message = ""
            finished = False
            try:
                async for raw in proc.stdout:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    kind = msg.get("type")
                    if kind in ("item.started", "item.completed"):
                        item = msg.get("item") or {}
                        if item.get("type") == "agent_message":
                            if kind == "item.completed" and item.get("text"):
                                last_message = item["text"]
                                if req.stream_text:
                                    yield AdapterEvent("delta", {"text": item["text"] + "\n\n"})
                            continue
                        if item.get("id") in seen:
                            continue
                        seen.add(item.get("id"))
                        if ev := self._tool_event(item):
                            yield ev
                    elif kind == "error":
                        text = str(msg.get("message") or "")
                        if _is_quota(text):
                            self._quota(text)
                        yield AdapterEvent("log", {"text": text})
                    elif kind == "turn.failed":
                        text = str((msg.get("error") or {}).get("message") or "Codex başarısız")
                        if _is_quota(text):
                            self._quota(text)
                        finished = True
                        yield AdapterEvent("error", {"text": text})
                    elif kind == "turn.completed":
                        finished = True
                        structured = None
                        if req.json_schema:
                            try:
                                structured = json.loads(last_message)
                            except json.JSONDecodeError:
                                structured = None
                        yield AdapterEvent(
                            "result", {"text": last_message, "structured": structured}
                        )
                await proc.wait()
                if not finished:
                    err = (await proc.stderr.read()).decode(errors="replace").strip()
                    if proc.returncode in (-15, -9):
                        raise AdapterError("Çalıştırma iptal edildi.")
                    raise AdapterError(err[-2000:] or f"Codex çıkış kodu {proc.returncode}")
            finally:
                self._procs.pop(run_id, None)
                if proc.returncode is None:
                    proc.kill()

    def _quota(self, message: str) -> None:
        self._cooldown_until = _reset_time(message) or int(time.time()) + FALLBACK_COOLDOWN_S
        raise QuotaExceeded(self._cooldown_until)

    @staticmethod
    def _tool_event(item: dict[str, Any]) -> AdapterEvent | None:
        t = item.get("type")
        if t == "command_execution":
            return AdapterEvent("tool", {"name": "Bash", "input": {"command": item.get("command")}})
        if t == "file_change":
            paths = [c.get("path") for c in item.get("changes") or [] if c.get("path")]
            return AdapterEvent("tool", {"name": "Edit", "input": {"file_path": ", ".join(paths)}})
        if t == "web_search":
            return AdapterEvent(
                "tool", {"name": "WebSearch", "input": {"query": item.get("query")}}
            )
        if t == "mcp_tool_call":
            return AdapterEvent("tool", {"name": str(item.get("tool") or "MCP"), "input": {}})
        if t == "error":
            return AdapterEvent("log", {"text": str(item.get("message") or "")})
        return None

    async def cancel(self, run_id: str) -> None:
        proc = self._procs.get(run_id)
        if proc and proc.returncode is None:
            proc.terminate()
