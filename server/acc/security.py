"""Security policy in one place: what agents and checks may never read, the sandbox rules,
and redaction of secrets before anything is written to Orbit's own logs.

Everything here is enforced by the OS sandbox or by Claude Code's permission engine — never
by asking a model nicely.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from acc import config

# Files that typically hold secrets. Agents can't read them with file tools, and Claude Code
# also applies Read-deny rules to sandboxed shell commands (verified: `cat .env` is refused).
# `.env.example` and similar templates stay readable.
SECRET_FILE_GLOBS = [
    "**/.env",
    "**/.env.local",
    "**/.env.*.local",
    "**/.env.production",
    "**/.env.prod",
    "**/.env.development",
    "**/.env.staging",
    "**/*.pem",
    "**/*.key",
    "**/*.p8",  # App Store Connect API keys
    "**/*.p12",
    "**/*.pfx",
    "**/*.keystore",
    "**/*.jks",
    "**/id_rsa*",
    "**/id_ed25519*",
    "**/.npmrc",
    "**/.pypirc",
    "**/.netrc",
    "**/credentials.json",
    "**/service-account*.json",
]

# Credential stores in the home folder: invisible to every sandboxed command.
CREDENTIAL_DIRS = [
    "~/.ssh",
    "~/.aws",
    "~/.gnupg",
    "~/.config/gh",
    "~/.config/gcloud",
    "~/.kube",
    "~/.docker",
    "~/.netrc",
    "~/.npmrc",
    "~/.pypirc",
    "~/.claude",
    "~/.codex",
    "~/Library/Keychains",
]

# Package registries: the only network sandboxed commands may reach (to install deps).
PACKAGE_REGISTRIES = [
    "registry.npmjs.org",
    "registry.yarnpkg.com",
    "pypi.org",
    "files.pythonhosted.org",
]


def _orbit_private_files() -> list[str]:
    """Orbit's own database holds every chat; sandboxed commands must not read it."""
    db = config.DATA_DIR / "acc.db"
    return [str(db), f"{db}-wal", f"{db}-shm"]


def claude_base_settings() -> dict[str, Any]:
    """Applied to every Claude Code run (chat, planning, agent steps)."""
    return {"permissions": {"deny": [f"Read({g})" for g in SECRET_FILE_GLOBS]}}


def claude_sandbox_settings() -> dict[str, Any]:
    """For agents that may run shell commands."""
    return {
        "sandbox": {
            "enabled": True,
            "autoAllowBashIfSandboxed": True,
            "allowUnsandboxedCommands": False,
            "failIfUnavailable": True,  # no sandbox -> nothing runs
            "network": {"allowedDomains": PACKAGE_REGISTRIES},
            "filesystem": {"denyRead": [*CREDENTIAL_DIRS, *_orbit_private_files()]},
        }
    }


def srt_settings(writable: Path) -> dict[str, Any]:
    """sandbox-runtime config for quality-gate commands Orbit itself runs."""
    return {
        "network": {"allowedDomains": PACKAGE_REGISTRIES, "deniedDomains": []},
        "filesystem": {
            "denyRead": [*CREDENTIAL_DIRS, *_orbit_private_files()],
            "allowWrite": [str(writable)],  # TMPDIR points inside it; /tmp stays closed
            "denyWrite": [],
        },
    }


# --- redaction -------------------------------------------------------------------------

_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWT
]
_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|PRIVATE_?KEY)[A-Z0-9_]*)"
    r"(\s*[:=]\s*)(['\"]?)([^\s'\"]{6,})"
)
MASK = "[gizli]"


def redact(text: str) -> str:
    for p in _PATTERNS:
        text = p.sub(MASK, text)
    return _ASSIGNMENT.sub(lambda m: f"{m[1]}{m[2]}{m[3]}{MASK}", text)


def redact_data(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_data(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_data(v) for v in value]
    return value
