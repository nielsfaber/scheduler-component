"""Tests for Scheduler action attribution."""

from unittest.mock import AsyncMock

from custom_components.scheduler import const
from custom_components.scheduler.actions import ActionHandler
from custom_components.scheduler.logbook import async_describe_events
from custom_components.scheduler.switch import async_service_run_action
import pytest

from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_NAME,
    ATTR_SERVICE_DATA,
    CONF_ACTION,
)
from homeassistant.core import Context, ServiceCall


@pytest.fixture
def timeslot():
    """Return a simple executable schedule timeslot."""
    return {
        const.ATTR_START: "21:00",
        "conditions": [],
        const.ATTR_CONDITION_TYPE: const.CONDITION_TYPE_AND,
        const.ATTR_TRACK_CONDITIONS: False,
        const.ATTR_ACTIONS: [
            {
                CONF_ACTION: "test.turn_on",
                ATTR_ENTITY_ID: "light.test_light",
                ATTR_SERVICE_DATA: {},
            }
        ],
    }


@pytest.mark.asyncio
async def test_action_execution_emits_trigger_and_propagates_context(hass, timeslot):
    """A service call shares its context with the Scheduler trigger event."""
    calls = []
    events = []

    async def record_service(call):
        calls.append(call)

    hass.services.async_register("test", "turn_on", record_service)
    hass.states.async_set("light.test_light", "off")
    hass.bus.async_listen(const.EVENT_SCHEDULE_TRIGGERED, events.append)

    handler = ActionHandler(hass, "schedule-id")
    await handler.async_queue_actions(
        timeslot,
        "Turn Off Aircon",
        "switch.schedule_276b13",
    )
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data == {
        ATTR_NAME: "Turn Off Aircon",
        ATTR_ENTITY_ID: "switch.schedule_276b13",
        const.ATTR_SOURCE: "timeslot at 21:00",
    }
    assert events[0].context.user_id is None
    assert len(calls) == 1
    assert calls[0].context.id == events[0].context.id


@pytest.mark.asyncio
async def test_action_batch_uses_one_trigger_context(hass, timeslot):
    """Multiple low-level calls in one queue do not create extra triggers."""
    calls = []
    events = []

    async def record_service(call):
        calls.append(call)

    hass.services.async_register("test", "turn_on", record_service)
    hass.states.async_set("light.test_light", "off")
    hass.bus.async_listen(const.EVENT_SCHEDULE_TRIGGERED, events.append)
    timeslot[const.ATTR_ACTIONS].append(
        {
            CONF_ACTION: "test.turn_on",
            ATTR_ENTITY_ID: "light.test_light",
            ATTR_SERVICE_DATA: {},
        }
    )

    handler = ActionHandler(hass, "schedule-id")
    await handler.async_queue_actions(
        timeslot,
        "Evening lights",
        "switch.schedule_evening_lights",
    )
    await hass.async_block_till_done()

    assert len(events) == 1
    assert len(calls) == 2
    assert {call.context.id for call in calls} == {events[0].context.id}


@pytest.mark.asyncio
async def test_action_batch_for_multiple_entities_uses_one_trigger_context(
    hass, timeslot
):
    """Separate entity queues share the execution context and trigger event."""
    calls = []
    events = []

    async def record_service(call):
        calls.append(call)

    hass.services.async_register("test", "turn_on", record_service)
    hass.states.async_set("light.test_light", "off")
    hass.states.async_set("light.test_light_two", "off")
    hass.bus.async_listen(const.EVENT_SCHEDULE_TRIGGERED, events.append)
    timeslot[const.ATTR_ACTIONS].append(
        {
            CONF_ACTION: "test.turn_on",
            ATTR_ENTITY_ID: "light.test_light_two",
            ATTR_SERVICE_DATA: {},
        }
    )

    handler = ActionHandler(hass, "schedule-id")
    await handler.async_queue_actions(
        timeslot,
        "Multi-target schedule",
        "switch.schedule_multi_target",
    )
    await hass.async_block_till_done()

    assert len(events) == 1
    assert {call.data[ATTR_ENTITY_ID][0] for call in calls} == {
        "light.test_light",
        "light.test_light_two",
    }
    assert {call.context.id for call in calls} == {events[0].context.id}


@pytest.mark.asyncio
async def test_action_execution_preserves_parent_context(hass, timeslot):
    """A manually initiated execution creates a child context."""
    calls = []
    events = []

    async def record_service(call):
        calls.append(call)

    parent_context = Context()
    hass.services.async_register("test", "turn_on", record_service)
    hass.states.async_set("light.test_light", "off")
    hass.bus.async_listen(const.EVENT_SCHEDULE_TRIGGERED, events.append)

    handler = ActionHandler(hass, "schedule-id")
    await handler.async_queue_actions(
        timeslot,
        "Manual schedule",
        "switch.schedule_manual",
        parent_context=parent_context,
    )
    await hass.async_block_till_done()

    assert events[0].context.parent_id == parent_context.id
    assert calls[0].context.id == events[0].context.id


@pytest.mark.asyncio
async def test_manual_run_action_preserves_parent_context(hass):
    """The run_action entity service passes its context to the schedule."""
    entity = AsyncMock()
    parent_context = Context()
    service_call = ServiceCall(
        hass,
        "switch",
        "run_action",
        {"time": None, const.ATTR_SKIP_CONDITIONS: True},
        context=parent_context,
    )

    await async_service_run_action(entity, service_call)

    assert entity.async_service_run_action.await_args.kwargs == {
        "time": None,
        "skip_conditions": True,
        "parent_context": parent_context,
    }


def test_logbook_descriptor_uses_schedule_name_and_safe_source():
    """The descriptor exposes schedule metadata, not service payloads."""
    described_events = {}

    def register(domain, event_type, describe):
        described_events[(domain, event_type)] = describe

    async_describe_events(None, register)
    description = described_events[(const.DOMAIN, const.EVENT_SCHEDULE_TRIGGERED)](
        type(
            "Event",
            (),
            {
                "data": {
                    ATTR_NAME: "Turn Off Aircon",
                    ATTR_ENTITY_ID: "switch.schedule_276b13",
                    const.ATTR_SOURCE: "timeslot at 21:00",
                },
                "context_id": "context-id",
            },
        )()
    )

    assert description == {
        "name": "Scheduler -> Turn Off Aircon",
        "message": "triggered by timeslot at 21:00",
        "source": "timeslot at 21:00",
        "entity_id": "switch.schedule_276b13",
        "context_id": "context-id",
    }
