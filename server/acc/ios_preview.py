"""iOS preview: build the app for the Simulator and screenshot it (macOS with Xcode only).

1. Build: `xcodebuild … -sdk iphonesimulator CODE_SIGNING_ALLOWED=NO`, in the same sandbox as
   the checks (writes only in the isolated copy; DerivedData, package checkouts, temp files and
   the home folder Xcode writes to are all redirected inside it; network only to package
   registries). If that fails, the user may retry this one run outside the sandbox: Xcode then
   runs the project's build scripts with the user's own rights, so Orbit only does that after
   an explicit confirmation for that run.
2. Show: the built .app is installed on an iPhone simulator, launched, screenshotted, then
   terminated and uninstalled; a simulator Orbit booted is shut down again. A Simulator app is
   a Mac process with the user's rights, so every iOS preview needs the user's confirmation.

Commands are standard `xcrun simctl` subcommands (list --json, bootstatus -b, install, launch,
status_bar override, io screenshot, terminate, uninstall, shutdown). Orbit's own test suite
runs them against stand-ins for xcodebuild and xcrun; the first real run is on the user's Mac.
"""

from __future__ import annotations

import asyncio
import json
import os
import plistlib
import re
import shlex
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from acc import checks
from acc.cost_guard import sanitized_env

BUILD_DIR = ".orbit-cache/ios"  # DerivedData inside the copy (Orbit's cache, never committed)
LAUNCH_WAIT_S = 4.0
STEP_TIMEOUT_S = 240
CONFIRM = (
    "iOS önizlemesi uygulamayı Simülatör'de açar. Simülatör uygulamaları Mac'inde senin "
    "yetkilerinle çalışır (dosyalarına ve internete erişebilir). Derleme sandbox'ta yapılır. "
    "Devam edilsin mi?"
)
CONFIRM_UNSANDBOXED = (
    "Sandbox dışında derleme, projenin derleme betiklerini (Run Script, paketler) Mac'inde "
    "korumasız çalıştırır. Kodu gözden geçirdiysen yalnızca bu sefer için devam et."
)


def xcrun() -> str | None:
    return os.environ.get("ACC_XCRUN") or shutil.which("xcrun")


def xcodebuild() -> str | None:
    return os.environ.get("ACC_XCODEBUILD") or shutil.which("xcodebuild")


def available() -> bool:
    if not (xcrun() and xcodebuild()):
        return False
    return sys.platform == "darwin" or bool(os.environ.get("ACC_XCRUN"))  # tests use stand-ins


def find(cwd: Path) -> dict[str, str] | None:
    """The Xcode workspace or project at the root or in ios/ (React Native / Expo / Capacitor
    keep it there). A workspace wins: it is what CocoaPods and multi-project apps build."""
    for folder in (cwd, cwd / "ios"):
        if not folder.is_dir():
            continue
        spaces = sorted(p for p in folder.glob("*.xcworkspace") if p.is_dir())
        projects = sorted(p for p in folder.glob("*.xcodeproj") if p.is_dir())
        if spaces:
            return {"flag": "-workspace", "path": str(spaces[0].relative_to(cwd))}
        if projects:
            return {"flag": "-project", "path": str(projects[0].relative_to(cwd))}
    return None


def scheme(cwd: Path, found: dict[str, str]) -> str:
    """A shared scheme named like the project, else the first shared one, else the project's
    name (Xcode makes a scheme per target when none is shared)."""
    path = cwd / found["path"]
    stem = path.stem
    containers = [path] if path.suffix == ".xcodeproj" else sorted(path.parent.glob("*.xcodeproj"))
    shared = sorted(
        s.stem for c in containers for s in (c / "xcshareddata" / "xcschemes").glob("*.xcscheme")
    )
    if stem in shared:
        return stem
    return shared[0] if shared else stem


def build_command(cwd: Path, found: dict[str, str], name: str) -> str:
    out = BUILD_DIR
    return " ".join(
        [
            shlex.quote(xcodebuild() or "xcodebuild"),
            found["flag"],
            shlex.quote(found["path"]),
            "-scheme",
            shlex.quote(name),
            "-configuration Debug -sdk iphonesimulator",
            "-destination 'generic/platform=iOS Simulator'",
            f"-derivedDataPath {out} -clonedSourcePackagesDirPath {out}/packages",
            "CODE_SIGNING_ALLOWED=NO build",
        ]
    )


def built_app(cwd: Path, name: str) -> Path | None:
    products = cwd / BUILD_DIR / "Build" / "Products" / "Debug-iphonesimulator"
    apps = [a for a in sorted(products.glob("*.app")) if not a.name.endswith("-Runner.app")]
    return next((a for a in apps if a.stem == name), apps[0] if apps else None)


def bundle_id(app: Path) -> str | None:
    try:
        with (app / "Info.plist").open("rb") as f:
            value = plistlib.load(f).get("CFBundleIdentifier")
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None
    return str(value) if value else None


def _version(runtime: str) -> tuple[int, ...]:
    m = re.search(r"iOS-(\d+(?:-\d+)*)", runtime)
    return tuple(int(x) for x in m[1].split("-")) if m else ()


def pick_device(listing: dict[str, Any]) -> dict[str, Any] | None:
    """A booted iPhone if there is one, else an iPhone on the newest iOS runtime."""
    phones = []
    for runtime, devices in (listing.get("devices") or {}).items():
        if "iOS" not in runtime:
            continue
        for d in devices:
            if d.get("isAvailable", True) and str(d.get("name", "")).startswith("iPhone"):
                phones.append({**d, "runtime": runtime, "version": _version(runtime)})
    if not phones:
        return None
    booted = [d for d in phones if d.get("state") == "Booted"]
    if booted:
        return booted[0]
    return max(phones, key=lambda d: d["version"])


