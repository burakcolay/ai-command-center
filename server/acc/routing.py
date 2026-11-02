"""Which model does which kind of work.

Three kinds: the assistant (everything the user asks in chat), independent review of its
changes (preferably by a different model) and summaries/backup (free local model first).
The router skips models that can't do the work, aren't healthy, are blocked by the cost
guard or — when an alternative exists — are close to their subscription limit. The user can
pin a model per kind. Adapters that aren't set up yet are listed too and take over as soon
as they are.
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
            "assistant",
            "Asistan",
            "Sohbet, araştırma, tasarım ve kod değişikliği: hepsi tek asistan.",
            ["claude_code", "codex", "mock"],
            ("tools", "coding", "web_search"),
        ),
        WorkKind(
            "review",
            "Bağımsız inceleme",
            "Asistanın değişikliklerini birleştirmeden önce inceler. Yazandan farklı bir model "
            "tercih edilir; böylece biri kaçırdığını öteki yakalar.",
            ["codex", "claude_code", "mock"],
            ("tools", "review"),
        ),
        WorkKind(
            "summarize",
            "Özetleme ve yedek",
            "Uzun sohbetleri özetler; asistan kullanılamazsa sohbeti sürdürür. Yerel model önce.",
            ["ollama", "claude_code", "mock"],
            ("chat",),
        ),
    ]
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
        self, kind: str, needs_tools: bool = False, avoid: frozenset[str] = frozenset()
    ) -> Choice:
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

        first, first_use = usable[0]
        if overrides().get(kind) == first.info.id:
            return Choice(first, "elle seçildi", skipped)
        # A second opinion should come from someone else (e.g. Codex reviewing Claude's work).
        if avoid and first.info.id in avoid:
            for alt, _ in usable[1:]:
                if alt.info.id not in avoid:
                    return Choice(alt, f"{first.info.name} yazdı; ikinci göz farklı model", skipped)
        # Quota: move off a nearly used-up subscription when there is somewhere to go.
        if first_use is not None and first_use >= QUOTA_SOFT_LIMIT:
            for alt, use in usable[1:]:
                if use is None or use < QUOTA_SOFT_LIMIT:
                    reason = f"{first.info.name} kotası %{round(first_use * 100)}; yük aktarıldı"
                    return Choice(alt, reason, skipped)
        return Choice(first, "varsayılan sıra", skipped)

    async def describe(self) -> list[dict]:
        """For the UI: every kind, its candidates and who would get the work right now."""
        out = []
        for kind in WORK_KINDS.values():
            choice = await self.pick(kind.id)
            candidates = [
                {
                    "id": a.info.id,
                    "name": a.info.name,
                    "eligible": self.eligible(kind.id, a, False) is None,
                }
                for a in (self.registry.get(i) for i in kind.order)
                if a is not None
            ]
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
