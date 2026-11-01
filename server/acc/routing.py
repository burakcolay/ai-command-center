"""Which model does which kind of work.

Each kind of work has a default preference order and the capabilities it needs. The router
skips models that can't do the work, aren't healthy, are blocked by the cost guard or (when
an alternative exists) are close to their subscription limit. The user can pin a model per
kind. Adapters that aren't installed yet (e.g. Codex) are already in the orders: the day one
is added, it starts taking the work it's listed for — no other change needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acc import prefs
from acc.adapters import Registry
from acc.adapters.base import ModelAdapter, ModelState
from acc.cost_guard import check_allowed

QUOTA_SOFT_LIMIT = 0.9  # above this share of a usage window, prefer an alternative


@dataclass(frozen=True)
class WorkKind:
    id: str
    label: str
    description: str
    order: list[str]
    needs: tuple[str, ...]  # capability flags that must be true


WORK_KINDS: dict[str, WorkKind] = {
    k.id: k
    for k in [
        WorkKind(
            "plan",
            "Planlama",
            "İsteği adımlara böler ve ajanlara dağıtır.",
            ["claude_code", "codex", "mock"],
            ("planning", "structured_output"),
        ),
        WorkKind(
            "chat",
            "Sohbet",
            "Fikirleri netleştirir, proje hakkında konuşur.",
            ["claude_code", "codex", "ollama", "mock"],
            ("chat",),
        ),
        WorkKind(
            "research",
            "Araştırma",
            "Web'de kaynak tarar, rapor yazar.",
            ["claude_code", "codex", "mock"],
            ("tools", "web_search"),
        ),
        WorkKind(
            "design",
            "Tasarım",
            "Ekran alternatifleri çizer.",
            ["claude_code", "codex", "mock"],
            ("structured_output",),
        ),
        WorkKind(
            "code",
            "Kod yazma",
            "Geliştirici ve dokümantasyon adımları; dosya değiştirir.",
            ["claude_code", "codex", "mock"],
            ("tools", "coding"),
        ),
        WorkKind(
            "review",
            "İnceleme ve test",
            "Kodu yazan modelden farklı bir model tercih edilir: ikinci göz.",
            ["codex", "claude_code", "mock"],
            ("tools", "review"),
        ),
        WorkKind(
            "summarize",
            "Özetleme",
            "Uzun sohbetleri özetler; ücretsiz yerel model önce.",
            ["ollama", "claude_code", "mock"],
            ("chat",),
        ),
    ]
}

# Which kind of work each agent does.
AGENT_WORK = {
    "orchestrator": "plan",
    "architect": "plan",
    "assistant": "chat",
    "research": "research",
    "developer": "code",
    "docs": "code",
    "qa": "review",
    "reviewer": "review",
}


@dataclass
class Choice:
    adapter: ModelAdapter | None
    reason: str = ""
    skipped: list[str] = field(default_factory=list)


def overrides() -> dict[str, str]:
    value = prefs.get("routing", {})
    return value if isinstance(value, dict) else {}


async def _utilization(adapter: ModelAdapter) -> float | None:
    usage = await adapter.usage_status()
    if usage.source != "verified" or not usage.windows:
        return None
    values = [w.utilization for w in usage.windows if w.utilization is not None]
    return max(values) if values else None


class Router:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry

    def order(self, kind: str) -> list[str]:
        base = WORK_KINDS[kind].order
        pinned = overrides().get(kind)
        if pinned and pinned != "auto":
            return [pinned, *[a for a in base if a != pinned]]
        return base

    def eligible(self, kind: str, adapter: ModelAdapter, needs_tools: bool) -> str | None:
        """None if the adapter can do this kind of work, else why not."""
        caps = adapter.capabilities
        missing = [n for n in WORK_KINDS[kind].needs if not getattr(caps, n, False)]
        if needs_tools and not caps.tools:
            missing.append("tools")
        return f"gereken yetenek yok ({', '.join(missing)})" if missing else None

    async def pick(
        self, kind: str, needs_tools: bool = False, avoid: set[str] | None = None
    ) -> Choice:
        avoid = avoid or set()
        skipped: list[str] = []
        usable: list[tuple[ModelAdapter, float | None]] = []
        for adapter_id in self.order(kind):
            adapter = self.registry.get(adapter_id)
            if adapter is None:
                continue  # not installed (yet)
            if why := self.eligible(kind, adapter, needs_tools):
                skipped.append(f"{adapter.info.name}: {why}")
                continue
            try:
                check_allowed(adapter.info)
            except Exception as e:
                skipped.append(str(e))
                continue
            health = await self.registry.health(adapter_id)
            if health.state != ModelState.AVAILABLE:
                skipped.append(f"{adapter.info.name}: {health.detail}")
                continue
            usable.append((adapter, await _utilization(adapter)))
        if not usable:
            return Choice(None, "", skipped)

        pinned = overrides().get(kind, "auto") not in ("auto", None)
        first, first_use = usable[0]
        if pinned and first.info.id == overrides()[kind]:
            return Choice(first, "elle seçildi", skipped)
        # Second opinion: prefer a model that didn't write the code being reviewed.
        if avoid:
            fresh = [(a, u) for a, u in usable if a.info.id not in avoid]
            if fresh and fresh[0][0] is not first:
                return Choice(fresh[0][0], "ikinci görüş: kodu yazan modelden farklı", skipped)
        # Quota: move off a nearly used-up subscription when there is somewhere to go.
        if first_use is not None and first_use >= QUOTA_SOFT_LIMIT:
            for alt, use in usable:
                if alt is not first and (use is None or use < QUOTA_SOFT_LIMIT):
                    reason = f"{first.info.name} kotası %{round(first_use * 100)}; yük aktarıldı"
                    return Choice(alt, reason, skipped)
        return Choice(first, "varsayılan sıra", skipped)

    async def describe(self) -> list[dict]:
        """For the UI: every kind, its candidates and who would get the work right now."""
        out = []
        for kind in WORK_KINDS.values():
            choice = await self.pick(kind.id)
            candidates = []
            for adapter_id in kind.order:
                adapter = self.registry.get(adapter_id)
                if adapter is None:
                    continue
                candidates.append(
                    {
                        "id": adapter_id,
                        "name": adapter.info.name,
                        "eligible": self.eligible(kind.id, adapter, False) is None,
                    }
                )
            out.append(
                {
                    "id": kind.id,
                    "label": kind.label,
                    "description": kind.description,
                    # The demo adapter only exists in demo mode; don't advertise it otherwise.
                    "order": [a for a in kind.order if a != "mock" or self.registry.get(a)],
                    "override": overrides().get(kind.id, "auto"),
                    "candidates": candidates,
                    "current": choice.adapter.info.id if choice.adapter else None,
                    "current_name": choice.adapter.info.name if choice.adapter else None,
                    "reason": choice.reason or "; ".join(choice.skipped) or "uygun model yok",
                }
            )
        return out
