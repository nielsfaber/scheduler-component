"""Store constants."""
import voluptuous as vol
import re
import homeassistant.util.dt as dt_util
from homeassistant.helpers import config_validation as cv
from homeassistant.const import (
  ATTR_ENTITY_ID,
  SUN_EVENT_SUNRISE,
  SUN_EVENT_SUNSET
)

VERSION = "3.0.3"

DOMAIN = "scheduler"
ENTITY_ID_FORMAT = DOMAIN + ".{}"

SUN_ENTITY = "sun.sun"

DAY_TYPE_DAILY = "daily"
DAY_TYPE_WORKDAY = "workday"
DAY_TYPE_WEEKEND = "weekend"

WORKDAY_ENTITY = "binary_sensor.workday_sensor"

CONDITION_TYPE_AND = "and"
CONDITION_TYPE_OR = "or"

MATCH_TYPE_EQUAL = "is"
MATCH_TYPE_UNEQUAL = "not"
MATCH_TYPE_BELOW = "below"
MATCH_TYPE_ABOVE = "above"

REPEAT_TYPE_REPEAT = "repeat"
REPEAT_TYPE_SINGLE = "single"
REPEAT_TYPE_PAUSE = "pause"

EVENT = "scheduler_updated"

SERVICE_REMOVE = "remove"
SERVICE_EDIT = "edit"
SERVICE_ADD = "add"

OffsetTimePattern = re.compile("^([a-z]+)([-|\+]{1})([0-9:]+)$")


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
