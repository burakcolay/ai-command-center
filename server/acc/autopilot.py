"""Otopilot: the team works through the Project Card's phases without a "devam" each time.

Off by default; the user turns it on per chat and it allows a fixed number of turns. After
each turn Orbit decides from measured facts, not from the model's say-so, whether to go on:
  - the turn changed code (no change usually means the lead is asking the user something),
  - the quality checks Orbit ran itself passed,
  - the independent review found nothing serious, or it was fixed,
  - the card has one more phase ticked than before the turn ("- [x]" in "## Aşamalar"),
    and phases are left,
  - Claude's measured quota is not nearly used up.
Any "no" stops it with the reason shown under the reply, and turns it off.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acc.review import SERIOUS

TURNS = 6  # auto turns per switch-on
QUOTA_STOP = 0.85
PROMPT = "Devam: kartta sıradaki aşama (otopilot)."
NOTE = (
    "OTOPİLOT AÇIK: Kullanıcı aşamaları senin ilerletmeni istiyor; her tur yalnızca kartta "
    "sıradaki tek aşamayı bitir. Aşama bitip kalite kontrolleri geçince PROJE.md'de o aşamayı "
    '"- [x]" yap; Orbit bir sonraki aşamayı kendisi başlatır. Kartla uyumlu küçük kararlarda '
    "makul olanı seç ve Kararlar'a yaz. Geri dönüşü zor ya da kartta olmayan bir karar "
    "gerekirse dur, soruyu sor ve aşamayı işaretleme.\n\n"
)


@dataclass(frozen=True)
class Decision:
    go: bool
    reason: str
    phase: str = ""  # e.g. "3/5": the phase the next turn works on

    def meta(self) -> dict[str, Any]:
        return {"go": self.go, "reason": self.reason, "phase": self.phase}


def _done(phases: list[dict[str, Any]]) -> int:
    return sum(1 for p in phases if p.get("done"))


def decide(
    *,
    changed: bool,
    checks: list[dict[str, Any]] | None,
    review: dict[str, Any] | None,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    quota: float | None,
) -> Decision:
    if not changed:
        return Decision(
            False, "Bu turda değişiklik olmadı; asistan senden bir cevap bekliyor olabilir."
        )
    failed = [c for c in checks or [] if c.get("status") == "failed"]
    if failed:
        return Decision(False, f"Kalite kontrolü geçmedi ({failed[0].get('name')}).")
    serious = [i for i in (review or {}).get("issues") or [] if i.get("onem") in SERIOUS]
    if serious and not (review or {}).get("fixed"):
        return Decision(False, "İnceleme ciddi bir sorun buldu ve düzeltilemedi.")
    if not after:
        return Decision(
            False, 'Kartta işaretlenebilir aşama yok (Aşamalar bölümünde "- [ ]" satırları).'
        )
    total, done = len(after), _done(after)
    if done == total:
        return Decision(False, "Kartın bütün aşamaları tamamlandı.")
    if done <= _done(before):
        return Decision(
            False, "Bu turda yeni bir aşama tamamlanmadı; asistan senden karar bekliyor olabilir."
        )
    if quota is not None and quota >= QUOTA_STOP:
        return Decision(False, f"Claude kotası %{round(quota * 100)}; kotayı korumak için durdu.")
    return Decision(True, "Sıradaki aşamaya geçiliyor.", f"{done + 1}/{total}")
