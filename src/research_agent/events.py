from __future__ import annotations

import asyncio
from collections import defaultdict

from .models import RunEvent


class EventBroker:
    """In-process event history plus live subscribers for the learning server."""

    def __init__(self, history_limit: int = 500) -> None:
        self.history_limit = history_limit
        self._history: dict[str, list[RunEvent]] = defaultdict(list)
        self._subscribers: dict[str, set[asyncio.Queue[RunEvent]]] = defaultdict(set)

    async def publish(self, event: RunEvent) -> None:
        history = self._history[event.run_id]
        history.append(event)
        if len(history) > self.history_limit:
            del history[: len(history) - self.history_limit]
        for queue in tuple(self._subscribers[event.run_id]):
            await queue.put(event)

    def history(self, run_id: str) -> list[RunEvent]:
        return list(self._history.get(run_id, []))

    async def subscribe(self, run_id: str):
        queue: asyncio.Queue[RunEvent] = asyncio.Queue(maxsize=100)
        self._subscribers[run_id].add(queue)
        try:
            for event in self.history(run_id):
                yield event
            while True:
                yield await queue.get()
        finally:
            self._subscribers[run_id].discard(queue)


broker = EventBroker()

