import logging

import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.data_validator import RequestDataValidator
from homeassistant.core import callback
from homeassistant.components.websocket_api import decorators, async_register_command
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from . import const
from .store import ScheduleEntry

_LOGGER = logging.getLogger(__name__)


class SchedulesAddView(HomeAssistantView):
    """Login to Home Assistant cloud."""

    url = "/api/{}/add".format(const.DOMAIN)
    name = "api:{}:add".format(const.DOMAIN)

    @RequestDataValidator(const.ADD_SCHEDULE_SCHEMA)
    async def post(self, request, data):
        """Handle config update request."""
        hass = request.app["hass"]
        coordinator = hass.data[const.DOMAIN]["coordinator"]
        coordinator.async_create_schedule(data)
        return self.json({"success": True})


class SchedulesEditView(HomeAssistantView):
    """Login to Home Assistant cloud."""

    url = "/api/{}/edit".format(const.DOMAIN)
    name = "api:{}:edit".format(const.DOMAIN)

    @RequestDataValidator(
        const.EDIT_SCHEDULE_SCHEMA.extend(
            {vol.Required(const.ATTR_SCHEDULE_ID): cv.string}
        )
    )
    async def post(self, request, data):
        """Handle config update request."""
        hass = request.app["hass"]
        coordinator = hass.data[const.DOMAIN]["coordinator"]
        schedule_id = data[const.ATTR_SCHEDULE_ID]
        del data[const.ATTR_SCHEDULE_ID]
        await coordinator.async_edit_schedule(schedule_id, data)
        return self.json({"success": True})


class SchedulesRemoveView(HomeAssistantView):
    """Login to Home Assistant cloud."""

    url = "/api/{}/remove".format(const.DOMAIN)
    name = "api:{}:remove".format(const.DOMAIN)

    @RequestDataValidator(vol.Schema({vol.Required(const.ATTR_SCHEDULE_ID): cv.string}))
    async def post(self, request, data):
        """Handle config update request."""
        hass = request.app["hass"]
        coordinator = hass.data[const.DOMAIN]["coordinator"]
        await coordinator.async_delete_schedule(data[const.ATTR_SCHEDULE_ID])
        return self.json({"success": True})


@callback
def websocket_get_schedules(hass, connection, msg):
    """Publish scheduler list data."""
    coordinator = hass.data[const.DOMAIN]["coordinator"]
    schedules = coordinator.async_get_schedules()
    connection.send_result(msg["id"], schedules)


@callback
def websocket_get_schedule_item(hass, connection, msg):
    """Publish scheduler list data."""
    coordinator = hass.data[const.DOMAIN]["coordinator"]
    item = msg[const.ATTR_SCHEDULE_ID]
    data = coordinator.async_get_schedule(item)
    connection.send_result(msg["id"], data)


@callback
def websocket_get_tags(hass, connection, msg):
    """Publish tag list data."""
    coordinator = hass.data[const.DOMAIN]["coordinator"]
    tags = coordinator.async_get_tags()
    connection.send_result(msg["id"], tags)


@callback
@decorators.websocket_command(
    {
        vol.Required("type"): const.EVENT,
    }
)
@decorators.async_response
async def handle_subscribe_updates(hass, connection, msg):
    """subscribe listeners when frontend connection is opened"""

    listeners = []

    @callback
    def async_handle_event_item_created(schedule: ScheduleEntry):
        """pass data to frontend when backend changes"""
        connection.send_message(
            {
                "id": msg["id"],
                "type": "event",
                "event": {  # data to pass with event
                    "event": const.EVENT_ITEM_CREATED,
                    "schedule_id": schedule.schedule_id,
                },
            }
        )

    listeners.append(
        async_dispatcher_connect(
            hass, const.EVENT_ITEM_CREATED, async_handle_event_item_created
        )
    )

    @callback
    def async_handle_event_item_updated(schedule_id: str):
        """pass data to frontend when backend changes"""
        connection.send_message(
            {
                "id": msg["id"],
                "type": "event",
                "event": {  # data to pass with event
                    "event": const.EVENT_ITEM_UPDATED,
                    "schedule_id": schedule_id,
                },
            }
        )

    listeners.append(
        async_dispatcher_connect(
            hass, const.EVENT_ITEM_UPDATED, async_handle_event_item_updated
        )
    )

    @callback
    def async_handle_event_item_removed(schedule_id: str):
        """pass data to frontend when backend changes"""
        connection.send_message(
            {
                "id": msg["id"],
                "type": "event",
                "event": {  # data to pass with event
                    "event": const.EVENT_ITEM_REMOVED,
                    "schedule_id": schedule_id,
                },
            }
        )

    listeners.append(
        async_dispatcher_connect(
            hass, const.EVENT_ITEM_REMOVED, async_handle_event_item_removed
        )
    )

    @callback
    def async_handle_event_timer_updated(schedule_id: str):
        """pass data to frontend when backend changes"""
        connection.send_message(
            {
                "id": msg["id"],
                "type": "event",
                "event": {  # data to pass with event
                    "event": const.EVENT_TIMER_UPDATED,
                    "schedule_id": schedule_id,
                },
            }
        )

    listeners.append(
        async_dispatcher_connect(
            hass, const.EVENT_TIMER_UPDATED, async_handle_event_timer_updated
        )
    )

    @callback
    def async_handle_event_timer_finished(schedule_id: str):
        """pass data to frontend when backend changes"""
        connection.send_message(
            {
                "id": msg["id"],
                "type": "event",
                "event": {  # data to pass with event
                    "event": const.EVENT_TIMER_FINISHED,
                    "schedule_id": schedule_id,
                },
            }
        )

    listeners.append(
        async_dispatcher_connect(
            hass, const.EVENT_TIMER_FINISHED, async_handle_event_timer_finished
        )
    )

    def unsubscribe_listeners():
        """unsubscribe listeners when frontend connection closes"""
        while len(listeners):
            listeners.pop()()

    connection.subscriptions[msg["id"]] = unsubscribe_listeners
    connection.send_result(msg["id"])


async def async_register_websockets(hass):

    # expose services
    hass.http.register_view(SchedulesAddView)
    hass.http.register_view(SchedulesEditView)
    hass.http.register_view(SchedulesRemoveView)

    # pass list of schedules to frontend
    hass.components.websocket_api.async_register_command(
        const.DOMAIN,
        websocket_get_schedules,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): const.DOMAIN,
            }
        ),
    )

    # pass single schedule to frontend
    hass.components.websocket_api.async_register_command(
        "{}/item".format(const.DOMAIN),
        websocket_get_schedule_item,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): "{}/item".format(const.DOMAIN),
                vol.Required(const.ATTR_SCHEDULE_ID): cv.string,
            }
        ),
    )

    # pass list of tags to frontend
    hass.components.websocket_api.async_register_command(
        "{}/tags".format(const.DOMAIN),
        websocket_get_tags,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): "{}/tags".format(const.DOMAIN),
            }
        ),
    )

    # instantiate listener for sending event to frontend on backend change
    async_register_command(hass, handle_subscribe_updates)
