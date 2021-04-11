"""Store constants."""
import voluptuous as vol
import re
import homeassistant.util.dt as dt_util
from homeassistant.helpers import config_validation as cv
from homeassistant.const import (
    WEEKDAYS,
    ATTR_ENTITY_ID,
    SUN_EVENT_SUNRISE,
    SUN_EVENT_SUNSET,
    ATTR_SERVICE,
    ATTR_SERVICE_DATA,
    CONF_CONDITIONS,
    CONF_ATTRIBUTE,
    ATTR_NAME,
)

VERSION = "3.1.0b"

DOMAIN = "scheduler"

SUN_ENTITY = "sun.sun"

DAY_TYPE_DAILY = "daily"
DAY_TYPE_WORKDAY = "workday"
DAY_TYPE_WEEKEND = "weekend"

WORKDAY_ENTITY = "binary_sensor.workday_sensor"

ATTR_CONDITION_TYPE = "condition_type"
CONDITION_TYPE_AND = "and"
CONDITION_TYPE_OR = "or"

ATTR_MATCH_TYPE = "match_type"
MATCH_TYPE_EQUAL = "is"
MATCH_TYPE_UNEQUAL = "not"
MATCH_TYPE_BELOW = "below"
MATCH_TYPE_ABOVE = "above"

ATTR_REPEAT_TYPE = "repeat_type"
REPEAT_TYPE_REPEAT = "repeat"
REPEAT_TYPE_SINGLE = "single"
REPEAT_TYPE_PAUSE = "pause"

EVENT = "scheduler_updated"

SERVICE_REMOVE = "remove"
SERVICE_EDIT = "edit"
SERVICE_ADD = "add"

OffsetTimePattern = re.compile("^([a-z]+)([-|\+]{1})([0-9:]+)$")

ATTR_START = "start"
ATTR_STOP = "stop"
ATTR_TIMESLOTS = "timeslots"
ATTR_WEEKDAYS = "weekdays"
ATTR_ENABLED = "enabled"
ATTR_SCHEDULE_ID = "schedule_id"
ATTR_ACTIONS = "actions"
ATTR_VALUE = "value"

EVENT_TIMER_FINISHED = "scheduler_timer_finished"
EVENT_TIMER_UPDATED = "scheduler_timer_updated"
EVENT_ITEM_UPDATED = "scheduler_item_updated"
EVENT_ITEM_CREATED = "scheduler_item_created"
EVENT_STARTED = "scheduler_started"

STATE_INIT = "init"
STATE_READY = "ready"


def validate_time(time):
    res = OffsetTimePattern.match(time)
    if not res:
        if dt_util.parse_time(time):
            return time
        else:
            raise vol.Invalid("Invalid time entered: {}".format(time))
    else:
        if res.group(1) not in [SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET]:
            raise vol.Invalid("Invalid time entered: {}".format(time))
        elif res.group(2) not in ['+', '-']:
            raise vol.Invalid("Invalid time entered: {}".format(time))
        elif not dt_util.parse_time(res.group(3)):
            raise vol.Invalid("Invalid time entered: {}".format(time))
        else:
            return time


CONDITION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_VALUE): vol.Any(int, float, str),
        vol.Optional(CONF_ATTRIBUTE): cv.string,
        vol.Required(ATTR_MATCH_TYPE): vol.In(
            [
                MATCH_TYPE_EQUAL,
                MATCH_TYPE_UNEQUAL,
                MATCH_TYPE_BELOW,
                MATCH_TYPE_ABOVE
            ]
        ),
    }
)

ACTION_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_SERVICE): cv.entity_id,
        vol.Optional(ATTR_SERVICE_DATA): dict,
    }
)

TIMESLOT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_START): validate_time,
        vol.Optional(ATTR_STOP): validate_time,
        vol.Optional(CONF_CONDITIONS): vol.All(
            cv.ensure_list, vol.Length(min=1), [CONDITION_SCHEMA]
        ),
        vol.Optional(ATTR_CONDITION_TYPE): vol.In(
            [
                CONDITION_TYPE_AND,
                CONDITION_TYPE_OR,
            ]
        ),
        vol.Required(ATTR_ACTIONS): vol.All(
            cv.ensure_list, vol.Length(min=1), [ACTION_SCHEMA]
        ),
    }
)

SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_WEEKDAYS): vol.All(
            cv.ensure_list,
            vol.Unique(),
            vol.Length(min=1),
            [
                vol.In(
                    WEEKDAYS + [
                        DAY_TYPE_WORKDAY,
                        DAY_TYPE_WEEKEND,
                        DAY_TYPE_DAILY,
                    ]
                )
            ],
        ),
        vol.Required(ATTR_TIMESLOTS): vol.All(
            cv.ensure_list, vol.Length(min=1), [TIMESLOT_SCHEMA]
        ),
        vol.Required(ATTR_REPEAT_TYPE): vol.In(
            [
                REPEAT_TYPE_REPEAT,
                REPEAT_TYPE_SINGLE,
                REPEAT_TYPE_PAUSE,
            ]
        ),
        vol.Optional(ATTR_NAME): vol.Any(cv.string, None),
    }
)
