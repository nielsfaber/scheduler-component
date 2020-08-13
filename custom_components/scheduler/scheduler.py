import logging
import voluptuous as vol
import json
from homeassistant.helpers.json import JSONEncoder
from homeassistant.helpers.entity_component import EntityComponent

from homeassistant.util import convert, dt as dt_util, location as loc_util
from datetime import datetime
from homeassistant.helpers import (
    config_validation as cv,
    service,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers.event import async_track_state_change
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    STATE_INITIALIZING,
    STATE_WAITING,
    STATE_TRIGGERED,
    STATE_DISABLED,
    STATE_INVALID,
    SERVICE_TURN_ON,
    SERVICE_TURN_OFF,
    SERVICE_TEST,
    SERVICE_REMOVE,
    SERVICE_EDIT,
    SERVICE_ADD,
    SCHEMA_ENTITY,
    SCHEMA_EDIT,
    SCHEMA_ADD,
    MQTT_DISCOVERY_RESPONSE_TOPIC,
    MQTT_DISCOVERY_REQUEST_TOPIC,
    MQTT_DISCOVERY_REQUEST_PAYLOAD,
    MQTT_STORAGE_TOPIC,
    INITIAL_ENTITY_PROPERTIES,
    EXPOSED_ENTITY_PROPERTIES,
    LISTENING_ENTITY_PROPERTIES,
    SUN_ENTITY,
    MQTT_SUNRISE_TOPIC,
    MQTT_SUNSET_TOPIC,
)

from .helpers import (
    get_id_from_topic,
    entity_exists_in_hass,
    service_exists_in_hass,
)

_LOGGER = logging.getLogger(__name__)

ENTITY_ID_FORMAT = DOMAIN + ".{}"
DEPENDENCIES = ["mqtt"]


async def async_setup(hass, config):
    _LOGGER.debug("async_setup")

    return True


async def async_setup_platform(hass, config):
    _LOGGER.debug("async_setup_platform")

    return True
