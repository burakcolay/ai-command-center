"""Project memory: a plain markdown file per project that every chat, plan and agent step sees.

The user writes lasting decisions and rules into it; Orbit appends a decision log entry each
time a task is merged. Files live in MEMORY_DIR, which can be a folder inside an Obsidian vault.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from acc import config

PROMPT_LIMIT = 12_000  # chars of memory included in prompts
LOG_HEADING = "## Karar Günlüğü"

TEMPLATE = """# {name} — Proje Hafızası

Orbit bu dosyayı bu projedeki her sohbete, plana ve ajana verir. Kalıcı kararları, kuralları
ve tercihleri buraya yaz (ör. kullanılan teknolojiler, tasarım dili, yapılmaması gerekenler).

## Notlar

{log_heading}
""".replace("{log_heading}", LOG_HEADING)


def path_for(project_name: str) -> Path:
    safe = re.sub(r'[\\/:*?"<>|#^\[\]]+', "-", project_name).strip(" .-") or "proje"
    return config.MEMORY_DIR / f"{safe}.md"


def read(project_name: str) -> str:
    p = path_for(project_name)
    return p.read_text(encoding="utf-8") if p.exists() else TEMPLATE.format(name=project_name)


def write(project_name: str, text: str) -> Path:
    p = path_for(project_name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return p


def append_decision(project_name: str, line: str) -> None:
    text = read(project_name).rstrip()
    if LOG_HEADING not in text:
        text += f"\n\n{LOG_HEADING}"
    write(project_name, f"{text}\n- {date.today().isoformat()} · {line}\n")


def for_prompt(project_name: str, limit: int = PROMPT_LIMIT) -> str | None:
    """Memory text for prompts, or None when nothing was written yet."""
    p = path_for(project_name)
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8").strip()
    if text == TEMPLATE.format(name=project_name).strip():
        return None
    if len(text) <= limit:
        return text
    half = limit // 2  # keep the hand-written top and the newest log entries
    return f"{text[:half]}\n\n[… hafızanın ortası kısaltıldı …]\n\n{text[-half:]}"


def prompt_block(project_name: str | None) -> str:
    mem = for_prompt(project_name) if project_name else None
    return f"PROJE HAFIZASI (kalıcı kararlar ve kurallar; bunlara uy):\n{mem}\n\n" if mem else ""
