"""Specialist agents are configuration, not processes: a role, allowed tools, and which
adapters it prefers. Tool lists are enforced by the CLI (--tools), not by the prompt."""

from dataclasses import dataclass

READ_ONLY_TOOLS = ["Read", "Glob", "Grep"]


@dataclass(frozen=True)
class Agent:
    id: str
    name: str
    description: str
    tools: list[str]
    adapters: list[str]  # preference order
    writes_files: bool


AGENTS: dict[str, Agent] = {
    a.id: a
    for a in [
        Agent(
            "orchestrator",
            "Orchestrator",
            "İsteği analiz eder, alt görevlere böler, ajan ve model seçer, plan sunar.",
            READ_ONLY_TOOLS,
            ["claude_code", "mock"],
            False,
        ),
        Agent(
            "research",
            "Araştırma",
            "Kod tabanı, dokümantasyon ve web araştırması yapar.",
            [*READ_ONLY_TOOLS, "WebSearch", "WebFetch"],
            ["claude_code", "mock"],
            False,
        ),
        Agent(
            "architect",
            "Mimar",
            "Teknik mimari, veri modeli ve teknoloji seçimleri.",
            READ_ONLY_TOOLS,
            ["claude_code", "mock"],
            False,
        ),
        Agent(
            "developer",
            "Geliştirici",
            "Kod yazar ve dosyaları değiştirir. Yalnızca görevin izole worktree'sinde çalışır.",
            [*READ_ONLY_TOOLS, "Edit", "Write", "Bash"],
            ["claude_code", "mock"],
            True,
        ),
        Agent(
            "qa",
            "QA",
            "Testleri çalıştırır, hataları raporlar. Dosya değiştiremez.",
            [*READ_ONLY_TOOLS, "Bash"],
            ["claude_code", "mock"],
            False,
        ),
        Agent(
            "reviewer",
            "Kod İnceleme",
            "Kod kalitesi, güvenlik ve performans incelemesi.",
            READ_ONLY_TOOLS,
            ["claude_code", "mock"],
            False,
        ),
        Agent(
            "docs",
            "Dokümantasyon",
            "README, teknik doküman ve proje notları yazar.",
            [*READ_ONLY_TOOLS, "Edit", "Write"],
            ["claude_code", "mock"],
            True,
        ),
    ]
}
