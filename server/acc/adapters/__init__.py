"""Adapter registry. Adding a provider = one new module + one line here."""

from __future__ import annotations

import time

from acc import config
from acc.adapters.base import Health, ModelAdapter, ModelState
from acc.adapters.claude_code import ClaudeCodeAdapter
from acc.adapters.codex import CodexAdapter
from acc.adapters.mock import MockAdapter
from acc.adapters.ollama import OllamaAdapter
from acc.cost_guard import check_allowed

HEALTH_TTL_S = 60


class Registry:
    def __init__(self, adapters: list[ModelAdapter]) -> None:
        self._adapters = {a.info.id: a for a in adapters}
        self._health: dict[str, tuple[float, Health]] = {}

    def all(self) -> list[ModelAdapter]:
        return list(self._adapters.values())

    def get(self, adapter_id: str) -> ModelAdapter | None:
        return self._adapters.get(adapter_id)

    async def health(self, adapter_id: str, fresh: bool = False) -> Health:
        cached = self._health.get(adapter_id)
        if cached and not fresh and time.monotonic() - cached[0] < HEALTH_TTL_S:
            return cached[1]
        h = await self._adapters[adapter_id].health_check()
        self._health[adapter_id] = (time.monotonic(), h)
        return h

    def invalidate(self, adapter_id: str) -> None:
        self._health.pop(adapter_id, None)

    async def pick(
        self, preferred: list[str], needs_tools: bool = False
    ) -> tuple[ModelAdapter | None, list[str]]:
        """First adapter in preference order that is available and allowed by the cost guard.

        Returns the adapter (or None) plus a human-readable reason for every skipped one.
        """
        skipped: list[str] = []
        for adapter_id in preferred:
            adapter = self._adapters.get(adapter_id)
            if adapter is None:
                continue
            if needs_tools and not adapter.capabilities.tools:
                skipped.append(f"{adapter.info.name}: dosya/araç desteği yok")
                continue
            try:
                check_allowed(adapter.info)
            except Exception as e:
                skipped.append(str(e))
                continue
            h = await self.health(adapter_id)
            if h.state == ModelState.AVAILABLE:
                return adapter, skipped
            skipped.append(f"{adapter.info.name}: {h.detail}")
        return None, skipped


def build_registry() -> Registry:
    adapters: list[ModelAdapter] = [ClaudeCodeAdapter(), CodexAdapter(), OllamaAdapter()]
    if config.DEMO_MODE:
        adapters.append(MockAdapter())
    return Registry(adapters)


registry = build_registry()
