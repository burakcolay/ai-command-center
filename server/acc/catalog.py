"""Every model the user can pick under the composer, with the efforts each one takes.

Lists come from the providers themselves where they can tell:
  - Codex: `codex debug models` (offline catalog; per-model reasoning levels, codex-cli 0.166)
  - Gemini / Antigravity: `agy models` (the signed-in account's models, agy 1.4.12)
  - Local: the models Ollama has installed
  - Claude: Claude Code has no list command; the current family is listed here, and a model
    the subscription lacks falls back to the default (404 handling in the adapter).
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
from typing import Any

from acc.adapters import Registry
from acc.adapters.base import ModelState
from acc.cost_guard import sanitized_env

CLAUDE_EFFORTS = ["low", "medium", "high", "xhigh", "max"]
AGY_EFFORTS = ["low", "medium", "high", "xhigh", "max"]  # agy --help (1.4.12)
CLAUDE_MODELS = [
    {"id": "claude-opus-5-5", "label": "Opus 5.5", "effort": "high", "note": "En güçlü"},
    {"id": "claude-sonnet-5-5", "label": "Sonnet 5.5", "effort": "medium", "note": "Dengeli"},
    {"id": "claude-haiku-5-5", "label": "Haiku 5.5", "effort": "low", "note": "En hızlı"},
    {"id": "claude-fable-5-1", "label": "Fable 5.1", "effort": "high", "note": "En yeni"},
]
CACHE_S = 600
PROVIDERS = ("claude_code", "codex", "gemini", "ollama")
NOTES = {
    "claude_code": "Her şeyi yapar; ekibi ve Codex köprüsünü yönetir.",
    "codex": "Dosya değiştirir ve komut çalıştırır; Claude'un ekibi olmadan çalışır.",
    "gemini": "Sohbet ve araştırma; dosya değiştiremez.",
    "ollama": "Ücretsiz, bilgisayarında; dosya ve web erişimi yok.",
}
_PICK = re.compile(
    r"^(auto|haiku|sonnet|opus|(claude_code|codex|gemini|ollama|mock)/[\w.:\-]{1,80})$"
)
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def valid(pick: str) -> bool:
    return bool(_PICK.match(pick))


def split(pick: str | None) -> tuple[str | None, str | None]:
    """ "codex/gpt-6.1-sol" → ("codex", "gpt-6.1-sol"); "auto" or legacy → Claude aliases."""
    if not pick or pick == "auto":
        return None, None
    if pick in ("haiku", "sonnet", "opus"):  # picks saved before providers were listed
        return "claude_code", pick
    provider, _, model = pick.partition("/")
    return provider, model or None


async def _cli(binary: str, *args: str, timeout: float = 20) -> str | None:
    if shutil.which(binary) is None:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=sanitized_env(),
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except (OSError, TimeoutError):
        return None
    return out.decode(errors="replace") if proc.returncode == 0 else None


def parse_codex(text: str) -> list[dict[str, Any]]:
    try:
        models = json.loads(text).get("models") or []
    except (json.JSONDecodeError, AttributeError):
        return []
    out = []
    for m in sorted(models, key=lambda m: m.get("priority") or 99):
        if m.get("visibility") != "list" or not m.get("slug"):
            continue
        efforts = [lv.get("effort") for lv in m.get("supported_reasoning_levels") or []]
        out.append(
            {
                "id": m["slug"],
                "label": m.get("display_name") or m["slug"],
                "efforts": [e for e in efforts if e],
                "effort": m.get("default_reasoning_level") or "medium",
                "note": m.get("description") or "",
            }
        )
    return out


def parse_agy(text: str) -> list[dict[str, Any]]:
    out = []
    for line in text.splitlines():
        if m := re.match(r"^\s*(\S+)\s{2,}(.+?)\s*$", line):
            out.append(
                {"id": m[1], "label": m[2], "efforts": AGY_EFFORTS, "effort": "medium", "note": ""}
            )
    return out


async def _cached(key: str, load) -> list[dict[str, Any]]:
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_S:
        return hit[1]
    models = await load()
    if models:
        _cache[key] = (time.monotonic(), models)
    return models


async def _models(provider: str, adapter, health) -> list[dict[str, Any]]:
    if provider in ("claude_code", "mock"):
        return [{**m, "efforts": CLAUDE_EFFORTS} for m in CLAUDE_MODELS]
    if provider == "codex":

        async def load():
            return parse_codex(await _cli(adapter.binary, "debug", "models") or "")

        return await _cached("codex", load)
    if provider == "gemini":

        async def load():
            return parse_agy(await _cli(adapter.binary, "models") or "")

        return await _cached("gemini", load)
    if provider == "ollama":
        installed = (health.data or {}).get("models") or []
        return [
            {"id": m["name"], "label": m["name"], "efforts": [], "effort": "", "note": ""}
            for m in installed
            if m.get("name")
        ]
    return []


async def catalog(registry: Registry) -> list[dict[str, Any]]:
    """Providers with their models; unavailable ones say why (shown greyed out)."""
    out = []
    for adapter in registry.all():
        provider = adapter.info.id
        if provider not in (*PROVIDERS, "mock"):
            continue
        health = await registry.health(provider)
        out.append(
            {
                "id": provider,
                "name": adapter.info.name,
                "available": health.state == ModelState.AVAILABLE,
                "reason": "" if health.state == ModelState.AVAILABLE else health.detail,
                "note": NOTES.get(provider, ""),
                "models": await _models(provider, adapter, health),
            }
        )
    return out


def default_effort(provider: str, model: str | None) -> str | None:
    """The effort a picked model runs at when the user didn't choose one."""
    if provider in ("claude_code", "mock"):
        known = {m["id"]: m["effort"] for m in CLAUDE_MODELS}
        return known.get(model or "", {"haiku": "low", "sonnet": "medium"}.get(model or "", "high"))
    if provider == "codex":
        cached = _cache.get("codex")
        found = next((m for m in (cached[1] if cached else []) if m["id"] == model), None)
        return found["effort"] if found else "medium"
    if provider == "gemini":
        return "medium"
    return None
