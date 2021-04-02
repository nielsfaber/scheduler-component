import logging

import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.data_validator import RequestDataValidator
from homeassistant.core import callback

from . import const

_LOGGER = logging.getLogger(__name__)


class SchedulesAddView(HomeAssistantView):
    """Login to Home Assistant cloud."""

    url = "/api/{}/add".format(const.DOMAIN)
    name = "api:{}:add".format(const.DOMAIN)

    @RequestDataValidator(const.SCHEDULE_SCHEMA)
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
        const.SCHEDULE_SCHEMA.extend(
            {
                vol.Required(const.ATTR_SCHEDULE_ID): cv.string
            }
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

    @RequestDataValidator(
        vol.Schema(
            {
                vol.Required(const.ATTR_SCHEDULE_ID): cv.string
            }
        )
    )
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


async def async_register_websockets(hass):

    hass.http.register_view(SchedulesAddView)
    hass.http.register_view(SchedulesEditView)
    hass.http.register_view(SchedulesRemoveView)

    hass.components.websocket_api.async_register_command(
        const.DOMAIN,
        websocket_get_schedules,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): const.DOMAIN,
            }
        ),
    )

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
