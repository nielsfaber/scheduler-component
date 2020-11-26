"""Initialization of Scheduler switch platform."""
import datetime
import logging

from homeassistant.components.switch import DOMAIN as PLATFORM
from homeassistant.core import callback
from homeassistant.helpers.device_registry import async_entries_for_config_entry
from homeassistant.helpers.entity import ToggleEntity
from homeassistant.helpers.entity_registry import async_entries_for_device
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_utc_time,
    async_track_state_change,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.service import async_call_from_config
from homeassistant.util import dt as dt_util

from homeassistant.const import (
    SUN_EVENT_SUNRISE,
    SUN_EVENT_SUNSET,
    STATE_OFF,
    STATE_ON,
    STATE_ALARM_TRIGGERED as STATE_TRIGGERED,
)
from .const import (
    DOMAIN,
    VERSION,
    MATCH_TYPE_ABOVE,
    MATCH_TYPE_BELOW,
    MATCH_TYPE_EQUAL,
    MATCH_TYPE_UNEQUAL,
    CONDITION_TYPE_AND,
    DAY_TYPE_WORKDAY,
    DAY_TYPE_WEEKEND,
)
from .migrate import migrate_old_entity

from .helpers import (
    has_overlapping_timeslot,
    calculate_next_timeslot,
)

_LOGGER = logging.getLogger(__name__)


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

    coordinator = hass.data[DOMAIN]

    entities = []

    device_registry = await hass.helpers.device_registry.async_get_registry()
    devices = async_entries_for_config_entry(device_registry, config_entry.entry_id)

    if len(devices) > 1:
        _LOGGER.error("Found multiple devices for integration")
        return False
    elif not devices:
        _LOGGER.error("Integration needs to be set up before it can be used")
        return False

    device = devices[0]

    entity_registry = await hass.helpers.entity_registry.async_get_registry()
    for entry in async_entries_for_device(entity_registry, device.id):

        entities.append(ScheduleEntity(coordinator, hass, entry.unique_id))

    async_add_entities(entities)

    @callback
    def async_add_entity(data):
        """Add switch for Scheduler."""

        _LOGGER.debug(data)
        return

        async_add_entities(
            [
                ScheduleEntity(
                    coordinator,
                    "schedule_",
                )
            ]
        )

    coordinator._create_schedule_handler = async_add_entity


