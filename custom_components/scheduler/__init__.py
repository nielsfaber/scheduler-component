"""The Scheduler Integration."""
import logging
from datetime import timedelta

from homeassistant.components.switch import DOMAIN as PLATFORM
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED 
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, asyncio
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import service
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import (async_track_state_change, async_call_later)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    SCHEMA_ADD,
    SERVICE_ADD,
    SUN_ENTITY,
    TIME_EVENT_DAWN,
    TIME_EVENT_DUSK,
    TIME_EVENT_SUNRISE,
    TIME_EVENT_SUNSET,
    VERSION,
    WORKDAY_ENTITY,
)
from .helpers import convert_days_to_numbers

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
        self.workday_data = None
        self._sun_listeners = []
        self._workday_listeners = []
        self._startup_listeners = []
        self.is_started = False

        super().__init__(hass, _LOGGER, name=DOMAIN)
        
        async_track_state_change(self.hass, SUN_ENTITY, self.async_sun_updated)
        async_track_state_change(self.hass, WORKDAY_ENTITY, self.async_workday_updated)

        self.update_sun_data()
        self.update_workday_data()

        def handle_startup(event):
            hass.add_job(
                async_call_later,
                self.hass,
                5,
                self.async_start_schedules,
            )
        hass.bus.async_listen(EVENT_HOMEASSISTANT_STARTED, handle_startup)

    async def async_start_schedules(self, _=None):
        if self.is_started:
            return
        self.is_started = True
        _LOGGER.debug("Scheduler coordinator is ready")
        while len(self._startup_listeners):
            await self._startup_listeners.pop()()
    
    def check_ready(self):
        if not self.sun_data or not self.workday_data:
            return
        elif not self.is_started:
            self.hass.add_job(
                self.async_start_schedules
            )

    async def async_sun_updated(self, entity, old_state, new_state):
        self.update_sun_data()
        if self.sun_data:
            for item in self._sun_listeners:
                await item(self.sun_data)

    def update_sun_data(self):
        sun_state = self.hass.states.get(SUN_ENTITY)
        if not sun_state:
            return

        sun_data = {
            TIME_EVENT_SUNRISE: sun_state.attributes["next_rising"],
            TIME_EVENT_SUNSET: sun_state.attributes["next_setting"],
            TIME_EVENT_DAWN: sun_state.attributes["next_dawn"],
            TIME_EVENT_DUSK: sun_state.attributes["next_dusk"],
        }
        if not self.sun_data:
            self.sun_data = sun_data
            self.check_ready()
        else:
            self.sun_data = sun_data
    
    async def async_workday_updated(self, entity, old_state, new_state):
        _LOGGER.debug("-----------")
        self.update_workday_data()
        if self.workday_data:
            for item in self._workday_listeners:
                await item(self.workday_data)

    def update_workday_data(self):
        workday_state = self.hass.states.get(WORKDAY_ENTITY)
        if not workday_state:
            return

        workday_data = {
            "workdays": convert_days_to_numbers(workday_state.attributes["workdays"]),
            "today_is_workday": (workday_state.state == "on"),
        }
        _LOGGER.debug(workday_data)
        if not self.workday_data:
            self.workday_data = workday_data
            self.check_ready()
        else:
            self.workday_data = workday_data

    async def _async_update_data(self):
        """Update data via library."""
        return True

    async def add_entity(self, data):
        for item in self._listeners:
            item(data)

    def add_sun_listener(self, cb_func):
        self._sun_listeners.append(cb_func)

    def add_workday_listener(self, cb_func):
        self._workday_listeners.append(cb_func)

    def add_startup_listener(self, cb_func):
        self._startup_listeners.append(cb_func)

    async def async_request_state(self, entity_id):
        state = self.hass.states.get(entity_id)
        if state:
            return state.state
        return None
