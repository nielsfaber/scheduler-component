
"""The Scheduler Integration."""
import logging
import voluptuous as vol
import time
from homeassistant.helpers import config_validation as cv
from datetime import timedelta

import async_timeout
from homeassistant.components.switch import DOMAIN as PLATFORM

from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, asyncio
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import (
    config_validation as cv,
    service,
)
from .const import (
    SUN_ENTITY,
)

from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.device_registry import async_get_registry as get_device_registry
from homeassistant.helpers.entity_registry import async_get_registry as get_entity_registry

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=30)

DOMAIN = "scheduler"
SERVICE_ADD = "add"

SCHEMA_ADD = vol.Schema(
    {
        vol.Required("time"): cv.string,
        vol.Optional("days"): list,
        vol.Required("entity"): cv.entity_id,
        vol.Required("service"): cv.string,
        vol.Optional("service_data"): dict,
    }
)

async def async_setup(hass, config):
    """Track states and offer events for sensors."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Scheduler integration from a config entry."""
    session = async_get_clientsession(hass)

    coordinator = SchedulerCoordinator(hass, session, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    if entry.unique_id is None:
        hass.config_entries.async_update_entry(entry, unique_id=coordinator.id)

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, PLATFORM)
    )

    async def async_service_add(data):
        # TODO: add validation
        output = dict(data.data)
        output["enabled"] = True

        await coordinator.add_entity(data)

    service.async_register_admin_service(
        hass, DOMAIN, SERVICE_ADD, async_service_add, SCHEMA_ADD
    )

    return True


class SchedulerCoordinator(DataUpdateCoordinator):
    """Define an object to hold scheduler data."""

    def __init__(self, hass, session, entry):
        """Initialize."""
        super().__init__(
            hass, _LOGGER, name=DOMAIN
        )
        self.id = entry.unique_id
        self.hass = hass
        self.sun_data = {
            "sunrise": None,
            "sunset": None
        }

        self.update_sun_data()
    
    def update_sun_data(self):
        _LOGGER.debug("update_sun_data")
        sun_state = self.hass.states.get(SUN_ENTITY)
        self.sun_data["sunrise"] = sun_state.attributes["next_rising"]
        self.sun_data["sunset"] = sun_state.attributes["next_setting"]

    async def _async_update_data(self):
        """Update data via library."""
        _LOGGER.debug("_async_update_data")
        return True

    async def add_entity(self, data):
        for item in self._listeners:
            item(data.data)


    async def async_add_device(self):
        _LOGGER.debug("async_add_device")

        num = int(time.time()) 
        
        entity_registry = await get_entity_registry(self.hass)
        entity_registry.async_get_or_create(
            DOMAIN,
            "switch",
            "schedule_%i" % num,
        )

async def async_unload_entry(hass, entry):
    """Unload Scheduler config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, PLATFORM)
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
