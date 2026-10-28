"""Describe Scheduler events for the Home Assistant Logbook."""

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_CONTEXT_ID,
    LOGBOOK_ENTRY_ENTITY_ID,
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
    LOGBOOK_ENTRY_SOURCE,
    LazyEventPartialState,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_NAME
from homeassistant.core import HomeAssistant, callback

from . import const


@callback
def async_describe_events(hass: HomeAssistant, async_describe_event):
    """Describe Scheduler trigger events."""

    @callback
    def async_describe_logbook_event(event: LazyEventPartialState):
        """Describe a Scheduler trigger event."""
        data = event.data
        source = data.get(const.ATTR_SOURCE)
        message = "triggered"
        if source:
            message = f"{message} by {source}"

        return {
            LOGBOOK_ENTRY_NAME: f"Scheduler -> {data.get(ATTR_NAME)}",
            LOGBOOK_ENTRY_MESSAGE: message,
            LOGBOOK_ENTRY_SOURCE: source,
            LOGBOOK_ENTRY_ENTITY_ID: data.get(ATTR_ENTITY_ID),
            LOGBOOK_ENTRY_CONTEXT_ID: event.context_id,
        }

    async_describe_event(
        const.DOMAIN,
        const.EVENT_SCHEDULE_TRIGGERED,
        async_describe_logbook_event,
    )
