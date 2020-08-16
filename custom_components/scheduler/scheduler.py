"""Handle the scheduler domain."""
import logging

from .const import (
    DOMAIN,
    EXPOSED_ENTITY_PROPERTIES,
    INITIAL_ENTITY_PROPERTIES,
    LISTENING_ENTITY_PROPERTIES,
    MQTT_DISCOVERY_REQUEST_PAYLOAD,
    MQTT_DISCOVERY_REQUEST_TOPIC,
    MQTT_DISCOVERY_RESPONSE_TOPIC,
    MQTT_STORAGE_TOPIC,
    MQTT_SUNRISE_TOPIC,
    MQTT_SUNSET_TOPIC,
    SCHEMA_ADD,
    SCHEMA_EDIT,
    SCHEMA_ENTITY,
    SERVICE_ADD,
    SERVICE_EDIT,
    SERVICE_REMOVE,
    SERVICE_TEST,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_DISABLED,
    STATE_INITIALIZING,
    STATE_INVALID,
    STATE_TRIGGERED,
    STATE_WAITING,
    SUN_ENTITY,
)
from .helpers import entity_exists_in_hass, get_id_from_topic, service_exists_in_hass

# from homeassistant.helpers.entity import (
#     ToggleEntity,
#     Entity
# )


_LOGGER = logging.getLogger(__name__)

ENTITY_ID_FORMAT = DOMAIN + ".{}"
DEPENDENCIES = ["mqtt"]


async def async_setup(hass, config):
    """Placeholder for async setup function."""
    _LOGGER.debug("async_setup")

    return True


async def async_setup_platform(hass, config):
    """Placeholder for async setup platform function."""
    _LOGGER.debug("async_setup_platform")

    return True
