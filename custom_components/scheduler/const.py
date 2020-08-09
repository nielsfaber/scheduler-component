
import voluptuous as vol
from homeassistant.helpers import (
    config_validation as cv,
)
from homeassistant.const import (
    ATTR_ENTITY_ID
)

DOMAIN = 'scheduler'
ENTITY_ID_FORMAT = DOMAIN + '.{}'



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


MQTT_DISCOVERY_RESPONSE_TOPIC = 'scheduler/+'
MQTT_DISCOVERY_REQUEST_TOPIC = 'scheduler/connect'
MQTT_AVAILABILITY_TOPIC = 'scheduler/status'
MQTT_ADD_TOPIC = 'scheduler/add'
MQTT_SUNRISE_TOPIC = 'scheduler/sunrise'
MQTT_SUNSET_TOPIC = 'scheduler/sunset'

def MQTT_TURN_ON_TOPIC(id):
     return 'scheduler/%s/turn_on' % id

def MQTT_TURN_OFF_TOPIC(id):
     return 'scheduler/%s/turn_off' % id

def MQTT_REMOVE_TOPIC(id):
     return 'scheduler/%s/remove' % id

def MQTT_EDIT_TOPIC(id):
     return 'scheduler/%s/edit' % id

def MQTT_INITIALIZATION_REQUEST_TOPIC(id):
     return 'scheduler/%s/discover' % id

def MQTT_INITIALIZATION_RESPONSE_TOPIC(id):
     return 'scheduler/%s/+' % id

MQTT_DISCOVERY_REQUEST_PAYLOAD = True
MQTT_AVAILABILITY_PAYLOAD = 'online'
MQTT_INITIALIZATION_REQUEST_PAYLOAD = True
MQTT_TURN_ON_PAYLOAD = True
MQTT_TURN_OFF_PAYLOAD = True
MQTT_REMOVE_PAYLOAD = True


STATE_INITIALIZING = 'initializing'
STATE_WAITING = 'waiting'
STATE_TRIGGERED = 'triggered'
STATE_DISABLED = 'off'
STATE_INVALID = 'invalid'

INITIAL_ENTITY_PROPERTIES = {
    "time": None,
    "days": None,
    "entity": None,
    "service": None,
    "enabled": False,
    "triggered": False,
}

LISTENING_ENTITY_PROPERTIES = [
    "time",
    "days",
    "entity",
    "service",
    "service_data",
    "enabled",
    "next_trigger",
    "triggered",
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
MQTT_SUNRISE_TOPIC = "scheduler/sunrise"
MQTT_SUNSET_TOPIC = "scheduler/sunset"