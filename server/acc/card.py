"""The Project Card (PROJE.md): the one document every agent reads before touching a project.

The lead assistant writes it from the user's idea or spec, the user approves it, and from
then on it is the shared understanding: goals, scope, architecture, the contract between
areas, and the team. Orbit reads its "Ekip" table to build one specialist per area (which
technology, which folder, built by Claude or Codex) and puts the card into every
specialist's instructions, so none of them starts without knowing the project.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

FILE = "PROJE.md"
LEAD_LIMIT = 16_000  # chars of the card in the lead's prompt
BRIEF_LIMIT = 8_000  # chars of the card inside each specialist's instructions

_TEAM_HEADING = re.compile(r"^#{2,3}\s*ek[iİı]p\b", re.I)
_PHASE_HEADING = re.compile(r"^#{2,3}\s*asamalar\b")  # after _TR and lower()
_PHASE = re.compile(r"^ ?(?:[-*+]|\d+[.)])\s+\[([ xX])\]\s+(.+)$")  # not nested
_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


@dataclass(frozen=True)
class Area:
    name: str  # e.g. "Backend"
    tech: str  # e.g. "FastAPI (Python 3.12)"
    folder: str  # e.g. "server/"
    builder: str  # "claude" or "codex"
    power: str = ""  # e.g. "Orta · medium": the lead's pick of model tier and effort

    @property
    def slug(self) -> str:
        s = re.sub(r"[^a-z0-9]+", "-", self.name.translate(_TR).lower()).strip("-")
        return s or "alan"


def read(folder: Path | None) -> str | None:
    if folder is None:
        return None
    path = folder / FILE
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return text or None


def _cells(line: str) -> list[str]:
    return [c.strip().strip("`").strip() for c in line.strip().strip("|").split("|")]


def team(text: str | None) -> list[Area]:
    """Rows of the "## Ekip" table: | Alan | Teknoloji | Klasör | Yapan | Güç |"""
    if not text:
        return []
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if _TEAM_HEADING.match(ln.strip())), None)
    if start is None:
        return []
    rows = []
    for ln in lines[start + 1 :]:
        s = ln.strip()
        if s.startswith("#"):
            break
        if s.startswith("|"):
            rows.append(_cells(s))
        elif rows and s:
            break  # the table ended
    if len(rows) < 2:
        return []
    header = [h.translate(_TR).lower() for h in rows[0]]

    def col(*names: str) -> int | None:
        return next((i for i, h in enumerate(header) if any(n in h for n in names)), None)

    i_area, i_tech = col("alan"), col("teknoloji", "dil")
    i_folder, i_builder = col("klasor"), col("yapan")
    i_power = col("guc", "seviye", "model")
    if i_area is None:
        return []
    areas, seen = [], set()
    for row in rows[1:]:
        if all(set(c) <= set("-: ") for c in row):  # the |---|---| line
            continue

        def get(i: int | None, row: list[str] = row) -> str:
            return row[i] if i is not None and i < len(row) else ""

        builder = "codex" if "codex" in get(i_builder).lower() else "claude"
        area = Area(get(i_area), get(i_tech), get(i_folder), builder, get(i_power))
        if area.name and area.slug not in seen:
            seen.add(area.slug)
            areas.append(area)
    return areas[:8]


def _trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[… kartın devamı {FILE} dosyasında; Read ile oku …]"


def lead_block(text: str | None) -> str:
    if not text:
        return ""
    return (
        f"PROJE KARTI ({FILE}: projenin ortak anlayışı; her işte buna uy, karar değişirse "
        f"güncelle):\n{_trim(text, LEAD_LIMIT)}\n\n"
    )


def brief(text: str) -> str:
    return _trim(text, BRIEF_LIMIT)


def phases(text: str | None) -> list[dict[str, object]]:
    """The checklist under "## Aşamalar": [{"title": "...", "done": bool}]. Only top-level
    "- [ ]" / "- [x]" lines count, so sub-steps don't change the progress."""
    if not text:
        return []
    out: list[dict[str, object]] = []
    inside = False
    for ln in text.splitlines():
        head = ln.strip().translate(_TR).lower()
        level = len(head) - len(head.lstrip("#"))
        if level and head[level : level + 1] == " ":  # a heading
            if level <= 3:  # a deeper one (#### …) stays inside the section
                inside = bool(_PHASE_HEADING.match(head))
            continue
        if inside and (m := _PHASE.match(ln)):
            out.append({"title": m[2].strip()[:200], "done": m[1] in "xX"})
    return out
