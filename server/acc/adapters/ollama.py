"""Ollama adapter: local models over the Ollama HTTP API (default http://127.0.0.1:11434).

Local models get no tools here (no file access, no shell, no web). Orbit uses them for
conversation and summarising, never for agent steps that touch a project.
API used: GET /api/tags, GET /api/ps, POST /api/chat (NDJSON stream).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from acc import config, prefs
from acc.adapters.base import (
    AdapterError,
    AdapterEvent,
    AdapterInfo,
    Billing,
    Capabilities,
    Health,
    ModelAdapter,
    ModelState,
    RunRequest,
    Usage,
    model_usage,
)

KEEP_ALIVE = "2m"  # unload soon after use: RAM is shared with everything else on a 16 GB Mac
GB = 1024**3


class OllamaAdapter(ModelAdapter):
    info = AdapterInfo(
        id="ollama",
        name="Ollama",
        provider="Yerel",
        billing=Billing.LOCAL_FREE,
        auth_method="yok · localhost:11434",
        requires_membership=False,
        requires_api_key=False,
        notes="Bilgisayarında çalışan modeller. Sohbet ve özetleme için; dosya araçları yok.",
    )
    capabilities = Capabilities(chat=True, headless=True, structured_output=True)

    def __init__(
        self, base_url: str | None = None, transport: httpx.AsyncBaseTransport | None = None
    ):
        url = base_url or config.OLLAMA_HOST
        self.base_url = url if "://" in url else f"http://{url}"
        self._transport = transport
        self._cancelled: set[str] = set()

    def _client(self, timeout: float | None = 5.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, transport=self._transport, timeout=timeout)

    async def models(self) -> list[dict[str, Any]]:
        async with self._client() as c:
            r = await c.get("/api/tags")
            r.raise_for_status()
            return r.json().get("models") or []

    async def loaded(self) -> list[dict[str, Any]]:
        async with self._client() as c:
            r = await c.get("/api/ps")
            r.raise_for_status()
            return r.json().get("models") or []

    @staticmethod
    def _choose(names: list[str]) -> str:
        chosen = prefs.get("ollama_model")
        return chosen if chosen in names else names[0]

    async def health_check(self) -> Health:
        try:
            models = await self.models()
        except (httpx.HTTPError, ValueError):
            return Health(
                ModelState.OFFLINE,
                "Ollama çalışmıyor. Kurulum: brew install ollama · başlatma: ollama serve",
            )
        if not models:
            return Health(
                ModelState.NOT_CONFIGURED,
                "Hiç model yok. 16 GB RAM için örnek: ollama pull qwen2.5:7b",
            )
        names = [m["name"] for m in models]
        chosen = self._choose(names)
        listing = [
            {
                "name": m["name"],
                "size_gb": round(m.get("size", 0) / GB, 1),
                "params": (m.get("details") or {}).get("parameter_size"),
                "quant": (m.get("details") or {}).get("quantization_level"),
            }
            for m in models
        ]
        return Health(
            ModelState.AVAILABLE, f"Model: {chosen}", {"models": listing, "selected": chosen}
        )

    async def usage_status(self) -> Usage:
        try:
            loaded = await self.loaded()
        except (httpx.HTTPError, ValueError):
            return Usage(source="unknown", detail="Ollama'ya ulaşılamadı.")
        if not loaded:
            return Usage(source="verified", detail="Şu an RAM'de yüklü model yok.")
        parts = [f"{m['name']} ({m.get('size', 0) / GB:.1f} GB)" for m in loaded]
        return Usage(source="verified", detail="RAM'de yüklü: " + ", ".join(parts))

    async def run(self, req: RunRequest, run_id: str) -> AsyncIterator[AdapterEvent]:
        if req.tools:
            raise AdapterError("Yerel model dosya ve web araçlarını kullanamaz.")
        health = await self.health_check()
        if health.state != ModelState.AVAILABLE:
            raise AdapterError(health.detail)
        model = req.model or health.data["selected"]  # the user's pick, else the default
        messages = []
        if req.system_prompt:
            messages.append({"role": "system", "content": req.system_prompt})
        messages.append({"role": "user", "content": req.prompt})
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": KEEP_ALIVE,
        }
        if req.json_schema:
            body["format"] = req.json_schema
        yield AdapterEvent("log", {"text": f"Model: {model} (yerel)"})

        buf: list[str] = []
        counts: dict[str, Any] = {}
        try:
            async with (
                self._client(timeout=None) as c,
                c.stream("POST", "/api/chat", json=body) as r,
            ):
                if r.status_code != 200:
                    detail = (await r.aread()).decode(errors="replace")[:500]
                    raise AdapterError(f"Ollama hatası ({r.status_code}): {detail}")
                async for line in r.aiter_lines():
                    if run_id in self._cancelled:
                        raise AdapterError("Çalıştırma iptal edildi.")
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    if d.get("error"):
                        raise AdapterError(f"Ollama: {d['error']}")
                    piece = (d.get("message") or {}).get("content") or ""
                    if piece:
                        buf.append(piece)
                        if req.stream_text:
                            yield AdapterEvent("delta", {"text": piece})
                    if d.get("done"):
                        counts = d  # prompt_eval_count / eval_count come on the last line
                        break
        except httpx.HTTPError as e:
            raise AdapterError(f"Ollama bağlantı hatası: {e}") from e
        finally:
            self._cancelled.discard(run_id)

        text = "".join(buf)
        structured = None
        if req.json_schema:
            try:
                structured = json.loads(text)
            except json.JSONDecodeError:
                raise AdapterError("Yerel model geçerli JSON döndürmedi.") from None
        used = model_usage(model, counts, cached_in_input=False)
        yield AdapterEvent(
            "result", {"text": text, "structured": structured, "model": model, "model_usage": used}
        )

    async def cancel(self, run_id: str) -> None:
        self._cancelled.add(run_id)
