
import voluptuous as vol
from homeassistant.helpers import (
    config_validation as cv,
)
from homeassistant.const import (
    ATTR_ENTITY_ID
)

DOMAIN = 'scheduler'
ENTITY_ID_FORMAT = DOMAIN + '.{}'

# STORAGE_KEY = DOMAIN
# STORAGE_VERSION = 1

SERVICE_TURN_ON = 'turn_on'
SERVICE_TURN_OFF = 'turn_off'
SERVICE_TEST = 'test'
SERVICE_REMOVE = 'remove'
SERVICE_EDIT = 'edit'
SERVICE_ADD = 'add'


SCHEMA_ENTITY = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_ids
})

SCHEMA_EDIT = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    vol.Optional('time'): cv.string,
    vol.Optional('days'): list,
})

SCHEMA_ADD = vol.Schema({
    vol.Required('time'): cv.string,
    vol.Optional('days'): list,
    vol.Required('entity'): cv.entity_id,
    vol.Required('service'): cv.string,
    vol.Optional('service_data'): dict,
})


MQTT_DISCOVERY_TOPIC = 'scheduler/+'


def MQTT_STORAGE_TOPIC(id):
     return 'scheduler/%s' % id



STATE_INITIALIZING = 'initializing'
STATE_WAITING = 'waiting'
STATE_TRIGGERED = 'triggered'
STATE_DISABLED = 'off'
STATE_INVALID = 'invalid'


STORED_ENTITY_PROPERTIES = [
    "time",
    "days",
    "entity",
    "service",
    "service_data",
    "enabled",
]

EXPOSED_ENTITY_PROPERTIES = [
    "time",
    "days",
    "entity",
    "service",
    "service_data",
    "next_trigger",
]

SUN_ENTITY = "sun.sun"