"""Where the tokens went: per model, per day, and the turns that used the most.

Built from what each turn already keeps (`messages.meta.team.usage`, filled by the orchestra
from every provider's own counts), so it costs nothing extra and needs no new table. Days are
the computer's local days.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from acc.db import session
from acc.models import Chat, Message

TOP = 5
_GUESS = (("GPT", "Codex"), ("Codex", "Codex"), ("Gemini", "Gemini"))


def _vendor(model: str, entry: dict[str, Any]) -> str:
    """Turns saved before the vendor was recorded: tell it from the model's name."""
    if entry.get("vendor"):
        return str(entry["vendor"])
    for prefix, vendor in _GUESS:
        if model.startswith(prefix):
            return vendor
    return "Claude"


def _local_day(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone().date().isoformat()


def summary(days: int = 7) -> dict[str, Any]:
    today = datetime.now().astimezone().date()
    first = today - timedelta(days=days - 1)
    since = datetime.combine(first, datetime.min.time()).astimezone()  # local midnight
    with session() as s:
        rows = s.execute(
            select(Message.id, Message.chat_id, Message.created_at, Message.meta, Chat.title)
            .join(Chat, Chat.id == Message.chat_id)
            .where(Message.role == "assistant", Message.created_at >= since.astimezone(UTC))
            .order_by(Message.id)
        ).all()

    day_keys = [(first + timedelta(days=i)).isoformat() for i in range(days)]
    by_day = {d: {"date": d, "input": 0, "output": 0, "cached": 0, "turns": 0} for d in day_keys}
    by_model: dict[str, dict[str, Any]] = {}
    turns: list[dict[str, Any]] = []
    for message_id, chat_id, created, meta, title in rows:
        used = ((meta or {}).get("team") or {}).get("usage") or {}
        if not used:
            continue
        day = by_day.get(_local_day(created))
        if day is None:
            continue
        turn = {"input": 0, "output": 0, "cached": 0}
        for model, entry in used.items():
            if not isinstance(entry, dict):
                continue
            row = by_model.setdefault(
                model,
                {
                    "model": model,
                    "vendor": _vendor(model, entry),
                    "input": 0,
                    "output": 0,
                    "cached": 0,
                    "turns": 0,
                },
            )
            row["turns"] += 1
            for k in ("input", "output", "cached"):
                n = int(entry.get(k) or 0)
                row[k] += n
                day[k] += n
                turn[k] += n
        day["turns"] += 1
        turns.append(
            {
                "message_id": message_id,
                "chat_id": chat_id,
                "chat_title": title,
                "date": _local_day(created),
                "models": sorted(used),
                **turn,
            }
        )

    models = sorted(by_model.values(), key=lambda r: r["input"] + r["output"], reverse=True)
    top = sorted(turns, key=lambda t: t["input"] + t["output"], reverse=True)[:TOP]
    totals = {k: sum(r[k] for r in models) for k in ("input", "output", "cached")}
    return {
        "days": days,
        "totals": {**totals, "turns": len(turns)},
        "by_day": list(by_day.values()),
        "by_model": models,
        "top_turns": top,
    }
