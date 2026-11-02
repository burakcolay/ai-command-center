"""Preview: see the web app being built, without running its code unguarded.

1. Build: the project's build command runs in the same sandbox as the checks (writes only in
   the isolated copy, network only to package registries).
2. Show: Orbit opens the built static files in its own locked browser and takes phone and
   desktop screenshots. The page's JavaScript runs (inside Chromium's own sandbox), but there
   is no server process at all: Orbit answers requests for a made-up origin straight from the
   build folder, every request anywhere else is aborted and service workers are blocked.

Static sites (index.html at the project root) skip the build. Apps that need their backend
show whatever they render without it; the console errors are reported, so the assistant can
be asked to fix them.
"""

from __future__ import annotations

import json
import mimetypes
import time
from pathlib import Path
from typing import Any

from acc import checks, config, gitops

ORIGIN = "http://onizleme.orbit"
VIEWS = {"phone": (393, 852), "desktop": (1280, 800)}
OUTPUT_DIRS = ("dist", "build", "out", "public", ".")  # first one with an index.html wins
MAX_ERRORS = 12
OWN_BLOCK = "net::ERR_FAILED"
TEXT_TYPES = ("application/javascript", "application/json", "image/svg+xml")


def folder(task_id: int) -> Path:
    return config.DATA_DIR / "previews" / str(task_id)


def plan(cwd: Path) -> dict[str, Any] | None:
    """How to build this project for a preview, or None if it isn't a web project."""
    pkg = cwd / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
        scripts = data.get("scripts") or {}
        if "build" in scripts:
            if (cwd / "pnpm-lock.yaml").exists():
                pm = "pnpm"
            elif (cwd / "yarn.lock").exists():
                pm = "yarn"
            else:
                pm = "npm"
            needs_install = bool(data.get("dependencies") or data.get("devDependencies"))
            setup = checks.detect(cwd)["setup"] if needs_install else None
            return {"setup": setup, "build": f"{pm} run build"}
    if (cwd / "index.html").exists():
        return {"setup": None, "build": None}
    return None


def output_dir(cwd: Path) -> Path | None:
    for name in OUTPUT_DIRS:
        if (cwd / name / "index.html").is_file():
            return (cwd / name).resolve()
    return None


def content_type(path: Path) -> str:
    """Text files go out as UTF-8: without it Chromium falls back to Windows-1252 for a page
    with no <meta charset>, and Turkish letters come out garbled."""
    kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if kind.startswith("text/") or kind in TEXT_TYPES:
        return f"{kind}; charset=utf-8"
    return kind


def _local_file(root: Path, url: str) -> Path | None:
    """The build file behind a request to the preview origin (never outside the build)."""
    path = url[len(ORIGIN) :].split("?", 1)[0].split("#", 1)[0].lstrip("/") or "index.html"
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        return None
    if target.is_dir():
        target = target / "index.html"
    if target.is_file():
        return target
    if "." not in Path(path).name:  # an app route like /settings: single-page app fallback
        return root / "index.html"
    return None


async def render(root: Path, out: Path) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    out.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    blocked: list[str] = []

    async def route(r) -> None:
        url = r.request.url
        if url.startswith(ORIGIN + "/") or url == ORIGIN:
            if f := _local_file(root, url):
                await r.fulfill(body=f.read_bytes(), content_type=content_type(f))
            else:
                await r.fulfill(status=404, body="")
            return
        if len(blocked) < MAX_ERRORS and url[:200] not in blocked:
            blocked.append(url[:200])
        await r.abort()  # no network: nothing leaves this machine

    images: dict[str, str] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=config.CHROMIUM_PATH)
        try:
            for view, (width, height) in VIEWS.items():
                context = await browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=2,
                    service_workers="block",
                    is_mobile=view == "phone",
                    has_touch=view == "phone",
                )
                await context.route("**/*", route)
                page = await context.new_page()
                page.on(
                    "console",
                    lambda m: (
                        errors.append(m.text[:300])
                        if m.type == "error"
                        and len(errors) < MAX_ERRORS
                        and OWN_BLOCK not in m.text  # our own abort; listed under blocked
                        else None
                    ),
                )
                page.on(
                    "pageerror",
                    lambda e: errors.append(str(e)[:300]) if len(errors) < MAX_ERRORS else None,
                )
                try:
                    await page.goto(ORIGIN + "/", wait_until="networkidle", timeout=20_000)
                except Exception as e:  # a page that never settles still gets a picture
                    errors.append(f"Sayfa tam yüklenmedi: {e}"[:300])
                await page.wait_for_timeout(400)
                await page.screenshot(path=str(out / f"{view}.png"))
                images[view] = view
                await context.close()
        finally:
            await browser.close()
    return {"images": images, "errors": list(dict.fromkeys(errors)), "blocked": blocked}


async def run(task_id: int, wt: Path, cwd: Path) -> dict[str, Any]:
    """Build (sandboxed) and screenshot. Always cleans the build output away afterwards."""
    started = time.time()
    p = plan(cwd)
    if p is None:
        return {
            "status": "unsupported",
            "reason": "Web projesi bulunamadı: package.json'da build betiği ya da kökte "
            "index.html olmalı.",
        }
    try:
        if p["build"]:
            cfg = {"setup": p["setup"], "commands": [{"name": "derleme", "command": p["build"]}]}
            results = await checks.run(cfg, wt, cwd, task_id)
            failed = next((r for r in results if r["status"] != "passed"), None)
            if failed:
                return {
                    "status": "build_failed",
                    "command": failed.get("command"),
                    "output": failed.get("output", "")[-3000:],
                }
        root = output_dir(cwd)
        if root is None:
            return {"status": "no_output", "reason": "Derlemeden sonra index.html bulunamadı."}
        shot = await render(root, folder(task_id))
        return {
            "status": "ok",
            "images": {
                v: f"/api/previews/{task_id}/{v}.png?t={int(started)}" for v in shot["images"]
            },
            "errors": shot["errors"],
            "blocked": shot["blocked"],
            "build": p["build"],
            "seconds": round(time.time() - started, 1),
        }
    except Exception as e:  # missing browser, crash: report, never take the app down
        return {"status": "error", "reason": str(e)[:500]}
    finally:
        await gitops.discard(wt)  # the build output never ends up in the change


def prompt_block(preview: dict[str, Any] | None) -> str:
    """Problems the last preview found, so "düzelt" needs no copy-pasting."""
    if not preview:
        return ""
    if preview.get("status") == "build_failed":
        return (
            f"ÖNİZLEME DERLEMESİ BAŞARISIZ ({preview.get('command')}):\n"
            f"{(preview.get('output') or '')[-1500:]}\n\n"
        )
    errors = preview.get("errors") or []
    if preview.get("status") == "ok" and errors:
        lines = "\n".join(f"- {e}" for e in errors)
        blocked = preview.get("blocked") or []
        note = (
            "Not: önizlemede internet ve arka uç bilerek kapalıydı (engellenen: "
            + ", ".join(blocked[:3])
            + "). Yalnızca bundan doğan hatalar için kodu değiştirme; gerekirse yüklenme "
            "ve hata durumunu kullanıcıya düzgün göster.\n"
            if blocked
            else ""
        )
        return f"ÖNİZLEMEDE TARAYICI HATALARI (konsol):\n{lines}\n{note}\n"
    return ""
