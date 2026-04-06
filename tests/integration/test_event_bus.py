import pytest
from pvx.core.events import EventBus


@pytest.mark.asyncio
async def test_event_bus_subscribe_and_emit():
    bus = EventBus()
    received = []
    bus.subscribe("TEST_EVENT", lambda e: received.append(e))
    bus.emit("TEST_EVENT", {"key": "value"})
    assert len(received) == 1
    assert received[0].type == "TEST_EVENT"


@pytest.mark.asyncio
async def test_event_bus_event_ids_are_unique():
    bus = EventBus()
    e1 = bus.emit("A", {})
    e2 = bus.emit("A", {})
    assert e1.id != e2.id


@pytest.mark.asyncio
async def test_event_bus_multiple_subscribers():
    bus = EventBus()
    results = []
    bus.subscribe("X", lambda e: results.append(1))
    bus.subscribe("X", lambda e: results.append(2))
    bus.emit("X", {})
    assert results == [1, 2]


@pytest.mark.asyncio
async def test_event_bus_unknown_event_type_does_not_raise():
    bus = EventBus()
    bus.emit("UNSUBSCRIBED_EVENT", {})
