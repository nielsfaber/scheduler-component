"""Store constants."""
import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import config_validation as cv

VERSION = "2.1.0"

DOMAIN = "scheduler"
ENTITY_ID_FORMAT = DOMAIN + ".{}"
# STORAGE_KEY = DOMAIN
# STORAGE_VERSION = 1

SERVICE_TURN_ON = "turn_on"
SERVICE_TURN_OFF = "turn_off"
SERVICE_TEST = "test"
SERVICE_REMOVE = "remove"
SERVICE_EDIT = "edit"
SERVICE_ADD = "add"

STATE_INITIALIZING = "initializing"
STATE_WAITING = "waiting"
STATE_TRIGGERED = "triggered"
STATE_DISABLED = "off"
STATE_INVALID = "invalid"

SUN_ENTITY = "sun.sun"

TIME_EVENT_SUNRISE = "sunrise"
TIME_EVENT_SUNSET = "sunset"
TIME_EVENT_DAWN = "dawn"
TIME_EVENT_DUSK = "dusk"

ENTRY_PATTERN_SUNRISE = "SR"
ENTRY_PATTERN_SUNSET = "SS"
ENTRY_PATTERN_DAWN = "DW"
ENTRY_PATTERN_DUSK = "DU"

DAY_TYPE_DAILY = "daily"
DAY_TYPE_WORKDAY = "workday"
DAY_TYPE_WEEKEND = "weekend"
DAY_TYPE_CUSTOM = "custom"

ENTRY_PATTERN_DAILY = "0"
ENTRY_PATTERN_WORKDAY = "15"
ENTRY_PATTERN_WEEKEND = "67"

WORKDAY_ENTITY = "binary_sensor.workday_sensor"

FIXED_TIME_ENTRY_SCHEMA = cv.time

SUN_TIME_ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required("event"): vol.In([TIME_EVENT_SUNRISE, TIME_EVENT_SUNSET, TIME_EVENT_DAWN, TIME_EVENT_DUSK]),
        vol.Optional("offset"): cv.time_period_str,
    }
)

ENTRY_SCHEMA = vol.Any(FIXED_TIME_ENTRY_SCHEMA, SUN_TIME_ENTRY_SCHEMA)

DAYS_SCHEMA = vol.Schema(
    {
        vol.Required("type"): vol.In([DAY_TYPE_DAILY, DAY_TYPE_WORKDAY, DAY_TYPE_WEEKEND, DAY_TYPE_CUSTOM]),
        vol.Optional("list"): vol.All(
            cv.ensure_list,
            vol.Unique(),
            vol.Length(min=1),
            [vol.All(int, vol.Range(min=0))],
        ),
    }
)

ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required("time"): vol.Any(FIXED_TIME_ENTRY_SCHEMA, SUN_TIME_ENTRY_SCHEMA),
        vol.Optional("end_time"): vol.Any(
            FIXED_TIME_ENTRY_SCHEMA, SUN_TIME_ENTRY_SCHEMA
        ),
        vol.Optional("days"): DAYS_SCHEMA,
        vol.Required("actions"): vol.All(
            cv.ensure_list,
            vol.Unique(),
            vol.Length(min=1),
            [vol.All(int, vol.Range(min=0))],
        ),
    }
)


ACTION_SCHEMA = vol.Schema(
    {
        vol.Required("service"): cv.string,
        vol.Optional("entity"): cv.entity_id,
        vol.Optional("service_data"): dict,
    }
)

SCHEMA_ADD = vol.Schema(
    {
        vol.Required("entries"): vol.All(
            cv.ensure_list, vol.Length(min=1), [ENTRY_SCHEMA]
        ),
        vol.Required("actions"): vol.All(
            cv.ensure_list, vol.Length(min=1), [ACTION_SCHEMA]
        ),
        vol.Optional("name"): cv.string,
    }
)

SCHEMA_ENTITY = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_ids})

SCHEMA_EDIT = SCHEMA_ADD.extend({vol.Required(ATTR_ENTITY_ID): cv.entity_ids})

SCHEMA_TEST = SCHEMA_ENTITY.extend(
    {vol.Optional("entries"): vol.All(int, vol.Range(min=0))}
)
