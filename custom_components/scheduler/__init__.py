"""The Scheduler Integration."""
import logging
import voluptuous as vol
import datetime
import homeassistant.util.dt as dt_util

from homeassistant.helpers import config_validation as cv
from homeassistant.components.switch import DOMAIN as PLATFORM
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_HOMEASSISTANT_STOP,
    ATTR_ENTITY_ID,
    ATTR_NAME,
)
from homeassistant.core import HomeAssistant, asyncio, CoreState, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_registry import async_get as get_entity_registry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.dispatcher import (
    async_dispatcher_send,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_point_in_time,
)

from . import const
from .store import async_get_registry
from .websockets import async_register_websockets

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass, config):
    """Track states and offer events for sensors."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Scheduler integration from a config entry."""
    session = async_get_clientsession(hass)
    store = await async_get_registry(hass)
    coordinator = SchedulerCoordinator(hass, session, entry, store)

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(const.DOMAIN, coordinator.id)},
        name="Scheduler",
        model="Scheduler",
        sw_version=const.VERSION,
        manufacturer="@nielsfaber",
    )

    hass.data.setdefault(const.DOMAIN, {})
    hass.data[const.DOMAIN] = {"coordinator": coordinator, "schedules": {}}

    if entry.unique_id is None:
        hass.config_entries.async_update_entry(entry, unique_id=coordinator.id)

    await hass.config_entries.async_forward_entry_setups(entry, [PLATFORM])

    await async_register_websockets(hass)

    @callback
    def service_create_schedule(service):
        coordinator.async_create_schedule(dict(service.data))

    hass.services.async_register(
        const.DOMAIN,
        const.SERVICE_ADD,
        service_create_schedule,
        schema=const.ADD_SCHEDULE_SCHEMA,
    )

    @callback
    def async_service_edit_schedule(service):
        match = None
        for (schedule_id, entity) in hass.data[const.DOMAIN]["schedules"].items():
            if entity.entity_id == service.data[const.ATTR_ENTITY_ID]:
                match = schedule_id
                continue
        if not match:
            raise vol.Invalid(
                "Entity not found: {}".format(service.data[const.ATTR_ENTITY_ID])
            )
        else:
            data = dict(service.data)
            del data[const.ATTR_ENTITY_ID]
            coordinator.async_edit_schedule(match, data)

    hass.services.async_register(
        const.DOMAIN,
        const.SERVICE_EDIT,
        async_service_edit_schedule,
        schema=const.EDIT_SCHEDULE_SCHEMA.extend(
            {vol.Required(ATTR_ENTITY_ID): cv.string}
        ),
    )

    @callback
    def async_service_remove_schedule(service):
        match = None
        for (schedule_id, entity) in hass.data[const.DOMAIN]["schedules"].items():
            if entity.entity_id == service.data["entity_id"]:
                match = schedule_id
                continue
        if not match:
            raise vol.Invalid("Entity not found: {}".format(service.data["entity_id"]))
        else:
            coordinator.async_delete_schedule(match)

    hass.services.async_register(
        const.DOMAIN,
        const.SERVICE_REMOVE,
        async_service_remove_schedule,
        schema=vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.string}),
    )

    @callback
    def service_copy_schedule(service):
        match = None
        for (schedule_id, entity) in hass.data[const.DOMAIN]["schedules"].items():
            if entity.entity_id == service.data[const.ATTR_ENTITY_ID]:
                match = schedule_id
                continue
        if not match:
            raise vol.Invalid(
                "Entity not found: {}".format(service.data[const.ATTR_ENTITY_ID])
            )
        else:
            data = store.async_get_schedule(match)
            tags = coordinator.async_get_tags_for_schedule(data[const.ATTR_SCHEDULE_ID])
            if tags:
                data[const.ATTR_TAGS] = tags
            del data[const.ATTR_SCHEDULE_ID]
            if ATTR_NAME in service.data:
                data[ATTR_NAME] = service.data[ATTR_NAME].strip()
            coordinator.async_create_schedule(data)

    hass.services.async_register(
        const.DOMAIN,
        const.SERVICE_COPY,
        service_copy_schedule,
        schema=vol.Schema(
            {
                vol.Required(ATTR_ENTITY_ID): cv.string,
                vol.Optional(ATTR_NAME): vol.Any(cv.string, None),
            }
        ),
    )

    async def async_service_disable_all(service):
        await coordinator.async_disable_all_schedules()

    hass.services.async_register(
        const.DOMAIN,
        const.SERVICE_DISABLE_ALL,
        async_service_disable_all
    )

    async def async_service_enable_all(service):
        await coordinator.async_enable_all_schedules()

    hass.services.async_register(
        const.DOMAIN,
        const.SERVICE_ENABLE_ALL,
        async_service_enable_all
    )

    return True


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        config_entry.version = 2
        config_entry.data = {"migrate_entities": True}

    return True


