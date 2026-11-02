"""Design variants: the assistant writes self-contained HTML screens into its output folder;
Orbit renders them to PNG and shows them side by side.

Rendering is locked down — JavaScript off, every network request aborted — so a generated
page can't run code or call out; it can only draw. The UI only ever shows the PNGs.
"""

from __future__ import annotations

import re
from pathlib import Path

from acc import config

VIEWPORTS = {"phone": (393, 852), "tablet": (820, 1180), "desktop": (1280, 800)}
SCALE = 2
MAX_VARIANTS = 4
_HEADER = re.compile(r"<!--(.*?)-->", re.S)
_TITLE = re.compile(r"<title>(.*?)</title>", re.S | re.I)


def folder(message_id: int) -> Path:
    return config.DESIGNS_DIR / str(message_id)


def _meta(html: str, fallback: str) -> dict[str, str]:
    """Reads the `<!-- başlık: … | fikir: … | görünüm: … -->` header the assistant writes."""
    fields: dict[str, str] = {}
    if m := _HEADER.search(html[:2000]):
        for part in m.group(1).split("|"):
            key, _, value = part.partition(":")
            fields[key.strip().lower()] = value.strip()
    title = fields.get("başlık") or (t[1].strip() if (t := _TITLE.search(html)) else fallback)
    viewport = fields.get("görünüm", "phone").lower()
    return {
        "title": title[:60],
        "idea": fields.get("fikir", ""),
        "viewport": viewport if viewport in VIEWPORTS else "phone",
    }


def collect(out_dir: Path) -> list[dict[str, str]]:
    """HTML screens the assistant wrote this turn, in name order."""
    variants = []
    for n, path in enumerate(sorted(out_dir.glob("*.html"))[:MAX_VARIANTS], start=1):
        html = path.read_text(encoding="utf-8", errors="replace")
        variants.append({"html": html, **_meta(html, f"Tasarım {n}")})
    return variants


async def render(message_id: int, variants: list[dict[str, str]]) -> list[dict]:
    """Copy each variant's HTML next to its screenshot. Returns per-variant metadata."""
    out = folder(message_id)
    out.mkdir(parents=True, exist_ok=True)
    for n, v in enumerate(variants, start=1):
        (out / f"v{n}.html").write_text(v["html"], encoding="utf-8")

    rendered = False
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path=config.CHROMIUM_PATH)
            for n, v in enumerate(variants, start=1):
                width, height = VIEWPORTS[v["viewport"]]
                context = await browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=SCALE,
                    java_script_enabled=False,
                )
                await context.route("**/*", lambda route: route.abort())  # no network at all
                page = await context.new_page()
                await page.set_content(v["html"], wait_until="load", timeout=15_000)
                await page.screenshot(path=str(out / f"v{n}.png"))
                await context.close()
            await browser.close()
        rendered = True
    except Exception as e:  # missing browser, bad HTML, …: keep the HTML, report no image
        (out / "render-error.txt").write_text(str(e)[:2000])

    return [
        {
            "n": n,
            "title": v["title"],
            "idea": v["idea"],
            "viewport": v["viewport"],
            "image": f"/api/designs/{message_id}/{n}.png" if rendered else None,
            "attachment": f"design:{message_id}:{n}",
        }
        for n, v in enumerate(variants, start=1)
    ]


def previous_block(message_ids: list[int]) -> str:
    """Earlier design rounds in this chat, so "1'in renkleri, 2'nin düzeni" can be followed."""
    lines = []
    for mid in message_ids:
        for html in sorted(folder(mid).glob("v*.html")):
            lines.append(f"- tur #{mid}, tasarım {html.stem[1:]}: {html}")
    if not lines:
        return ""
    return "ÖNCEKİ TASARIMLAR (HTML'lerini Read ile açabilirsin):\n" + "\n".join(lines) + "\n\n"
