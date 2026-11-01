"""Quality gates: the project's own test / lint / typecheck commands, run by Orbit itself
(not by an agent) before the user reviews a task, so "tests pass" is a measurement.

Agent-written code is untrusted — a planted test script could do anything — so every
command runs inside sandbox-runtime: writes only in the worktree, no credential folders,
network only to package registries. Without the sandbox, nothing runs.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shlex
import shutil
import time
from pathlib import Path
from typing import Any

from acc import config, security
from acc.env import sanitized_env

OUTPUT_TAIL = 6000  # chars of output kept per command


def detect(root: Path) -> dict[str, Any]:
    """Guess setup and check commands from the project's files. Nothing is executed."""
    setup: list[str] = []
    commands: list[dict[str, str]] = []

    pkg = root / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(pkg.read_text()).get("scripts") or {}
        except (json.JSONDecodeError, OSError):
            scripts = {}
        if (root / "pnpm-lock.yaml").exists():
            pm, install = "pnpm", "pnpm install --frozen-lockfile"
        elif (root / "yarn.lock").exists():
            pm, install = "yarn", "yarn install --frozen-lockfile"
        else:
            pm = "npm"
            install = "npm ci" if (root / "package-lock.json").exists() else "npm install"
        setup.append(install)
        for key in ("typecheck", "lint", "test"):
            script = scripts.get(key)
            if script and "no test specified" not in script:
                commands.append({"name": f"{pm} {key}", "command": f"{pm} run {key}"})

    pyproject = root / "pyproject.toml"
    py_text = pyproject.read_text() if pyproject.exists() else ""
    has_py_tests = (root / "tests").is_dir() or any(root.glob("test_*.py"))
    if (root / "uv.lock").exists():
        setup.append("uv sync")
        if has_py_tests or "pytest" in py_text:
            commands.append({"name": "pytest", "command": "uv run pytest -q"})
        if "[tool.ruff" in py_text or (root / "ruff.toml").exists():
            commands.append({"name": "ruff", "command": "uv run ruff check ."})
    elif (root / "requirements.txt").exists():
        setup.append("python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt pytest")
        if has_py_tests:
            commands.append({"name": "pytest", "command": ".venv/bin/python -m pytest -q"})
    elif has_py_tests:
        commands.append({"name": "pytest", "command": "python3 -m pytest -q"})

    makefile = root / "Makefile"
    if not commands and makefile.exists() and "\ntest:" in "\n" + makefile.read_text():
        commands.append({"name": "make test", "command": "make test"})

    return {"setup": " && ".join(setup) or None, "commands": commands}


def effective(configured: dict[str, Any] | None, root: Path) -> dict[str, Any]:
    return configured if configured is not None else detect(root)


def sandbox_available() -> bool:
    return config.SRT_BIN.exists() and shutil.which("node") is not None


async def _run_one(cmd: str, cwd: Path, settings_file: Path, env: dict[str, str]) -> dict:
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        str(config.SRT_BIN),
        "--settings",
        str(settings_file),
        "-c",
        cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), config.CHECK_TIMEOUT_S)
        code = proc.returncode
        timed_out = False
    except TimeoutError:
        proc.kill()
        out, _ = await proc.communicate()
        code, timed_out = None, True
    text = security.redact(out.decode(errors="replace"))
    return {
        "exit_code": code,
        "timed_out": timed_out,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "output": text[-OUTPUT_TAIL:],
    }


async def run(cfg: dict[str, Any], worktree: Path, cwd: Path, task_id: int) -> list[dict]:
    """Run setup + checks in the sandbox. Returns one result per command."""
    commands = cfg.get("commands") or []
    if not commands:
        return []
    if not sandbox_available():
        return [
            {
                **c,
                "status": "skipped",
                "output": "Sandbox (srt) kurulu değil; komutlar korumasız çalıştırılmaz. "
                "Kurmak için: make setup",
            }
            for c in commands
        ]

    settings_file = config.DATA_DIR / "srt" / f"task-{task_id}.json"
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(security.srt_settings(worktree)))
    cache = worktree / ".orbit-cache"
    env = {
        **sanitized_env(),
        "CI": "1",
        # Tool caches inside the worktree: the sandbox only allows writes there.
        "npm_config_cache": str(cache / "npm"),
        "UV_CACHE_DIR": str(cache / "uv"),
        "PIP_CACHE_DIR": str(cache / "pip"),
        "XDG_CACHE_HOME": str(cache),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    # The command gets a private temp dir (system /tmp isn't writable in the sandbox). It is
    # set inside the command, not on srt itself: srt keeps its own sockets in the system temp,
    # and unix socket paths must stay short (~104 chars on macOS).
    tmp = cache / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    prefix = f"export TMPDIR={shlex.quote(str(tmp))}; "

    results: list[dict] = []
    setup = cfg.get("setup")
    marker = cache / "setup.done"
    fingerprint = _setup_fingerprint(setup, cwd) if setup else ""
    if setup and marker.exists() and marker.read_text() == fingerprint:
        setup = None  # dependencies already installed in this worktree and unchanged
    if setup:
        r = await _run_one(prefix + setup, cwd, settings_file, env)
        ok = r["exit_code"] == 0
        if ok:
            marker.write_text(fingerprint)
        results.append(
            {"name": "kurulum", "command": setup, "status": "passed" if ok else "failed", **r}
        )
        if not ok:
            results += [
                {
                    **c,
                    "status": "skipped",
                    "output": "Kurulum başarısız olduğu için çalıştırılmadı.",
                }
                for c in commands
            ]
            return results
    for c in commands:
        r = await _run_one(prefix + c["command"], cwd, settings_file, env)
        results.append({**c, "status": "passed" if r["exit_code"] == 0 else "failed", **r})
    return results


LOCKFILES = (
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "pyproject.toml",
    "uv.lock",
    "requirements.txt",
)


def _setup_fingerprint(setup: str, cwd: Path) -> str:
    """Setup only reruns when the command or a dependency manifest changed."""
    h = hashlib.sha256(setup.encode())
    for name in LOCKFILES:
        f = cwd / name
        if f.exists():
            h.update(name.encode() + f.read_bytes())
    return h.hexdigest()


def failure_note(results: list[dict]) -> str:
    """Feedback for a revision step when checks fail."""
    failed = [r for r in results if r["status"] == "failed"]
    parts = [
        "Kalite kontrolleri başarısız oldu. Hataları düzelt. Testleri silme, atlama veya "
        "gevşetme; sorunun kök nedenini çöz."
    ]
    for r in failed:
        parts.append(f"$ {r['command']}\n{r.get('output', '')[-1500:]}")
    return "\n\n".join(parts)


def summary(results: list[dict]) -> str:
    if not results:
        return "kontrol yok"
    passed = sum(r["status"] == "passed" for r in results)
    failed = sum(r["status"] == "failed" for r in results)
    skipped = sum(r["status"] == "skipped" for r in results)
    bits = [f"{passed} geçti"]
    if failed:
        bits.append(f"{failed} başarısız")
    if skipped:
        bits.append(f"{skipped} atlandı")
    return ", ".join(bits)