async def async_unload_entry(hass, entry):
    """Unload Scheduler config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[hass.config_entries.async_forward_entry_unload(entry, PLATFORM)]
        )
    )
    coordinator = hass.data[const.DOMAIN]["coordinator"]
    await coordinator.async_unload()
    return unload_ok


async def async_remove_entry(hass, entry):
    """Remove Scheduler data."""
    coordinator = hass.data[const.DOMAIN]["coordinator"]
    await coordinator.async_delete_config()
    del hass.data[const.DOMAIN]


class SchedulerCoordinator(DataUpdateCoordinator):
    """Define an object to hold scheduler data."""

    def __init__(self, hass, session, entry, store):
        """Initialize."""
        self.id = entry.unique_id
        self.hass = hass
        self.store = store
        self.state = const.STATE_INIT
        self._workday_tracker = None
        self._workday_timer = None
        self.stopped = False

        super().__init__(hass, _LOGGER, name=const.DOMAIN)

        # detect time of prior shutdown to determine which schedules need to be triggered
        time_shutdown = self.store.async_get_time_shutdown()
        if time_shutdown:
            self.time_shutdown = dt_util.as_local(datetime.datetime.fromisoformat(time_shutdown))
            _LOGGER.debug("Scheduler detected a shutdown at {}.".format(self.time_shutdown))
        else:
            self.time_shutdown = None

        # wait for 10 seconds after HA startup to allow entities to be initialized
        @callback
        def handle_startup(_event):
            hass.async_create_task(self.async_init_workday_sensor())

            @callback
            def async_timer_finished(_now):
                self.state = const.STATE_READY
                async_dispatcher_send(self.hass, const.EVENT_STARTED)

            async_call_later(hass, 10, async_timer_finished)

        if hass.state == CoreState.running:
            handle_startup(None)
        else:
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, handle_startup)

        # store the current date+time when scheduler is being shutdown
        @callback
        async def async_handle_shutdown(_event):
            if self.stopped:
                return
            now = dt_util.utcnow().isoformat()
            await self.store.async_set_time_shutdown(now)

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_handle_shutdown)

    def async_get_schedule(self, schedule_id: str):
        """fetch a schedule (websocket API hook)"""
        if schedule_id not in self.hass.data[const.DOMAIN]["schedules"]:
            return None
        item = self.hass.data[const.DOMAIN]["schedules"][schedule_id]
        return item.async_get_entity_state()

    def async_get_schedules(self):
        """fetch a list of schedules (websocket API hook)"""
        schedules = self.hass.data[const.DOMAIN]["schedules"]
        data = []
        for item in schedules.values():
            config = item.async_get_entity_state()
            data.append(config)
        return data

    @callback
    def async_create_schedule(self, data):
        """add a new schedule"""
        tags = None
        if const.ATTR_TAGS in data:
            tags = data[const.ATTR_TAGS]
            del data[const.ATTR_TAGS]
        res = self.store.async_create_schedule(data)
        if res:
            self.async_assign_tags_to_schedule(res.schedule_id, tags)
            async_dispatcher_send(self.hass, const.EVENT_ITEM_CREATED, res)

    @callback
    def async_edit_schedule(self, schedule_id: str, data: dict):
        """edit an existing schedule"""
        if schedule_id not in self.hass.data[const.DOMAIN]["schedules"]:
            return
        item = self.async_get_schedule(schedule_id)

        if ATTR_NAME in data and item[ATTR_NAME] != data[ATTR_NAME]:
            data[ATTR_NAME] = data[ATTR_NAME].strip()
        elif ATTR_NAME in data:
            del data[ATTR_NAME]

        tags_updated = False
        tags = None
        if const.ATTR_TAGS in data:
            tags_updated = True
            tags = data[const.ATTR_TAGS]
            del data[const.ATTR_TAGS]

        entry = self.store.async_update_schedule(schedule_id, data)
        if tags_updated:
            self.async_assign_tags_to_schedule(schedule_id, tags)
        entity = self.hass.data[const.DOMAIN]["schedules"][schedule_id]
        if ATTR_NAME in data:
            # if the name has been changed, the entity ID must change hence the entity should be destroyed
            entity_registry = get_entity_registry(self.hass)
            entity_registry.async_remove(entity.entity_id)
            async_dispatcher_send(self.hass, const.EVENT_ITEM_CREATED, entry)
        else:
            async_dispatcher_send(self.hass, const.EVENT_ITEM_UPDATED, schedule_id)

    @callback
    def async_delete_schedule(self, schedule_id: str):
        """delete an existing schedule"""
        if schedule_id not in self.hass.data[const.DOMAIN]["schedules"]:
            return
        entity = self.hass.data[const.DOMAIN]["schedules"][schedule_id]
        entity_registry = get_entity_registry(self.hass)
        entity_registry.async_remove(entity.entity_id)
        self.store.async_delete_schedule(schedule_id)
        self.async_assign_tags_to_schedule(schedule_id, None)
        self.hass.data[const.DOMAIN]["schedules"].pop(schedule_id, None)
        async_dispatcher_send(self.hass, const.EVENT_ITEM_REMOVED, schedule_id)

    async def _async_update_data(self):
        """Update data via library."""
        return True

    async def async_unload(self):
        if self._workday_tracker:
            self._workday_tracker()
            self._workday_tracker = None
        self.stopped = True

    async def async_delete_config(self):
        await self.store.async_delete()

    def async_get_tags(self):
        """fetch a list of tags (websocket API hook)"""
        tags = self.store.async_get_tags()
        return list(tags.values())

    def async_get_tags_for_schedule(self, schedule_id: str):
        """fetch a list of tags for a schedule"""
        tags = self.async_get_tags()
        result = filter(lambda el: schedule_id in el[const.ATTR_SCHEDULES], tags)
        result = list(map(lambda x: x[ATTR_NAME], result))
        result = sorted(result)
        return result

    def async_assign_tags_to_schedule(self, schedule_id: str, new_tags: list):
        if not new_tags:
            new_tags = []
        old_tags = self.async_get_tags_for_schedule(schedule_id)
        for tag_name in old_tags:
            if tag_name not in new_tags:
                # remove old tag
                el = self.store.async_get_tag(tag_name)
                if len(el[const.ATTR_SCHEDULES]) > 1:
                    self.store.async_update_tag(
                        tag_name,
                        {
                            const.ATTR_SCHEDULES: [
                                x for x in el[const.ATTR_SCHEDULES] if x != schedule_id
                            ]
                        },
                    )
                else:
                    self.store.async_delete_tag(tag_name)
            else:
                new_tags.remove(tag_name)

        for tag_name in new_tags:
            # assign new tag
            el = self.store.async_get_tag(tag_name)
            if el:
                self.store.async_update_tag(
                    tag_name,
                    {const.ATTR_SCHEDULES: el[const.ATTR_SCHEDULES] + [schedule_id]},
                )
            else:
                self.store.async_create_tag(
                    {ATTR_NAME: tag_name, const.ATTR_SCHEDULES: [schedule_id]}
                )

    async def async_reset_workday_timer(self):
        """the workday polling timer has finished"""

        @callback
        async def async_workday_timer_finished(_now):
            """perform daily polling of the workday entity"""
            _LOGGER.debug("Performing daily update of workday sensor")
            await self.async_reset_workday_timer()
            async_dispatcher_send(self.hass, const.EVENT_WORKDAY_SENSOR_UPDATED)

        now = dt_util.as_local(dt_util.utcnow())
        ts = dt_util.find_next_time_expression_time(
            now, seconds=[0], minutes=[5], hours=[0]
        )
        today = now.date()
        while ts.date() == today:
            # ensure the timer is set for the next day
            now = now + datetime.timedelta(days=1)
            ts = dt_util.find_next_time_expression_time(
                now, seconds=[0], minutes=[5], hours=[0]
            )

        if self._workday_timer:
            self._workday_timer()

        self._workday_timer = async_track_point_in_time(
            self.hass, async_workday_timer_finished, ts
        )

    async def async_init_workday_sensor(self):
        """watch for changes in the workday sensor"""

        workday_entity = self.hass.states.get(const.WORKDAY_ENTITY)
        if not workday_entity:
            return None

        @callback
        async def async_workday_state_updated(_event):
            """the workday sensor has been updated"""
            _LOGGER.debug("Workday sensor has updated")
            await self.async_reset_workday_timer()
            async_dispatcher_send(self.hass, const.EVENT_WORKDAY_SENSOR_UPDATED)

        self._workday_tracker = async_track_state_change_event(
            self.hass, const.WORKDAY_ENTITY, async_workday_state_updated
        )
        await self.async_reset_workday_timer()

    async def async_enable_all_schedules(self):
        """enables all schedules"""
        for schedule in self.hass.data[const.DOMAIN]["schedules"].values():
            await schedule.async_turn_on()

    async def async_disable_all_schedules(self):
        """disables all schedules"""
        for schedule in self.hass.data[const.DOMAIN]["schedules"].values():
            await schedule.async_turn_off()
