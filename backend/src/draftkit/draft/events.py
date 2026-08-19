"""In-process pub/sub for session events, consumed by the SSE endpoint.

Deliberately tiny: one asyncio.Queue per connected browser tab. A dropped
subscriber just stops being fed; nothing blocks a pick from being recorded.
"""

import asyncio
import contextlib
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[int, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, session_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers[session_id].append(queue)
        return queue

    def unsubscribe(self, session_id: int, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(session_id, [])
        if queue in subs:
            subs.remove(queue)

    def publish(self, session_id: int, event: str, data: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(session_id, [])):
            # a stalled tab must never block the draft
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait({"event": event, "data": data})

    def subscriber_count(self, session_id: int) -> int:
        return len(self._subscribers.get(session_id, []))