async def _xcrun(*args: str, timeout: float = STEP_TIMEOUT_S) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        xcrun() or "xcrun",
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=sanitized_env(),
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        return -1, f"zaman aşımı: xcrun {' '.join(args[:2])}"
    return proc.returncode or 0, out.decode(errors="replace")


async def _build_unsandboxed(cmd: str, cwd: Path) -> dict[str, Any]:
    """Only after the user's explicit confirmation for this run."""
    started = time.monotonic()
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=str(cwd),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=sanitized_env(),
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), 900)
    except TimeoutError:
        proc.kill()
        out, _ = await proc.communicate()
    return {
        "status": "passed" if proc.returncode == 0 else "failed",
        "command": cmd,
        "output": out.decode(errors="replace")[-6000:],
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


async def run(
    task_id: int, wt: Path, cwd: Path, out: Path, unsandboxed: bool = False
) -> dict[str, Any]:
    started = time.time()
    if not available():
        return {
            "status": "unsupported",
            "kind": "ios",
            "reason": "iOS önizlemesi için macOS'ta Xcode gerekir (xcode-select --install).",
        }
    found = find(cwd)
    if found is None:
        return {"status": "unsupported", "kind": "ios", "reason": "Xcode projesi bulunamadı."}
    name = scheme(cwd, found)
    # Xcode writes to ~/Library too; inside the sandbox that home is a folder in the copy.
    home = shlex.quote(str(cwd / BUILD_DIR / "home"))
    redirect = f"mkdir -p {home} && export HOME={home} CFFIXED_USER_HOME={home}; "
    cmd = build_command(cwd, found, name)
    if unsandboxed:
        result = await _build_unsandboxed(cmd, cwd)
    else:
        cfg = {"setup": None, "commands": [{"name": "ios-derleme", "command": redirect + cmd}]}
        results = await checks.run(cfg, wt, cwd, task_id)
        result = results[0] if results else {"status": "failed", "output": "çalışmadı"}
        if result["status"] == "skipped":  # no sandbox installed: never build unguarded silently
            return {"status": "error", "kind": "ios", "reason": result.get("output", "")}
    if result["status"] != "passed":
        return {
            "status": "build_failed",
            "kind": "ios",
            "command": cmd,
            "output": (result.get("output") or "")[-3000:],
            "sandboxed": not unsandboxed,
            "confirm": CONFIRM_UNSANDBOXED if not unsandboxed else "",
        }
    app = built_app(cwd, name)
    bundle = bundle_id(app) if app else None
    if not app or not bundle:
        return {"status": "no_output", "kind": "ios", "reason": "Derlenmiş .app bulunamadı."}
    return await _show(task_id, app, bundle, out, cmd, not unsandboxed, started)


async def _show(
    task_id: int, app: Path, bundle: str, out: Path, cmd: str, sandboxed: bool, started: float
) -> dict[str, Any]:
    code, listing = await _xcrun("simctl", "list", "--json", "devices", "available", timeout=60)
    try:
        device = pick_device(json.loads(listing)) if code == 0 else None
    except json.JSONDecodeError:
        device = None
    if device is None:
        return {
            "status": "error",
            "kind": "ios",
            "reason": "Kullanılabilir iPhone simülatörü yok (Xcode → Settings → Platforms).",
        }
    udid = str(device["udid"])
    booted_here = device.get("state") != "Booted"
    out.mkdir(parents=True, exist_ok=True)
    shot = out / "ios.png"
    try:
        for step in (
            ("simctl", "bootstatus", udid, "-b"),  # boots it if needed and waits until ready
            ("simctl", "install", udid, str(app)),
            ("simctl", "launch", "--terminate-running-process", udid, bundle),
        ):
            code, text = await _xcrun(*step)
            if code != 0:
                return {
                    "status": "error",
                    "kind": "ios",
                    "reason": f"xcrun {' '.join(step[:2])} başarısız: {text.strip()[-500:]}",
                }
        await _xcrun("simctl", "status_bar", udid, "override", "--time", "9:41", timeout=30)
        await asyncio.sleep(LAUNCH_WAIT_S)
        code, text = await _xcrun("simctl", "io", udid, "screenshot", "--type=png", str(shot))
        if code != 0 or not shot.is_file():
            return {
                "status": "error",
                "kind": "ios",
                "reason": f"Ekran görüntüsü alınamadı: {text}",
            }
    finally:  # leave the simulator as we found it
        await _xcrun("simctl", "terminate", udid, bundle, timeout=30)
        await _xcrun("simctl", "uninstall", udid, bundle, timeout=60)
        if booted_here:
            await _xcrun("simctl", "shutdown", udid, timeout=60)
    runtime = ".".join(str(x) for x in device["version"])
    return {
        "status": "ok",
        "kind": "ios",
        "images": {"ios": f"/api/previews/{task_id}/ios.png?t={int(started)}"},
        "errors": [],
        "blocked": [],
        "device": f"{device.get('name')} · iOS {runtime}".strip(),
        "build": cmd.split(" ", 1)[0].rsplit("/", 1)[-1],
        "sandboxed": sandboxed,
        "seconds": round(time.time() - started, 1),
    }
