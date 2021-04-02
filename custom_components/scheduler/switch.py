"""Initialization of Scheduler switch platform."""
import copy
import datetime
import logging
import voluptuous as vol


import homeassistant.util.dt as dt_util
from homeassistant.components.switch import DOMAIN as PLATFORM
from homeassistant.helpers import (entity_platform, config_validation as cv)
from homeassistant.const import (
    STATE_ALARM_TRIGGERED as STATE_TRIGGERED,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    ATTR_ENTITY_ID,
    ATTR_NAME,
    ATTR_TIME,
    CONF_SERVICE,
    ATTR_SERVICE_DATA,
)
from homeassistant.core import (
    callback
)
from homeassistant.helpers.device_registry import async_entries_for_config_entry
from homeassistant.helpers.entity import ToggleEntity
from homeassistant.helpers.entity_registry import async_entries_for_device
from homeassistant.helpers.event import (
    async_call_later,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
)
from . import const
from .migrate import migrate_old_entity
from .store import ScheduleEntry, async_get_registry
from .timer import TimerHandler
from .actions import ActionHandler

_LOGGER = logging.getLogger(__name__)


SERVICE_RUN_ACTION = "run_action"
RUN_ACTION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional(ATTR_TIME): cv.time
    }
)


def entity_exists_in_hass(hass, entity_id):
    """Check that an entity exists."""
    return hass.states.get(entity_id) is not None


async def async_setup(hass, config):
    """Track states and offer events for binary sensors."""
    return True


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the platform from config."""
    return True


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Scheduler switch devices. """

    coordinator = hass.data[const.DOMAIN]["coordinator"]

    if (
        "migrate_entities" in config_entry.data
        and config_entry.data["migrate_entities"]
    ):
        # perform one-time migration of old persistent entities to the store
        entities = []

        device_registry = await hass.helpers.device_registry.async_get_registry()
        devices = async_entries_for_config_entry(device_registry, config_entry.entry_id)
        device = devices[0]

        entity_registry = await hass.helpers.entity_registry.async_get_registry()
        for entry in async_entries_for_device(entity_registry, device.id):

            entities.append(MigrationScheduleEntity(coordinator, entry.unique_id))

        async_add_entities(entities)
        hass.config_entries.async_update_entry(config_entry, data={})
        _LOGGER.warning(
            "Migration of schedule entities in progress. Please restart HA to complete it."
        )

    @callback
    def async_add_entity(schedule: ScheduleEntry):
        """Add switch for Scheduler."""

        schedule_id = schedule.schedule_id
        name = schedule.name

        if name and len(slugify(name)):
            entity_id = "{}.schedule_{}".format(PLATFORM, slugify(name))
        else:
            entity_id = "{}.schedule_{}".format(PLATFORM, schedule_id)

        entity = ScheduleEntity(coordinator, hass, schedule_id, entity_id)
        hass.data[const.DOMAIN]["schedules"][schedule_id] = entity
        async_add_entities([entity])

    for entry in coordinator.store.schedules.values():
        async_add_entity(entry)

    async_dispatcher_connect(hass, const.EVENT_ITEM_CREATED, async_add_entity)

    platform = entity_platform.current_platform.get()

    platform.async_register_entity_service(
        SERVICE_RUN_ACTION, RUN_ACTION_SCHEMA, "async_service_run_action"
    )


