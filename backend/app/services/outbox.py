"""Side effects that must only happen after the DB transaction commits (jobs, realtime, email)."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from backend.app.core.logging import get_logger

log = get_logger("provok.outbox")

Action = Callable[[], Awaitable[object]]


class Outbox:
    def __init__(self) -> None:
        self._actions: list[Action] = []

    def add(self, action: Action) -> None:
        self._actions.append(action)

    def extend(self, other: Outbox) -> None:
        self._actions.extend(other._actions)

    async def flush(self) -> None:
        actions, self._actions = self._actions, []
        for action in actions:
            try:
                await action()
            except Exception as exc:  # one failing side effect must not block the rest
                log.error("outbox_action_failed", error=str(exc), action=getattr(action, "__name__", repr(action)))
