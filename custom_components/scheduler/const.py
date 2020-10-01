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

FIXED_TIME_ENTRY_SCHEMA = cv.time

SUN_TIME_ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required("event"): vol.In(["sunrise", "sunset", "dawn", "dusk"]),
        vol.Optional("offset"): cv.time_period_str,
    }
)

ENTRY_SCHEMA = vol.Any(FIXED_TIME_ENTRY_SCHEMA, SUN_TIME_ENTRY_SCHEMA)

ENTRY_SCHEMA = vol.Schema(
    {
        vol.Required("time"): vol.Any(FIXED_TIME_ENTRY_SCHEMA, SUN_TIME_ENTRY_SCHEMA),
        vol.Optional("end_time"): vol.Any(FIXED_TIME_ENTRY_SCHEMA, SUN_TIME_ENTRY_SCHEMA),
        vol.Optional("days"): vol.All(
            cv.ensure_list,
            vol.Unique(),
            vol.Length(min=1),
            [vol.All(int, vol.Range(min=1, max=7))],
        ),
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
        vol.Optional("name"): cv.string
    }
)

SCHEMA_ENTITY = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_ids})

SCHEMA_EDIT = SCHEMA_ADD.extend(
    {vol.Required(ATTR_ENTITY_ID): cv.entity_ids}
)

SCHEMA_TEST = SCHEMA_ENTITY.extend(
    {vol.Optional("entries"): vol.All(int, vol.Range(min=0))}
)


STATE_INITIALIZING = "initializing"
STATE_WAITING = "waiting"
STATE_TRIGGERED = "triggered"
STATE_DISABLED = "off"
STATE_INVALID = "invalid"

SUN_ENTITY = "sun.sun"
