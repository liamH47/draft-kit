"""The SSE fan-out layer, exercised directly.

The endpoint is a thin wrapper over this bus; testing the bus keeps the
assertions precise and avoids a synchronous test client deadlocking on its
own open stream.
"""

import asyncio

from draftkit.draft.events import EventBus


async def test_publish_reaches_every_subscriber():
    bus = EventBus()
    a, b = bus.subscribe(1), bus.subscribe(1)
    bus.publish(1, "pick_recorded", {"player_id": "x"})
    assert await a.get() == {"event": "pick_recorded", "data": {"player_id": "x"}}
    assert await b.get() == {"event": "pick_recorded", "data": {"player_id": "x"}}


async def test_events_are_scoped_to_their_session():
    bus = EventBus()
    other = bus.subscribe(2)
    bus.subscribe(1)
    bus.publish(1, "pick_recorded", {"player_id": "x"})
    assert other.empty()


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    queue = bus.subscribe(1)
    bus.unsubscribe(1, queue)
    bus.publish(1, "pick_recorded", {})
    assert queue.empty()
    assert bus.subscriber_count(1) == 0


async def test_a_stalled_subscriber_never_blocks_publishing():
    bus = EventBus()
    stalled = bus.subscribe(1)
    for _ in range(stalled.maxsize + 5):
        bus.publish(1, "pick_recorded", {})  # must not raise or hang
    healthy = bus.subscribe(1)
    bus.publish(1, "pick_undone", {})
    assert await asyncio.wait_for(healthy.get(), timeout=1) == {
        "event": "pick_undone",
        "data": {},
    }
