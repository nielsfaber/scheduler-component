"""Initialization of Scheduler switch platform."""
from homeassistant.const import (
    DEVICE_CLASS_PRESSURE,
    DEVICE_CLASS_TEMPERATURE,
    PRESSURE_BAR,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
    TIME_HOURS,
    UNIT_PERCENTAGE,
)
import logging
import secrets

from homeassistant.helpers.entity import ToggleEntity
import time
import asyncio

from homeassistant.components.switch import DOMAIN as PLATFORM

from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity_registry import async_entries_for_device
from homeassistant.helpers.device_registry import async_entries_for_config_entry
from homeassistant.helpers.entity_component import EntityComponent
from .datacollection import DataCollection


DOMAIN = "scheduler"

_LOGGER = logging.getLogger(__name__)
SENSORS = {
    "Outside Temperature": "outside_temp",
}


def entity_exists_in_hass(hass, entity_id):
    if hass.states.get(entity_id) is None:
        return False
    else:
        return True

async def async_setup(hass, config):
    """Track states and offer events for binary sensors."""

    return True

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the light from config."""
    _LOGGER.debug("async_setup_platform")
    return True

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Scheduler switch devices. """
    _LOGGER.debug("async_setup_entry")

    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = []

    
    device_registry = await hass.helpers.device_registry.async_get_registry()
    entry = async_entries_for_config_entry(device_registry, config_entry.entry_id)

    if len(entry)>1:
        _LOGGER.error("Found multiple devices for integration")
        return False
    
    device = entry[0]

    entity_registry = await hass.helpers.entity_registry.async_get_registry()
    for entry in async_entries_for_device(entity_registry, device.id):
        entities.append(ScheduleEntity(coordinator, entry.unique_id))
    
    async_add_entities(entities)

    # callback from the gateway
    def async_add_switch(data):
        """Add switch for Scheduler."""

        """Generate a unique token"""
        token = secrets.token_hex(3)
        while entity_exists_in_hass(hass, "{}.schedule_{}".format(PLATFORM,token)):
            token = secrets.token_hex(3)

        datacollection = DataCollection()
        datacollection.import_from_service(data)

        async_add_entities([ScheduleEntity(coordinator, "schedule_{}".format(token), datacollection)])

    # We add a listener after fetching the data, so manually trigger listener
    coordinator.async_add_listener(async_add_switch)



class ScheduleEntity(RestoreEntity, ToggleEntity):
    """Defines a base schedule entity."""

    def __init__(self, coordinator, entity_id: str, data: DataCollection = None) -> None:
        """Initialize the schedule entity."""
        self.coordinator = coordinator
        self.entity_id = "{}.{}".format(PLATFORM,entity_id)
        self.id = entity_id
        self._name = DOMAIN.title()
        self._data = data
        self._state = "my state"


    @property
    def device_info(self) -> dict:
        """Return info for device registry."""
        device = self.coordinator.id
        return {
            "identifiers": {(DOMAIN, device)},
            "name": "Scheduler",
            "model": "Scheduler",
            "sw_version": "v1",
            "manufacturer": "@nielsfaber",
        }

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def should_poll(self) -> bool:
        """Return the polling requirement of the entity."""
        return False


    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def icon(self):
        """Return icon."""
        return "mdi:home"


    @property
    def state_attributes(self):
        """Return the state of the sensor."""
        return self._data.export_data()


    @property
    def available(self):
        """Return True if entity is available."""
        return True

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{self.id}"

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        await super().async_added_to_hass()

        state = await self.async_get_last_state()

        # Check against None because value can be 0
        if state is not None:
            self._state = state.state
            data = DataCollection()
            data.import_data(state.attributes)            
            self._data = data
            
            
        

    async def async_update(self):
        """Update Scheduler entity."""
        _LOGGER.debug("async_update")
        await self.coordinator.async_request_refresh()
