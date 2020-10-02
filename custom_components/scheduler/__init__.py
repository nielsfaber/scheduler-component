"""The Scheduler Integration."""
import logging
from datetime import timedelta

from homeassistant.components.switch import DOMAIN as PLATFORM
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, asyncio
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import service
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, SCHEMA_ADD, SERVICE_ADD, SUN_ENTITY, VERSION

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=30)


async def async_setup(hass, config):
    """Track states and offer events for sensors."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Scheduler integration from a config entry."""
    session = async_get_clientsession(hass)

    coordinator = SchedulerCoordinator(hass, session, entry)

    device_registry = await dr.async_get_registry(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, coordinator.id)},
        name="Scheduler",
        model="Scheduler",
        sw_version=VERSION,
        manufacturer="@nielsfaber",
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    if entry.unique_id is None:
        hass.config_entries.async_update_entry(entry, unique_id=coordinator.id)

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, PLATFORM)
    )

    async def async_service_add(data):
        # TODO: add validation

        await coordinator.add_entity(data.data)

    service.async_register_admin_service(
        hass, DOMAIN, SERVICE_ADD, async_service_add, SCHEMA_ADD
    )

    return True


async def async_unload_entry(hass, entry):
    """Unload Scheduler config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[hass.config_entries.async_forward_entry_unload(entry, PLATFORM)]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class SchedulerCoordinator(DataUpdateCoordinator):
    """Define an object to hold scheduler data."""

    def __init__(self, hass, session, entry):
        """Initialize."""
        self.id = entry.unique_id
        self.hass = hass
        self.sun_data = None
        self._sun_listeners = []

        super().__init__(hass, _LOGGER, name=DOMAIN)

        async def async_sun_updated(entity, old_state, new_state):

            for item in self._sun_listeners:
                await item(self.sun_data)

        sun_state = self.hass.states.get(SUN_ENTITY)
        if sun_state:
            self.update_sun_data()
            async_track_state_change(hass, SUN_ENTITY, async_sun_updated)

    def update_sun_data(self):
        sun_state = self.hass.states.get(SUN_ENTITY)
        if sun_state:
            self.sun_data = {
                "sunrise": sun_state.attributes["next_rising"],
                "sunset": sun_state.attributes["next_setting"],
                "dawn": sun_state.attributes["next_dawn"],
                "dusk": sun_state.attributes["next_dusk"],
            }

    async def _async_update_data(self):
        """Update data via library."""
        return True

    async def add_entity(self, data):
        for item in self._listeners:
            item(data)

    def add_sun_listener(self, cb_func):
        self._sun_listeners.append(cb_func)
