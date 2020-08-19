"""Store constants."""
import voluptuous as vol, types
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import config_validation as cv

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

BASE_SCHEMA = types.MappingProxyType({vol.Optional("time"): cv.string, vol.Optional("days"): list})

SCHEMA_ENTITY = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_ids})

SCHEMA_EDIT = vol.Schema(
    {**BASE_SCHEMA, **{vol.Required(ATTR_ENTITY_ID): cv.entity_id}}
)

SCHEMA_ADD = vol.Schema(
    {
        **BASE_SCHEMA,
        **{
            vol.Required("entity"): cv.entity_id,
            vol.Required("service"): cv.string,
            vol.Optional("service_data"): dict,
        },
    }
)


MQTT_DISCOVERY_TOPIC = "scheduler/+"


def mqtt_storage_topic(mqtt_id):
    """Get the scheduler MQTT topic from an ID."""
    return f"scheduler/{mqtt_id}"


STATE_INITIALIZING = "initializing"
STATE_WAITING = "waiting"
STATE_TRIGGERED = "triggered"
STATE_DISABLED = "off"
STATE_INVALID = "invalid"


STORED_ENTITY_PROPERTIES = (
    "time",
    "days",
    "entity",
    "service",
    "service_data",
    "enabled",
)

EXPOSED_ENTITY_PROPERTIES = (
    "time",
    "days",
    "entity",
    "service",
    "service_data",
    "next_trigger",
)

SUN_ENTITY = "sun.sun"
