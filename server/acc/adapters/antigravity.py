"""Gemini through Google's Antigravity CLI (`agy`), signed in with the user's Google account.

Gemini CLI no longer accepts personal Google logins (June 2026); Antigravity CLI is the way an
AI Plus/Pro subscription is used from a terminal. Checked on the user's Mac with agy 1.4.12:
`agy -p "…" --output-format json < /dev/null > file` (no terminal, like Orbit runs it) exits 0
and prints one JSON object: {conversation_id, status: "SUCCESS", response, duration_seconds,
num_turns, usage}. Flags used here are from its `--help`. With --json-schema and a model
that wanted to run a command, it ended SUCCESS with an empty response and
`denied_actions: [{action: "command"}]` — hence the up-front rule and the one retry.

Role: independent reviewer and summariser, never the author. Headless agy can't answer
permission prompts, so it can't edit files or run commands on its own anyway; it also runs
with `--sandbox`. Google API-key / Vertex variables are stripped (`env.BILLING_ENV_VARS`), so
only the signed-in account can be used.
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
    model_usage,
)
from acc.cost_guard import sanitized_env

TIMEOUT_S = 600
# Headless agy auto-denies anything that needs a permission (e.g. running a command) and then
# ends with an empty response. Said up front, and if it still tries, asked once more.
NO_COMMANDS = (
    "ÖNEMLİ: Bu ortamda terminal komutu çalıştıramazsın, istersen reddedilir ve cevabın boş "
    "kalır. Kodu çalıştırmaya çalışma; gerekiyorsa yalnızca dosya okuma aracını kullan, "
    "değerlendirmeni okuyarak yap."
)
RETRY = (
    "Önceki denemede izin gerektiren bir araç (ör. komut çalıştırma) kullanmak istedin ve "
    "reddedildi. Hiçbir araç kullanmadan, yalnızca aşağıdaki metne bakarak cevap ver."
)
FALLBACK_COOLDOWN_S = 30 * 60
_QUOTA = ("quota", "rate limit", "resource exhausted", "resource_exhausted", "usage limit")
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _structured(data: dict[str, Any]) -> Any:
    """Schema-shaped answer: a dedicated field if agy gives one, else the response as JSON."""
    for key in ("structured_output", "structured", "output", "result"):
        if isinstance(data.get(key), dict):
            return data[key]
    text = _FENCE.sub("", str(data.get("response") or "").strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


class AntigravityAdapter(ModelAdapter):
    info = AdapterInfo(
        id="gemini",
        name="Gemini",
        provider="Google (Antigravity CLI)",
        billing=Billing.SUBSCRIPTION,
        auth_method="Google hesabı (agy ile giriş)",
        requires_membership=False,
        requires_api_key=False,
        notes="Değişiklikleri bağımsız inceler ve uzun sohbetleri özetler; kod yazmaz.",
    )
    capabilities = Capabilities(
        chat=True,
        tools=True,
        review=True,
        headless=True,
        structured_output=True,
        web_search=True,
    )

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or os.environ.get("ACC_AGY") or "agy"
        self._procs: dict[str, asyncio.subprocess.Process] = {}
        self._cooldown_until: int | None = None

    async def _exec(self, args: list[str], cwd: Path, timeout: float) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            self.binary,
            *args,
            cwd=str(cwd),
            stdin=asyncio.subprocess.DEVNULL,  # never wait for a sign-in or a permission prompt
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
                "Antigravity CLI kurulu değil: brew install --cask antigravity-cli, sonra agy",
            )
        if self._cooldown_until and self._cooldown_until > time.time():
            return Health(
                ModelState.COOLDOWN,
                str(QuotaExceeded(self._cooldown_until)),
                {"resets_at": self._cooldown_until},
            )
        try:
            code, out = await self._exec(["models"], Path(tempfile.gettempdir()), 20)
        except (TimeoutError, OSError) as e:
            return Health(ModelState.UNKNOWN, f"agy yanıt vermedi: {e}")
        if code != 0:
            return Health(
                ModelState.AUTH_REQUIRED,
                "Google hesabıyla giriş gerekli. Terminalde bir kez: agy " + out.strip()[-200:],
            )
        return Health(ModelState.AVAILABLE, "Google hesabıyla giriş yapıldı.")

    async def usage_status(self) -> Usage:
        return Usage(
            source="unknown",
            detail="Antigravity kalan kotayı bildirmiyor; dolduğunda Orbit bekler.",
        )

    def _args(self, req: RunRequest, retry: bool = False) -> list[str]:
        prompt = req.prompt
        if req.system_prompt:  # no "system prompt" flag: instructions lead the message
            prompt = f"TALİMATLAR:\n{req.system_prompt}\n\n{NO_COMMANDS}\n\n---\n\n{prompt}"
        else:
            prompt = f"{NO_COMMANDS}\n\n---\n\n{prompt}"
        if req.json_schema:
            prompt += "\n\nCevabını yalnızca istenen JSON olarak ver."
        if retry:
            prompt = f"{RETRY}\n\n{prompt}"
        args = [
            "--print",
            prompt,
            "--output-format",
            "json",
            "--print-timeout",
            f"{TIMEOUT_S}s",
            "--sandbox",
        ]
        if req.model:
            args += ["--model", req.model]
        if req.effort:
            args += ["--effort", req.effort]
        if req.json_schema:
            args += ["--json-schema", json.dumps(req.json_schema)]
        for d in req.read_dirs:
            args += ["--add-dir", str(d)]
        return args

    async def run(self, req: RunRequest, run_id: str) -> AsyncIterator[AdapterEvent]:
        health = await self.health_check()
        if health.state == ModelState.COOLDOWN:
            raise QuotaExceeded(health.data.get("resets_at"))
        if health.state != ModelState.AVAILABLE:
            raise AdapterError(health.detail)

        data = await self._once(req, run_id, retry=False)
        if not data.get("response") and data.get("denied_actions"):
            data = await self._once(req, run_id, retry=True)
        if data.get("status") != "SUCCESS":
            detail = str(data.get("error") or data.get("message") or data.get("status"))
            self._check_quota(detail)
            yield AdapterEvent("error", {"text": f"Gemini: {detail}"})
            return
        response = str(data.get("response") or "")
        structured = _structured(data) if req.json_schema else None
        if not response and structured is None:
            denied = (
                ", ".join(
                    str(a.get("display_name") or a.get("action")) for a in data["denied_actions"]
                )
                if data.get("denied_actions")
                else ""
            )
            why = f" (izin gerektiren araç istedi: {denied})" if denied else ""
            yield AdapterEvent("error", {"text": f"Gemini cevap üretmedi{why}."})
            return
        if req.stream_text and response:
            yield AdapterEvent("delta", {"text": response})
        used = model_usage(req.model or str(data.get("model") or "Gemini"), data.get("usage"))
        yield AdapterEvent(
            "result", {"text": response, "structured": structured, "model_usage": used}
        )

    async def _once(self, req: RunRequest, run_id: str, retry: bool) -> dict[str, Any]:
        # Summaries have no project: give agy an empty folder rather than the home directory.
        with tempfile.TemporaryDirectory(prefix="orbit-agy-") as tmp:
            cwd = req.cwd or Path(tmp)
            proc = await asyncio.create_subprocess_exec(
                self.binary,
                *self._args(req, retry),
                cwd=str(cwd),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=sanitized_env(),
            )
            self._procs[run_id] = proc
            try:
                out, err = await asyncio.wait_for(proc.communicate(), TIMEOUT_S + 30)
            except TimeoutError:
                proc.kill()
                raise AdapterError("Gemini zaman aşımına uğradı.") from None
            finally:
                self._procs.pop(run_id, None)
        if proc.returncode in (-15, -9):
            raise AdapterError("Çalıştırma iptal edildi.")
        text = out.decode(errors="replace").strip()
        for line in reversed(text.splitlines()):  # the JSON object is the last line
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
        detail = (err.decode(errors="replace") or text).strip()[-1500:]
        self._check_quota(detail)
        raise AdapterError(detail or f"agy çıkış kodu {proc.returncode}")

    def _check_quota(self, detail: str) -> None:
        if any(word in detail.lower() for word in _QUOTA):
            self._cooldown_until = int(time.time()) + FALLBACK_COOLDOWN_S
            raise QuotaExceeded(self._cooldown_until)

    async def cancel(self, run_id: str) -> None:
        proc = self._procs.get(run_id)
        if proc and proc.returncode is None:
            proc.terminate()