class ScheduleEntity(ToggleEntity):
    """Defines a base schedule entity."""

    def __init__(self, coordinator, hass, schedule_id: str, entity_id: str) -> None:
        """Initialize the schedule entity."""
        self.coordinator = coordinator
        self.hass = hass
        self.schedule_id = schedule_id
        self.entity_id = entity_id
        self.schedule = None

        self._state = None
        self._timer = None
        self._next_trigger = None
        self._timestamps = []
        self._next_entries = []
        self._current_slot = None
        self._init = True

        self._listeners = [
            async_dispatcher_connect(self.hass, const.EVENT_ITEM_UPDATED, self.async_item_updated),
            async_dispatcher_connect(self.hass, const.EVENT_TIMER_UPDATED, self.async_timer_updated),
            async_dispatcher_connect(self.hass, const.EVENT_TIMER_FINISHED, self.async_timer_finished)
        ]

    @callback
    async def async_item_updated(self, id: str):
        """update internal properties when schedule config was changed"""
        if id != self.schedule_id:
            return
        store = await async_get_registry(self.hass)
        self.schedule = store.async_get_schedule(self.schedule_id)

        if self.schedule[const.ATTR_ENABLED] and self._state == STATE_OFF:
            self._state = STATE_ON
        elif not self.schedule[const.ATTR_ENABLED] and self._state != STATE_OFF:
            self._state = STATE_OFF

        self._init = True  # trigger actions of starting timeslot

        if self.hass is None:
            return

        await self.async_update_ha_state()
        self.hass.bus.async_fire(const.EVENT)

    @callback
    async def async_timer_updated(self, id: str):
        """update internal properties when schedule timer was changed"""
        if id != self.schedule_id:
            return

        self._next_entries = self._timer_handler.slot_queue
        self._timestamps = list(
            map(lambda x: datetime.datetime.isoformat(x), self._timer_handler.timestamps)
        )
        if self._current_slot is not None and self._timer_handler.current_slot is None:
            # we are leaving a timeslot, stop execution of actions
            await self._action_handler.async_empty_queue()
        self._current_slot = self._timer_handler.current_slot

        if self._init:
            # initial startpoint for timer calculated, fire actions if currently overlapping with timeslot
            if self._current_slot is not None:
                _LOGGER.debug(
                    "Schedule {} is starting in a timeslot, proceed with actions".format(self.schedule_id)
                )
                await self._action_handler.async_queue_actions(
                    self.schedule[const.ATTR_TIMESLOTS][self._current_slot]
                )
            self._init = False

        if self._state not in [STATE_OFF, STATE_TRIGGERED]:
            self._state = STATE_ON if len(self._next_entries) else STATE_UNAVAILABLE

        if self.hass is None:
            return

        await self.async_update_ha_state()
        self.hass.bus.async_fire(const.EVENT)

    @callback
    async def async_timer_finished(self, id: str):
        """fire actions when timer is finished"""
        if id != self.schedule_id or self._state == STATE_OFF:
            return

        if self._current_slot is not None:
            _LOGGER.debug(
                "Schedule {} is triggered, proceed with actions".format(self.schedule_id)
            )
            await self._action_handler.async_queue_actions(
                self.schedule[const.ATTR_TIMESLOTS][self._current_slot]
            )

        if self.schedule[const.ATTR_REPEAT_TYPE] == const.REPEAT_TYPE_PAUSE:
            await self.async_turn_off()
            return

        elif self.schedule[const.ATTR_REPEAT_TYPE] == const.REPEAT_TYPE_SINGLE:
            await self.coordinator.async_delete_schedule(self.schedule_id)
            return

        @callback
        async def async_trigger_finished(_now):
            """internal timer is finished, reset the schedule"""
            _LOGGER.debug("Resetting timer for {}".format(id))
            self._state = STATE_ON
            await self._timer_handler.async_start_timer()

        # keep the entity in triggered state for 1 minute, then restart the timer
        self._timer = async_call_later(
            self.hass,
            60,
            async_trigger_finished
        )
        self._state = STATE_TRIGGERED

        await self.async_update_ha_state()
        self.hass.bus.async_fire(const.EVENT)

    async def async_cancel_timer(self):
        """cancel timer"""
        if self._timer:
            self._timer()
            self._timer = None

    @property
    def device_info(self) -> dict:
        """Return info for device registry."""
        device = self.coordinator.id
        return {
            "identifiers": {(const.DOMAIN, device)},
            "name": "Scheduler",
            "model": "Scheduler",
            "sw_version": const.VERSION,
            "manufacturer": "@nielsfaber",
        }

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        if self.schedule and self.schedule[ATTR_NAME]:
            return self.schedule[ATTR_NAME]
        else:
            return "Schedule #{}".format(self.schedule_id)

    @property
    def should_poll(self) -> bool:
        """Return the polling requirement of the entity."""
        return False

    @property
    def state(self):
        """Return the state of the entity."""
        return self._state

    @property
    def icon(self):
        """Return icon."""
        return "mdi:calendar-clock"

    @property
    def weekdays(self):
        return self.schedule[const.ATTR_WEEKDAYS] if self.schedule else None

    @property
    def actions(self):
        actions = []
        if not self.schedule:
            return
        for timeslot in self.schedule[const.ATTR_TIMESLOTS]:
            for action in timeslot[const.ATTR_ACTIONS]:
                my_action = (
                    action
                    if action[ATTR_SERVICE_DATA]
                    else {
                        CONF_SERVICE: action[CONF_SERVICE],
                        ATTR_ENTITY_ID: action[ATTR_ENTITY_ID],
                    }
                )
                if my_action not in actions:
                    actions.append(my_action)

        return actions

    @property
    def times(self):
        times = []
        if not self.schedule:
            return
        for timeslot in self.schedule[const.ATTR_TIMESLOTS]:
            times.append(timeslot["start"])
        return times

    @property
    def state_attributes(self):
        """Return the data of the entity."""
        output = {
            "weekdays": self.weekdays,
            "times": self.times,
            "actions": self.actions,
            "current_slot": self._current_slot,
            "next_slot": self._next_entries[0] if len(self._next_entries) else None,
            "next_trigger": self._timestamps[self._next_entries[0]] if len(self._next_entries) else None,
        }

        return output

    @property
    def available(self):
        """Return True if entity is available."""
        return True

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{self.schedule_id}"

    @property
    def is_on(self):
        """Return true if entity is on."""
        return self._state != STATE_OFF

    @callback
    def async_get_entity_state(self):
        """fetch schedule data for websocket API"""
        data = copy.copy(self.schedule)
        if not data:
            data = {}
        data.update(
            {
                "next_entries": self._next_entries,
                "timestamps": self._timestamps,
                "name": self.schedule[ATTR_NAME] if self.schedule else "",
                "entity_id": self.entity_id,
            }
        )
        return data

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        store = await async_get_registry(self.hass)
        self.schedule = store.async_get_schedule(self.schedule_id)
        if not self.schedule[const.ATTR_ENABLED]:
            self._state = STATE_OFF
        self._timer_handler = TimerHandler(self.hass, self.schedule_id)
        self._action_handler = ActionHandler(self.hass, self.schedule_id)

    async def async_turn_off(self):
        """turn off a schedule"""
        if self.schedule[const.ATTR_ENABLED]:
            await self.coordinator.async_edit_schedule(
                self.schedule_id, {const.ATTR_ENABLED: False}
            )

    async def async_turn_on(self):
        """turn on a schedule"""
        if not self.schedule[const.ATTR_ENABLED]:
            await self.coordinator.async_edit_schedule(
                self.schedule_id, {const.ATTR_ENABLED: True}
            )

    async def async_will_remove_from_hass(self):
        """remove entity from hass."""
        _LOGGER.debug("Schedule {} is removed from hass".format(self.schedule_id))

        await self.async_cancel_timer()
        await self._action_handler.async_empty_queue()
        await self._timer_handler.async_unload()

        await super().async_will_remove_from_hass()

    async def async_service_remove(self):
        """remove a schedule"""
        self._state = STATE_OFF

        await self.async_remove()

    async def async_service_edit(
        self, entries, actions, conditions=None, options=None, name=None
    ):
        """edit a schedule"""
        if self._timer:
            old_state = self._state
            self._state = STATE_OFF
            self._timer()
            self._timer = None
            self._state = old_state

        await self.async_cancel_timer()
        await self._action_handler.async_empty_queue()
        await self._timer_handler.async_unload()

        await self.async_update_ha_state()

    async def async_service_run_action(self, time=None):
        """Manually trigger the execution of the actions of a timeslot"""

        now = dt_util.as_local(dt_util.utcnow())
        if time is not None:
            now = now.replace(hour=time.hour, minute=time.minute, second=time.second)

        (slot, ts) = self._timer_handler.current_timeslot(now)

        if slot is None and time is None and len(self.schedule[const.ATTR_TIMESLOTS]) == 1:
            slot = 0

        if slot is None:
            _LOGGER.info("Schedule {} has no active timeslot at {}".format(
                self.entity_id,
                now.strftime("%H:%M:%S")
            ))
            return

        _LOGGER.debug(
            "Executing actions for {}, timeslot {}".format(self.entity_id, slot)
        )
        await self._action_handler.async_queue_actions(
            self.schedule[const.ATTR_TIMESLOTS][slot]
        )


class MigrationScheduleEntity(RestoreEntity, ToggleEntity):
    """Defines a base schedule entity."""

    def __init__(self, coordinator, entity_id: str) -> None:
        self.coordinator = coordinator
        self.entity_id = "{}.{}".format(PLATFORM, entity_id)
        self.id = entity_id

    @property
    def is_on(self):
        """Return true if entity is on."""
        return False

    @property
    def available(self):
        """Return True if entity is available."""
        return False

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{self.id}"

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        await super().async_added_to_hass()

        state = await self.async_get_last_state()

        if state is not None and state.attributes:
            if "entries" in state.attributes:
                entry = migrate_old_entity(state.attributes, self.id)
                entry[const.ATTR_ENABLED] = state.state != STATE_OFF
                _LOGGER.info("Migrating schedule {}".format(entry[const.ATTR_SCHEDULE_ID]))
                self.coordinator.async_create_schedule(entry)

        await self.async_remove()

    async def async_will_remove_from_hass(self):
        """Connect to dispatcher listening for entity data notifications."""

        await super().async_will_remove_from_hass()

        entity_registry = await self.hass.helpers.entity_registry.async_get_registry()
        entity_registry.async_remove(self.entity_id)
