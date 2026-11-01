"""macOS notifications for moments that need the user (plan ready, review ready, paused…).

Uses osascript with the text passed as arguments (never interpolated into the script), so a
task title can't inject AppleScript. Silently does nothing on other platforms.
"""

from __future__ import annotations

import asyncio
import sys

from acc import prefs

SCRIPT = [
    "-e",
    "on run argv",
    "-e",
    'display notification (item 2 of argv) with title (item 1 of argv) sound name "Glass"',
    "-e",
    "end run",
]
_pending: set[asyncio.Task[None]] = set()


def supported() -> bool:
    return sys.platform == "darwin"


def enabled() -> bool:
    return supported() and prefs.get("notifications", True) is not False


async def _send(title: str, body: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "osascript",
        *SCRIPT,
        title[:120],
        body[:240],
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()


def send(title: str, body: str, force: bool = False) -> bool:
    """Fire and forget. Returns whether a notification was attempted."""
    if not (force and supported()) and not enabled():
        return False
    try:
        job = asyncio.get_running_loop().create_task(_send(title, body))
    except RuntimeError:
        return False
    _pending.add(job)
    job.add_done_callback(_pending.discard)
    return True
