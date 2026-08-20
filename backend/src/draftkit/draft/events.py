"""In-process pub/sub for session events, consumed by the SSE endpoint.

Two things here are load-bearing:

1. Picks are recorded by synchronous FastAPI endpoints, which run in a
   threadpool — not on the event loop. Waking an asyncio.Queue from another
   thread requires call_soon_threadsafe; put_nowait alone enqueues the item
   but never wakes the waiting stream, so events sit until the next keepalive.
2. A stalled or vanished subscriber must never block a pick from being
   recorded. Every delivery failure is dropped, not raised.
"""

import asyncio
import contextlib
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[int, list[tuple[asyncio.Queue, asyncio.AbstractEventLoop]]] = (
            defaultdict(list)
        )

    def subscribe(self, session_id: int) -> asyncio.Queue:
        """Called from the stream coroutine, so the running loop here is the
        one that must be woken on publish."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers[session_id].append((queue, asyncio.get_running_loop()))
        return queue

    def unsubscribe(self, session_id: int, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(session_id, [])
        self._subscribers[session_id] = [(q, loop) for q, loop in subs if q is not queue]

    def publish(self, session_id: int, event: str, data: dict[str, Any]) -> None:
        item = {"event": event, "data": data}
        for queue, loop in list(self._subscribers.get(session_id, [])):
            # A stalled tab must never block the draft.
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(self._offer, queue, item)

    @staticmethod
    def _offer(queue: asyncio.Queue, item: dict[str, Any]) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(item)

    def subscriber_count(self, session_id: int) -> int:
        return len(self._subscribers.get(session_id, []))
