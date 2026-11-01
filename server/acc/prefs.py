from typing import Any

from acc.db import session
from acc.models import Preference

# Keys the UI may set. Anything else is rejected, so this never becomes a generic store.
ALLOWED = {"ollama_model"}


def get(key: str, default: Any = None) -> Any:
    with session() as s:
        p = s.get(Preference, key)
        return p.value if p else default


def put(key: str, value: Any) -> None:
    if key not in ALLOWED:
        raise KeyError(key)
    with session() as s:
        p = s.get(Preference, key)
        if p:
            p.value = value
        else:
            s.add(Preference(key=key, value=value))
