"""In-process async pub/sub event bus.

Services publish domain events (appointment.booked, appointment.cancelled)
after commit.  The WebSocket route subscribes and broadcasts to the frontend.
"""

import asyncio
import threading
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DomainEvent:
    topic: str
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


class EventBus:
    """Simple in-process fan-out using asyncio.Queue per subscriber."""

    def __init__(self) -> None:
        self._subscribers: list[
            tuple[asyncio.AbstractEventLoop, asyncio.Queue[DomainEvent]]
        ] = []
        self._lock = threading.Lock()

    async def publish(self, event: DomainEvent) -> None:
        self.publish_threadsafe(event)

    def publish_threadsafe(self, event: DomainEvent) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers)
        for loop, queue in subscribers:
            if loop.is_running() and not loop.is_closed():
                loop.call_soon_threadsafe(queue.put_nowait, event)

    async def subscribe(self) -> AsyncGenerator[DomainEvent, None]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[DomainEvent] = asyncio.Queue()
        subscription = (loop, queue)
        with self._lock:
            self._subscribers.append(subscription)
        try:
            while True:
                yield await queue.get()
        finally:
            with self._lock:
                self._subscribers.remove(subscription)


# Global singleton
event_bus = EventBus()