class ScheduleEntity(RestoreEntity, ToggleEntity):
    """Defines a base schedule entity."""

    def __init__(
        self, coordinator, hass, entity_id: str
    ) -> None:
        """Initialize the schedule entity."""
        self.coordinator = coordinator
        self.hass = hass
        self.entity_id = "{}.{}".format(PLATFORM, entity_id)
        self.id = entity_id
        self._name = entity_id.capitalize().replace("_", " #")
        self._icon = "mdi:calendar-clock"
        self._state = None
        self._timer = None
        self._entry = None
        self._next_trigger = None
        self._registered_sun_update = False
        self._registered_workday_update = False
        self._queued_actions = []
        self._queued_entry = None
        self._retry_timeout = None
        self._schedule_id = None
        self._weekdays = None
        self._timeslots = None

    @property
    def device_info(self) -> dict:
        """Return info for device registry."""
        device = self.coordinator.id
        return {
            "identifiers": {(DOMAIN, device)},
            "name": "Scheduler",
            "model": "Scheduler",
            "sw_version": VERSION,
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
        """Return the state of the entity."""
        return self._state

    @property
    def icon(self):
        """Return icon."""
        return self._icon

    @property
    def state_attributes(self):
        """Return the data of the entity."""
        output = {
            "schedule_id": self._schedule_id,
            "weekdays": self._weekdays,
            "entities": self.entities,
        }
        if self._next_trigger:
            output["next_trigger"] = self._next_trigger

        return output

    @property
    def available(self):
        """Return True if entity is available."""
        return True

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{self.id}"

    @property
    def is_on(self):
        """Return true if entity is on."""
        return self._state != STATE_OFF

    @property
    def weekdays(self):
        """Return a list of weekdays for this entity."""
        return self._weekdays

    @property
    def entities(self):
        """Return a list of entities for this entity."""
        entities = []
        for timeslot in self._timeslots:
            for action in timeslot["actions"]:
                if action["entity_id"] and action["entity_id"] not in entities:
                    entities.append(action["entity_id"])
        return entities

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        await super().async_added_to_hass()

        state = await self.async_get_last_state()

        if state is not None:
            self._state = state.state

            if "name" in state.attributes:
                self._name = state.attributes["name"]
            if "icon" in state.attributes:
                self._icon = state.attributes["icon"]

            if "entries" in state.attributes:
                my_data = migrate_old_entity(state.attributes, self.id)
                self._schedule_id = my_data["schedule_id"]

            elif "schedule_id" in state.attributes:
                self._schedule_id = state.attributes["schedule_id"]

            config = self.coordinator.store.async_get_schedule(self._schedule_id)
            self._weekdays = config["weekdays"]
            self._timeslots = config["timeslots"]

        await self.async_register_workday_updates()
        await self.async_register_sun_updates()
        # async def async_startup_finished():
        #     await self.async_start_timer()

        # if not self.coordinator.is_started:
        #     self.coordinator.add_startup_listener(async_startup_finished)
        # else:
        #     await self.async_start_timer()

    async def async_turn_off(self):
        if self._state != STATE_OFF:
            self._state = STATE_OFF
            if self._timer:
                self._timer()
                self._timer = None
                self._next_trigger = None
            await self.async_abort_queued_actions()
            await self.async_update_ha_state()

    async def async_turn_on(self):
        if self._state == STATE_OFF:
            self._state = STATE_ON
            await self.async_start_timer()

    async def async_start_timer(self):
        """Search the entries for nearest timepoint and start timer."""
        if self._state == STATE_OFF:
            return

        # make sure to use latest-greatest workday / sun info
        self.workday_data = self.coordinator.workday_data
        self.sun_data = self.coordinator.sun_data

        _LOGGER.debug("Rescheduling timer for %s" % self.entity_id)

        start_timeslot = has_overlapping_timeslot(
            self._timeslots,
            weekdays=self.weekdays,
            sun_data=self.sun_data,
            workday_data=self.workday_data
        )

        if start_timeslot is not None:
            # execute the action of the current timeslot
            _LOGGER.debug("We are starting in a timeslot. Proceed with actions.")
            self._entry = start_timeslot
            await self.async_execute_command()

        (self._entry, timestamp) = calculate_next_timeslot(
            self._timeslots,
            weekdays=self.weekdays,
            sun_data=self.sun_data,
            workday_data=self.workday_data
        )
        self._next_trigger = dt_util.as_local(timestamp).isoformat()

        self._timer = async_track_point_in_utc_time(
            self.hass, self.async_timer_finished, timestamp
        )
        _LOGGER.debug("The next timer is set for %s" % self._next_trigger)

        self._state = STATE_ON

        await self.async_update_ha_state()
        self.async_write_ha_state()

    async def async_timer_finished(
        self, run_variables, context=None, skip_condition=False
    ):
        """Callback for timer finished."""

        self._timer = None
        if self._state != STATE_ON:
            return

        _LOGGER.debug("timer for %s is triggered" % self.entity_id)

        self._state = STATE_TRIGGERED
        self._next_trigger = None
        await self.async_update_ha_state()

        # cancel previous actions (previous timeslot)
        await self.async_abort_queued_actions()
        # execute the action
        await self.async_execute_command()

        # if (
        #     self.dataCollection.get_option_config(self._entry, OPTION_RUN_ONCE)
        #     is not None
        # ):
        #     _LOGGER.debug(
        #         "timer for %s has the run_once option, disabling" % self.entity_id
        #     )
        #     await self.async_turn_off()
        #     return

        # wait 1 minute before restarting
        now = dt_util.now().replace(microsecond=0)
        next = now + datetime.timedelta(minutes=1)

        self._timer = async_track_point_in_utc_time(
            self.hass, self.async_cooldown_timer_finished, next
        )

    async def async_cooldown_timer_finished(self, time):
        """Restart the timer, now that the cooldown timer finished."""
        self._timer = None

        if self._state != STATE_TRIGGERED:
            return

        await self.async_start_timer()

    async def async_execute_command(self):
        """Helper to execute command."""
        _LOGGER.debug("start of executing actions for %s" % self.entity_id)

        self._queued_entry = self._entry

        actions = self._timeslots[self._entry]["actions"]
        for num in range(len(actions)):
            action = actions[num]

            await self.async_queue_action(num, action)

        for item in self._queued_actions:
            if item is not None and not self._timeslots[self._entry]["stop"]:
                _LOGGER.debug("allowing devices to recover for 10 mins")
                self._retry_timeout = async_call_later(
                    self.hass, 600, self.async_abort_queued_actions
                )
                break

    async def async_abort_queued_actions(self, is_timeout=None):
        if self._retry_timeout:
            self._retry_timeout()
        if len(self._queued_actions):
            for item in self._queued_actions:
                if item is not None:
                    item()
            self._queued_actions = []
            self._queued_entry = None

    async def async_queue_action(self, num, service_call):
        async def async_handle_device_available():

            await self.async_execute_action(service_call)

            if self._queued_actions[num]:  # remove state change listener from queue
                self._queued_actions[num]()
                self._queued_actions[num] = None

            for item in self._queued_actions:  # check if queue is empty
                if item is not None:
                    return
            await self.async_abort_queued_actions()

        entity = service_call["entity_id"] if "entity_id" in service_call else None

        (res, cb_handle) = self.check_entity_availability(
            entity, async_handle_device_available
        )
        if res:
            await self.async_execute_action(service_call)
            self._queued_actions.append(None)
        else:
            self._queued_actions.append(cb_handle)
            _LOGGER.debug(
                "Entity {} is not available right now, action {} will be queued.".format(
                    entity, service_call["service"]
                )
            )

    async def async_execute_action(self, service_call):

        current_slot = self._timeslots[self._queued_entry]
        if current_slot["conditions"]:
            _LOGGER.debug("validating conditions for %s" % self.entity_id)

            results = self.validate_conditions_for_entry(current_slot["conditions"])
            result = all(results) if current_slot["condition_type"] == CONDITION_TYPE_AND else any(results)
            if not result:
                _LOGGER.debug("conditions have failed, skipping execution of actions")
                return

        if "entity_id" in service_call:
            _LOGGER.debug(
                "Executing action {} for entity {}.".format(
                    service_call["service"], service_call["entity_id"]
                )
            )
        else:
            _LOGGER.debug("Executing action {}.".format(service_call["service"]))

        await async_call_from_config(
            self.hass,
            service_call,
        )

    def validate_conditions_for_entry(self, conditions):
        """Validate the set of conditions against the results"""

        results = []
        for condition in conditions:
            state = self.hass.states.get(condition["entity_id"])

            required = condition["value"]
            actual = state.state if state else None

            if isinstance(required, int):
                try:
                    actual = int(float(actual))
                except:
                    pass
            elif isinstance(required, float):
                try:
                    actual = float(actual)
                except:
                    pass
            elif isinstance(required, str):
                actual = str(actual)

            if actual is None or actual == "unavailable" or actual == "unknown":
                result = False
            elif condition["match_type"] == MATCH_TYPE_EQUAL:
                result = actual == required
            elif condition["match_type"] == MATCH_TYPE_UNEQUAL:
                result = actual != required
            elif condition["match_type"] == MATCH_TYPE_BELOW:
                result = actual < required
            elif condition["match_type"] == MATCH_TYPE_ABOVE:
                result = actual > required
            else:
                result = False

            # _LOGGER.debug("validating condition for {}: required={}, actual={}, match_type={}, result={}".format(condition["entity_id"], required,actual,condition["match_type"], result))
            results.append(result)
        return results

    async def async_service_remove(self):
        self._state = STATE_OFF
        if self._timer:
            self._timer()
            self._timer = None

        await self.async_remove()

    async def async_service_edit(
        self, entries, actions, conditions=None, options=None, name=None
    ):
        if self._timer:
            old_state = self._state
            self._state = STATE_OFF
            self._timer()
            self._timer = None
            self._state = old_state

        await self.async_abort_queued_actions()
        await self.async_start_timer()

        await self.async_update_ha_state()

    async def async_will_remove_from_hass(self):
        """Connect to dispatcher listening for entity data notifications."""

        await super().async_will_remove_from_hass()

        entity_registry = (
            await self.hass.helpers.entity_registry.async_get_registry()
        )
        entity_registry.async_remove(self.entity_id)

    async def async_register_sun_updates(self):
        has_sun = False
        for item in self._timeslots:
            if (
                item["start"]
                and (SUN_EVENT_SUNRISE in item["start"] or SUN_EVENT_SUNSET in item["start"])
            ):
                has_sun = True
                break
            elif (
                item["stop"]
                and (SUN_EVENT_SUNRISE in item["stop"] or SUN_EVENT_SUNSET in item["stop"])
            ):
                has_sun = True
                break
        if not has_sun:
            return

        @callback
        async def async_sun_updated(sun_data):
            if self._state != STATE_ON:
                return

            slot = self._timeslots[self._entry]

            ts_old = calculate_next_timeslot(
                start=slot["start"],
                weekdays=self.weekdays,
                sun_data=self.sun_data,
                workday_data=self.workday_data
            )
            ts_new = calculate_next_timeslot(
                start=slot["start"],
                weekdays=self.weekdays,
                sun_data=sun_data,
                workday_data=self.workday_data
            )
            delta = (ts_old - ts_new).total_seconds()

            if abs(delta) >= 60 and abs(delta) <= 3600:
                # only reschedule if the drift is more than 1 min, and not hours (next day)
                self._state = STATE_OFF
                self._timer()
                self._timer = None
                self._state = STATE_ON
                await self.async_start_timer()

        self.coordinator.add_sun_listener(async_sun_updated)
        self._registered_sun_update = True

    async def async_register_workday_updates(self):
        if DAY_TYPE_WORKDAY not in self.weekdays and DAY_TYPE_WEEKEND not in self.weekdays:
            return

        @callback
        async def async_workday_updated(workday_data):
            if self._state != STATE_ON or not self._entry:
                return

            slot = self._timeslots[self._entry]

            ts_old = calculate_next_timeslot(
                start=slot["start"],
                weekdays=self.weekdays,
                sun_data=self.sun_data,
                workday_data=self.workday_data
            )
            ts_new = calculate_next_timeslot(
                start=slot["start"],
                weekdays=self.weekdays,
                sun_data=self.sun_data,
                workday_data=workday_data
            )
            delta = (ts_old - ts_new).total_seconds()

            if abs(delta) >= 3600:
                # item needs to be rescheduled
                self._state = STATE_OFF
                self._timer()
                self._timer = None
                self._state = STATE_ON
                await self.async_start_timer()

        self.coordinator.add_workday_listener(async_workday_updated)
        self._registered_workday_update = True

    def check_entity_availability(self, action_entity, cb_func):

        entity_list = self.dataCollection.get_condition_entities_for_entry(
            self._queued_entry
        )

        if not entity_list:
            entity_list = []
        if action_entity:
            entity_list.append(action_entity)

        if not len(entity_list):
            return

        async def async_check_entities_available(entity, old_state, new_state):
            result = True
            _LOGGER.debug(
                "Entity {} was updated to state={}, re-evaluating queued action.".format(
                    entity, new_state.state
                )
            )
            for entity in entity_list:
                state = self.hass.states.get(entity)
                if (
                    state is None
                    or state.state == "unavailable"
                    or state.state == "unknown"
                ):
                    result = False
                    break

            if result:
                await cb_func()

        listener_handles = []

        for entity in entity_list:
            state = self.hass.states.get(entity)
            if (
                state is None
                or state.state == "unavailable"
                or state.state == "unknown"
            ):
                listener_handle = async_track_state_change(
                    self.hass, entity, async_check_entities_available
                )
                listener_handles.append(listener_handle)

        def listener_handle_remover():
            while len(listener_handles):
                listener_handles.pop()()

        if len(listener_handles):
            return (False, listener_handle_remover)
        else:
            return (True, None)
