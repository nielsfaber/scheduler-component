import logging

import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.data_validator import RequestDataValidator
from homeassistant.core import callback
from .helpers import validate_time

from .const import (
    DOMAIN,
    MATCH_TYPE_EQUAL,
    MATCH_TYPE_UNEQUAL,
    MATCH_TYPE_BELOW,
    MATCH_TYPE_ABOVE,
    CONDITION_TYPE_AND,
    CONDITION_TYPE_OR,
    DAY_TYPE_WORKDAY,
    DAY_TYPE_WEEKEND,
    DAY_TYPE_DAILY,
    REPEAT_TYPE_REPEAT,
    REPEAT_TYPE_SINGLE,
    REPEAT_TYPE_PAUSE,
)

_LOGGER = logging.getLogger(__name__)
EVENT = "schedules_updated"


CONDITION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required("value"): vol.Any(int, float, str),
        vol.Optional("attribute"): cv.string,
        vol.Required("match_type"): vol.In(
            [MATCH_TYPE_EQUAL, MATCH_TYPE_UNEQUAL, MATCH_TYPE_BELOW, MATCH_TYPE_ABOVE]
        ),
    }
)

ACTION_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
        vol.Optional("service"): cv.entity_id,
        vol.Optional("service_data"): dict,
    }
)

TIMESLOT_SCHEMA = vol.Schema(
    {
        vol.Required("start"): validate_time,
        vol.Optional("stop"): validate_time,
        vol.Optional("conditions"): vol.All(
            cv.ensure_list, vol.Length(min=1), [CONDITION_SCHEMA]
        ),
        vol.Optional("condition_type"): vol.In(
            [
                CONDITION_TYPE_AND,
                CONDITION_TYPE_OR,
            ]
        ),
        vol.Required("actions"): vol.All(
            cv.ensure_list, vol.Length(min=1), [ACTION_SCHEMA]
        ),
    }
)

SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("weekdays"): vol.All(
            cv.ensure_list,
            vol.Unique(),
            vol.Length(min=1),
            [
                vol.In(
                    [
                        "mon",
                        "tue",
                        "wed",
                        "thu",
                        "fri",
                        "sat",
                        "sun",
                        DAY_TYPE_WORKDAY,
                        DAY_TYPE_WEEKEND,
                        DAY_TYPE_DAILY,
                    ]
                )
            ],
        ),
        vol.Required("timeslots"): vol.All(
            cv.ensure_list, vol.Length(min=1), [TIMESLOT_SCHEMA]
        ),
        vol.Required("repeat_type"): vol.In(
            [
                REPEAT_TYPE_REPEAT,
                REPEAT_TYPE_SINGLE,
                REPEAT_TYPE_PAUSE,
            ]
        ),
        vol.Optional("name"): cv.string,
    }
)


class SchedulesAddView(HomeAssistantView):
    """Login to Home Assistant cloud."""

    url = "/api/scheduler/add"
    name = "api:scheduler:add"

    @RequestDataValidator(SCHEDULE_SCHEMA)
    async def post(self, request, data):
        """Handle config update request."""
        hass = request.app["hass"]
        coordinator = hass.data[DOMAIN]["coordinator"]
        coordinator.async_create_schedule(data)
        return self.json({"success": True})


class SchedulesEditView(HomeAssistantView):
    """Login to Home Assistant cloud."""

    url = "/api/scheduler/edit"
    name = "api:scheduler:edit"

    @RequestDataValidator(
        SCHEDULE_SCHEMA.extend({vol.Required("schedule_id"): cv.string})
    )
    async def post(self, request, data):
        """Handle config update request."""
        hass = request.app["hass"]
        coordinator = hass.data[DOMAIN]["coordinator"]
        schedule_id = data["schedule_id"]
        del data["schedule_id"]
        await coordinator.async_edit_schedule(schedule_id, data)
        return self.json({"success": True})


class SchedulesRemoveView(HomeAssistantView):
    """Login to Home Assistant cloud."""

    url = "/api/scheduler/remove"
    name = "api:scheduler:remove"

    @RequestDataValidator(vol.Schema({vol.Required("schedule_id"): cv.string}))
    async def post(self, request, data):
        """Handle config update request."""
        hass = request.app["hass"]
        coordinator = hass.data[DOMAIN]["coordinator"]
        await coordinator.async_delete_schedule(data["schedule_id"])
        return self.json({"success": True})


@callback
def websocket_get_schedules(hass, connection, msg):
    """Publish scheduler list data."""
    coordinator = hass.data[DOMAIN]["coordinator"]
    schedules = coordinator.async_get_schedules()
    connection.send_result(msg["id"], schedules)


@callback
def websocket_get_schedule_item(hass, connection, msg):
    """Publish scheduler list data."""
    coordinator = hass.data[DOMAIN]["coordinator"]
    item = msg["schedule_id"]
    data = coordinator.async_get_schedule(item)
    connection.send_result(msg["id"], data)


async def async_register_websockets(hass):

    hass.http.register_view(SchedulesAddView)
    hass.http.register_view(SchedulesEditView)
    hass.http.register_view(SchedulesRemoveView)

    hass.components.websocket_api.async_register_command(
        "scheduler",
        websocket_get_schedules,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {vol.Required("type"): "scheduler"}
        ),
    )

    hass.components.websocket_api.async_register_command(
        "scheduler/item",
        websocket_get_schedule_item,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): "scheduler/item",
                vol.Required("schedule_id"): cv.string,
            }
        ),
    )
