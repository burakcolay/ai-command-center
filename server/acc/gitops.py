"""Git operations for task workspaces. Agents never run these; Orbit does.

Every task works in its own worktree on branch `orbit/task-<id>`, created from the
project's HEAD. The user's working tree is only touched by an approved merge.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Identity for commits Orbit makes on behalf of agents inside task worktrees.
AGENT_IDENTITY = ["-c", "user.name=Orbit", "-c", "user.email=orbit@localhost"]
NO_SIGN = ["-c", "commit.gpgsign=false"]
PATCH_LIMIT = 400_000  # bytes of patch text sent to the UI

# Build/test byproducts that agents create just by running code. Never committed, even when
# the project has no .gitignore, and never counted as "a read-only agent changed files".
JUNK = [
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
    ".DS_Store",
    ".coverage",
    ".orbit-cache",
    ".cc-writes",  # Claude Code's own bookkeeping folder inside the working directory
]
WITHOUT_JUNK = [
    "--",
    ".",
    *(f":(exclude,glob)**/{p}" for p in JUNK),
    *(f":(exclude,glob)**/{p}/**" for p in JUNK),
]


class GitError(Exception):
    pass


async def _run(cwd: Path, *args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"},
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


async def git(cwd: Path, *args: str) -> str:
    code, out, err = await _run(cwd, *args)
    if code != 0:
        raise GitError((err or out).strip() or f"git {args[0]} başarısız ({code})")
    return out


@dataclass
class RepoInfo:
    root: Path  # repository top level
    rel: Path  # project folder relative to root ("." when the project is the root)
    branch: str | None  # None when HEAD is detached
    head: str
    dirty: bool


async def repo_info(project_path: Path) -> RepoInfo:
    if not project_path.is_dir():
        raise GitError(f"Proje klasörü bulunamadı: {project_path}")
    code, out, _ = await _run(project_path, "rev-parse", "--show-toplevel")
    if code != 0:
        raise GitError(
            "Proje klasörü bir git deposu değil. Klasörde `git init` ve ilk commit'i yapın."
        )
    root = Path(out.strip()).resolve()
    code, head, _ = await _run(root, "rev-parse", "--verify", "-q", "HEAD")
    if code != 0:
        raise GitError("Depoda henüz commit yok. Yürütme için en az bir commit gerekli.")
    code, branch, _ = await _run(root, "symbolic-ref", "--short", "-q", "HEAD")
    status = await git(root, "status", "--porcelain")
    return RepoInfo(
        root=root,
        rel=project_path.resolve().relative_to(root),
        branch=branch.strip() if code == 0 else None,
        head=head.strip(),
        dirty=bool(status.strip()),
    )


async def ensure_worktree(root: Path, path: Path, branch: str, base: str) -> None:
    """Create (or reuse, when resuming) the task worktree."""
    if (path / ".git").exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    await git(root, "worktree", "prune")
    code, _, _ = await _run(root, "rev-parse", "--verify", "-q", f"refs/heads/{branch}")
    if code == 0:
        await git(root, "worktree", "add", str(path), branch)
    else:
        await git(root, "worktree", "add", "-b", branch, str(path), base)


async def is_dirty(wt: Path) -> bool:
    return bool((await git(wt, "status", "--porcelain", *WITHOUT_JUNK)).strip())


async def commit_all(wt: Path, message: str) -> str | None:
    """Commit everything in the worktree. Returns the sha, or None when nothing changed."""
    await git(wt, "add", "-A", *WITHOUT_JUNK)
    code, _, _ = await _run(wt, "diff", "--cached", "--quiet")
    if code == 0:
        return None
    await git(wt, *AGENT_IDENTITY, *NO_SIGN, "commit", "-q", "--no-verify", "-m", message)
    return (await git(wt, "rev-parse", "HEAD")).strip()


async def head(wt: Path) -> str:
    return (await git(wt, "rev-parse", "HEAD")).strip()


async def undo_commit(wt: Path, commit: str) -> None:
    """Drop `commit`, which must be the worktree's HEAD (the task branch only)."""
    if await head(wt) != commit:
        raise GitError("Son değişiklik en üstte değil; geri alınamadı.")
    await git(wt, "reset", "-q", "--hard", f"{commit}~1")


async def discard(wt: Path) -> None:
    """Drop uncommitted changes in the worktree (ignored files are left alone)."""
    await git(wt, "reset", "-q", "--hard", "HEAD")
    # Keep installed dependencies and Orbit's caches; they are never committed anyway.
    keep = [arg for p in JUNK for arg in ("-e", p)]
    await git(wt, "clean", "-fdq", *keep)


async def diff(wt: Path, base: str) -> dict[str, Any]:
    files = []
    for line in (await git(wt, "diff", "--numstat", "-M", base, "HEAD")).splitlines():
        added, removed, path = line.split("\t", 2)
        binary = added == "-"
        files.append(
            {
                "path": path,
                "added": 0 if binary else int(added),
                "removed": 0 if binary else int(removed),
                "binary": binary,
            }
        )
    patch = await git(wt, "diff", "--no-color", "-M", base, "HEAD")
    truncated = len(patch) > PATCH_LIMIT
    return {"files": files, "patch": patch[:PATCH_LIMIT], "truncated": truncated}


async def _identity_args(root: Path) -> list[str]:
    """Use the user's own git identity for merges; fall back to Orbit if none is set."""
    code, out, _ = await _run(root, "config", "user.email")
    return [] if code == 0 and out.strip() else AGENT_IDENTITY


async def merge(root: Path, branch: str, into: str, message: str) -> str:
    code, current, _ = await _run(root, "symbolic-ref", "--short", "-q", "HEAD")
    current = current.strip() if code == 0 else None
    if current != into:
        raise GitError(
            f"Projede şu an '{current or 'detached HEAD'}' açık. Birleştirme için "
            f"'{into}' branch'ine geçin (git checkout {into}) ve tekrar deneyin."
        )
    ident = await _identity_args(root)
    code, out, err = await _run(
        root, *ident, *NO_SIGN, "merge", "--no-ff", "--no-edit", "-m", message, branch
    )
    if code != 0:
        await _run(root, "merge", "--abort")
        raise GitError(
            "Birleştirme yapılamadı, proje değiştirilmedi. "
            "Commitlenmemiş değişiklikler veya çakışma olabilir:\n" + (err or out).strip()[-800:]
        )
    return (await git(root, "rev-parse", "HEAD")).strip()


async def remove_worktree(root: Path, path: Path, branch: str, merged: bool) -> None:
    await _run(root, "worktree", "remove", "--force", str(path))
    await _run(root, "worktree", "prune")
    await _run(root, "branch", "-d" if merged else "-D", branch)


async def changed_files(root: Path, base: str, head: str) -> list[str]:
    out = await git(root, "diff", "--name-only", base, head)
    return [line for line in out.splitlines() if line]


async def initial_commit(root: Path) -> None:
    await git(
        root,
        *AGENT_IDENTITY,
        *NO_SIGN,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "Orbit: proje oluşturuldu",
    )
