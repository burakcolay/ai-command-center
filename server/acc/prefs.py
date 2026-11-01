from typing import Any

from acc.db import session
from acc.models import Preference

# Keys the UI may set, with their allowed values (None = any value of the right kind).
# Anything else is rejected, so this never becomes a generic store.
ALLOWED: dict[str, set[Any] | None] = {
    "ollama_model": None,
    "notifications": {True, False},
    "quality": {"economy", "balanced", "best"},
    "claude_model": {"default", "sonnet", "opus", "fable"},
}


def get(key: str, default: Any = None) -> Any:
    with session() as s:
        p = s.get(Preference, key)
        return p.value if p else default


def put(key: str, value: Any) -> None:
    if key not in ALLOWED:
        raise KeyError(key)
    allowed = ALLOWED[key]
    if allowed is not None and value not in allowed:
        raise ValueError(value)
    with session() as s:
        p = s.get(Preference, key)
        if p:
            p.value = value
        else:
            s.add(Preference(key=key, value=value))
