"""Which model, at which effort, for which role — the same plan for Claude and Codex.

Roles are vendor-neutral tiers ("güçlü", "orta", "hafif") plus an effort level; each vendor
maps a tier to its own model. The Settings "Kalite" choice picks a preset; the lead may pick
less (never more) per area in the Project Card, to spend as few tokens as the work allows.

Model names were checked: Claude Code takes the aliases opus / sonnet / haiku (a subagent with
"haiku" really ran on claude-haiku-5-5; `effort` is a validated subagent field). The Codex
tiers come from `codex debug models` (codex-cli 0.166): gpt-6-astra "frontier intelligence",
gpt-6.1-sol "workhorse for coding", gpt-6-luna "fast and affordable"; all take low…max.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TIERS = ("hafif", "orta", "guclu")  # weakest → strongest
EFFORTS = ("low", "medium", "high", "xhigh", "max")

CLAUDE = {"guclu": "opus", "orta": "sonnet", "hafif": "haiku"}
CODEX = {"guclu": "gpt-6-astra", "orta": "gpt-6.1-sol", "hafif": "gpt-6-luna"}
TIER_LABEL = {"guclu": "Güçlü", "orta": "Orta", "hafif": "Hafif"}


@dataclass(frozen=True)
class Power:
    tier: str  # one of TIERS
    effort: str  # one of EFFORTS

    def model_for(self, vendor: str) -> str | None:
        if vendor == "claude_code":
            return CLAUDE[self.tier]
        if vendor == "codex":
            return CODEX[self.tier]
        return None  # Gemini / local: their own single model, effort only

    def at_most(self, cap: Power) -> Power:
        tier = min(self.tier, cap.tier, key=TIERS.index)
        effort = min(self.effort, cap.effort, key=EFFORTS.index)
        return Power(tier, effort)

    def label(self) -> str:
        return f"{TIER_LABEL[self.tier]} · {self.effort}"


# role → Power, per quality preset. "lead" conducts (plans, splits, checks), "builder" writes
# code, "designer" draws screens, "reader" explores and researches, "reviewer" reviews.
PRESETS: dict[str, dict[str, Power]] = {
    "economy": {
        "lead": Power("orta", "medium"),
        "builder": Power("orta", "low"),
        "designer": Power("orta", "low"),
        "reader": Power("hafif", "low"),
        "reviewer": Power("hafif", "medium"),
    },
    "balanced": {
        "lead": Power("guclu", "high"),
        "builder": Power("orta", "medium"),
        "designer": Power("orta", "medium"),
        "reader": Power("hafif", "low"),
        "reviewer": Power("orta", "medium"),
    },
    "best": {
        "lead": Power("guclu", "xhigh"),
        "builder": Power("guclu", "medium"),
        "designer": Power("guclu", "medium"),
        "reader": Power("orta", "low"),
        "reviewer": Power("guclu", "high"),
    },
}

# The most an area specialist may get, whatever the card asks for.
BUILDER_CAP = {
    "economy": Power("orta", "medium"),
    "balanced": Power("guclu", "medium"),
    "best": Power("guclu", "high"),
}

_TIER_WORDS = {
    "guclu": "guclu",
    "güçlü": "guclu",
    "opus": "guclu",
    "astra": "guclu",
    "orta": "orta",
    "sonnet": "orta",
    "sol": "orta",
    "hafif": "hafif",
    "haiku": "hafif",
    "luna": "hafif",
}
_EFFORT_WORDS = {
    "low": "low",
    "düşük": "low",
    "dusuk": "low",
    "medium": "medium",
    "orta": "medium",
    "high": "high",
    "yüksek": "high",
    "yuksek": "high",
    "xhigh": "xhigh",
    "max": "max",
}


def parse(text: str) -> Power | None:
    """ "Orta · medium", "güçlü/high", "Opus medium" → Power. None if no tier is named."""
    words = [w for w in re.split(r"[\s·/,|-]+", text.strip().lower()) if w]
    tier = next((_TIER_WORDS[w] for w in words if w in _TIER_WORDS), None)
    if tier is None:
        return None
    rest = words[words.index(next(w for w in words if w in _TIER_WORDS)) + 1 :]
    effort = next((_EFFORT_WORDS[w] for w in rest if w in _EFFORT_WORDS), "medium")
    return Power(tier, effort)


def preset(quality: str) -> dict[str, Power]:
    return PRESETS.get(quality, PRESETS["balanced"])


def for_area(spec: str, quality: str) -> Power:
    """What an area specialist gets: the card's choice, capped by the quality setting."""
    default = preset(quality)["builder"]
    chosen = parse(spec) if spec else None
    return (chosen or default).at_most(BUILDER_CAP.get(quality, BUILDER_CAP["balanced"]))


def model_name(model_id: str | None) -> str:
    """claude-opus-5-5 → "Opus 5.5", gpt-6.1-sol → "GPT-6.1 Sol", opus → "Opus"."""
    if not model_id:
        return ""
    m = re.match(r"claude-([a-z]+)-(\d+)-(\d+)", model_id)
    if m:
        return f"{m[1].title()} {m[2]}.{m[3]}"
    m = re.match(r"gpt-([\d.]+)-([a-z]+)", model_id)
    if m:
        return f"GPT-{m[1]} {m[2].title()}"
    return model_id.replace("-", " ").title() if model_id.isalpha() else model_id
