"""GitHub: send a chat's changes as a pull request instead of merging locally.

Only ever runs when the user presses the button. The assistant itself can't push: its shell
runs in a sandbox whose network only reaches package registries. Pushing uses the user's own
git credentials and the `gh` CLI they logged in with (`gh auth login`); Orbit stores no tokens.
Only Orbit's own `orbit/task-<id>` branch is pushed; the PR is merged (or not) on GitHub.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from acc import security
from acc.gitops import _run as git_run  # read-only lookups

GH = os.environ.get("ACC_GH") or "gh"
TIMEOUT_S = 120
# https://github.com/owner/repo(.git) or git@github.com:owner/repo(.git)
_REMOTE = re.compile(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


class GitHubError(Exception):
    pass


@dataclass
class Status:
    repo: str | None  # owner/name when origin is on GitHub
    ready: bool  # gh installed and logged in
    reason: str  # why not, in Turkish, for the UI


def parse_remote(url: str) -> str | None:
    m = _REMOTE.search(url.strip())
    return f"{m[1]}/{m[2]}" if m else None


async def _exec(cwd: Path, *cmd: str) -> tuple[int, str]:
    """Run without ever waiting for a prompt (password, passphrase, "are you sure")."""
    env = {
        **os.environ,
        "GH_PROMPT_DISABLED": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "NO_COLOR": "1",
        "LC_ALL": "C",
    }
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
    except FileNotFoundError:
        return 127, f"{cmd[0]} bulunamadı"
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), TIMEOUT_S)
    except TimeoutError:
        proc.kill()
        return 124, f"{cmd[0]} zaman aşımına uğradı"
    return proc.returncode or 0, security.redact(out.decode(errors="replace"))


async def _gh(cwd: Path, *args: str) -> tuple[int, str]:
    return await _exec(cwd, GH, *args)


async def status(root: Path) -> Status:
    # The configured URL, not `remote get-url` (which applies insteadOf rewrites).
    code, url, _ = await git_run(root, "config", "--get", "remote.origin.url")
    repo = parse_remote(url) if code == 0 else None
    if repo is None:
        return Status(None, False, "Projenin GitHub'da bir 'origin' remote'u yok.")
    if shutil.which(GH) is None:
        return Status(repo, False, "GitHub CLI kurulu değil: brew install gh")
    code, _ = await _gh(root, "auth", "status", "--hostname", "github.com")
    if code != 0:
        return Status(repo, False, "GitHub'a giriş yapılmamış: gh auth login")
    return Status(repo, True, "")


async def push(root: Path, branch: str) -> None:
    """Push Orbit's branch. Force (with lease) because "undo last" rewrites it."""
    ref = f"refs/heads/{branch}"
    code, out = await _exec(
        root, "git", "push", "--force-with-lease", "-u", "origin", f"{ref}:{ref}"
    )
    if code != 0:
        raise GitHubError("Push başarısız: " + out.strip()[-600:])


async def create_pr(root: Path, repo: str, branch: str, base: str, title: str, body: str) -> str:
    code, out = await _gh(
        root,
        "pr",
        "create",
        "--repo",
        repo,
        "--base",
        base,
        "--head",
        branch,
        "--title",
        title,
        "--body",
        body,
    )
    url = next((w for w in out.split() if w.startswith("https://github.com/")), None)
    if code != 0 or url is None:
        raise GitHubError("PR açılamadı: " + out.strip()[-600:])
    return url
