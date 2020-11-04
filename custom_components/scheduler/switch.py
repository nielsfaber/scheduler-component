"""Initialization of Scheduler switch platform."""
import datetime
import logging
import secrets

from homeassistant.components.switch import DOMAIN as PLATFORM
from homeassistant.helpers import entity_platform
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

from .const import (
    DOMAIN,
    OPTION_RUN_ONCE,
    SCHEMA_EDIT,
    SCHEMA_ENTITY,
    SCHEMA_TEST,
    SERVICE_EDIT,
    SERVICE_REMOVE,
    SERVICE_TEST,
    STATE_DISABLED,
    STATE_INITIALIZING,
    STATE_INVALID,
    STATE_TRIGGERED,
    STATE_WAITING,
    VERSION,
)
from .datacollection import DataCollection

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

    coordinator = hass.data[DOMAIN][config_entry.entry_id]

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

        entities.append(ScheduleEntity(coordinator, entry.unique_id))

    async_add_entities(entities)

    # callback from the coordinator
    def async_add_switch(data):
        """Add switch for Scheduler."""

        # Generate a unique token
        token = secrets.token_hex(3)
        while entity_exists_in_hass(hass, "{}.schedule_{}".format(PLATFORM, token)):
            token = secrets.token_hex(3)

        datacollection = DataCollection()
        datacollection.import_from_service(data)

        async_add_entities(
            [
                ScheduleEntity(
                    coordinator,
                    "schedule_{}".format(token),
                    datacollection,
                )
            ]
        )

    # We add a listener after fetching the data, so manually trigger listener
    coordinator.async_add_listener(async_add_switch)

    platform = entity_platform.current_platform.get()

    platform.async_register_entity_service(
        SERVICE_TEST, SCHEMA_TEST, "async_execute_command"
    )

    platform.async_register_entity_service(
        SERVICE_REMOVE, SCHEMA_ENTITY, "async_service_remove"
    )

    platform.async_register_entity_service(
        SERVICE_EDIT, SCHEMA_EDIT, "async_service_edit"
    )


class ScheduleEntity(RestoreEntity, ToggleEntity):
    """Defines a base schedule entity."""

    def __init__(
        self, coordinator, entity_id: str, data: DataCollection = None
    ) -> None:
        """Initialize the schedule entity."""
        self.coordinator = coordinator
        self.entity_id = "{}.{}".format(PLATFORM, entity_id)
        self.id = entity_id
        self._name = entity_id.capitalize().replace("_", " #")
        self.dataCollection = data
        self._valid = True
        self._state = STATE_INITIALIZING
        self._timer = None
        self._entry = None
        self._next_trigger = None
        self._registered_sun_update = False
        self._registered_workday_update = False
        self._queued_actions = []
        self._queued_entry = None
        self._retry_timeout = None

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
        if self.dataCollection and self.dataCollection.name:
            return self.dataCollection.name
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
        if self.dataCollection and self.dataCollection.icon:
            return self.dataCollection.icon
        return "mdi:calendar-clock"

    @property
    def state_attributes(self):
        """Return the data of the entity."""
        output = (
            self.dataCollection.export_data() if self.dataCollection is not None else {}
        )
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
        return self._state != STATE_DISABLED

    async def async_turn_off(self):
        if self._state != STATE_DISABLED:
            self._state = STATE_DISABLED
            if self._timer:
                self._timer()
                self._timer = None
                self._next_trigger = None
            await self.async_abort_queued_actions()
            await self.async_update_ha_state()

    async def async_turn_on(self):
        if self._state == STATE_DISABLED:
            if not self._valid:
                self._state = STATE_INVALID
                await self.async_update_ha_state()
            else:
                self._state = STATE_WAITING
                await self.async_start_timer()

    async def async_start_timer(self):
        """Search the entries for nearest timepoint and start timer."""
        if self.dataCollection is None:
            return

        if self._state == STATE_DISABLED:
            return

        _LOGGER.debug("Rescheduling timer for %s" % self.entity_id)
        await self.async_update_sun_data()
        await self.async_update_workday_data()
        (
            self._entry,
            has_overlapping_timeslot,
        ) = self.dataCollection.has_overlapping_timeslot()

        if has_overlapping_timeslot:
            # execute the action
            _LOGGER.debug("We are starting in a timeslot. Proceed with actions.")
            await self.async_execute_command()

        (self._entry, timestamp) = self.dataCollection.get_next_entry()
        self._next_trigger = dt_util.as_local(timestamp).isoformat()

        self._timer = async_track_point_in_utc_time(
            self.coordinator.hass, self.async_timer_finished, timestamp
        )
        _LOGGER.debug("The next timer is set for %s" % self._next_trigger)

        self._state = STATE_WAITING

        await self.async_update_ha_state()
        self.async_write_ha_state()

    async def async_timer_finished(
        self, run_variables, context=None, skip_condition=False
    ):
        """Callback for timer finished."""

        self._timer = None
        if self._state != STATE_WAITING:
            return

        _LOGGER.debug("timer for %s is triggered" % self.entity_id)

        self._state = STATE_TRIGGERED
        self._next_trigger = None
        await self.async_update_ha_state()

        # cancel previous actions (previous timeslot)
        await self.async_abort_queued_actions()
        # execute the action
        await self.async_execute_command()

        if (
            self.dataCollection.get_option_config(self._entry, OPTION_RUN_ONCE)
            is not None
        ):
            _LOGGER.debug(
                "timer for %s has the run_once option, disabling" % self.entity_id
            )
            await self.async_turn_off()
            return

        # wait 1 minute before restarting
        now = dt_util.now().replace(microsecond=0)
        next = now + datetime.timedelta(minutes=1)

        self._timer = async_track_point_in_utc_time(
            self.coordinator.hass, self.async_cooldown_timer_finished, next
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

        service_calls = self.dataCollection.get_service_calls_for_entry(self._entry)
        for num in range(len(service_calls)):
            service_call = service_calls[num]

            await self.async_queue_action(num, service_call)

        for item in self._queued_actions:
            if item is not None and not self.dataCollection.is_timeslot(self._entry):
                _LOGGER.debug("allowing devices to recover for 10 mins")
                self._retry_timeout = async_call_later(
                    self.coordinator.hass, 600, self.async_abort_queued_actions
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

        if "entity_id" in service_call:
            action_entity = service_call["entity_id"]
        else:
            action_entity = None

        (res, cb_handle) = self.check_entity_availability(
            action_entity, async_handle_device_available
        )
        if res:
            await self.async_execute_action(service_call)
            self._queued_actions.append(None)
        else:
            self._queued_actions.append(cb_handle)
            _LOGGER.debug(
                "Entity {} is not available right now, action {} will be queued.".format(
                    service_call["entity_id"], service_call["service"]
                )
            )

    async def async_execute_action(self, service_call):

        condition_entities = self.dataCollection.get_condition_entities_for_entry(
            self._queued_entry
        )
        if condition_entities:
            _LOGGER.debug("validating conditions for %s" % self.entity_id)
            states = {}
            for entity in condition_entities:
                state = await self.coordinator.async_request_state(entity)
                states[entity] = state

            result = self.dataCollection.validate_conditions_for_entry(
                self._queued_entry, states
            )
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

        state = self.coordinator.hass.states.get(service_call["entity_id"])

        await async_call_from_config(
            self.coordinator.hass,
            service_call,
        )

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        await super().async_added_to_hass()

        state = await self.async_get_last_state()

        if state is not None:
            self._state = state.state
            data = DataCollection()
            self._valid = data.import_data(state.attributes)
            self.dataCollection = data

        async def async_startup_finished():
            await self.async_start_timer()

        if not self.coordinator.is_started:
            self.coordinator.add_startup_listener(async_startup_finished)
        else:
            await self.async_start_timer()

    async def async_service_remove(self):
        self._state = STATE_DISABLED
        if self._timer:
            self._timer()
            self._timer = None

        await self.async_remove()

    async def async_service_edit(
        self, entries, actions, conditions=None, options=None, name=None
    ):

        data = DataCollection()
        data.import_from_service(
            {
                "entries": entries,
                "actions": actions,
                "conditions": conditions,
                "options": options,
                "name": name,
            }
        )
        self.dataCollection = data

        if self._timer:
            old_state = self._state
            self._state = STATE_DISABLED
            self._timer()
            self._timer = None
            self._state = old_state

        await self.async_abort_queued_actions()
        await self.async_start_timer()

        await self.async_update_ha_state()

    async def async_update(self):
        """Update Scheduler entity."""

        await self.coordinator.async_request_refresh()

    async def async_will_remove_from_hass(self):
        """Connect to dispatcher listening for entity data notifications."""

        await super().async_will_remove_from_hass()

        entity_registry = (
            await self.coordinator.hass.helpers.entity_registry.async_get_registry()
        )
        entity_registry.async_remove(self.entity_id)

    async def async_update_sun_data(self):
        if not self.dataCollection or not self.dataCollection.has_sun():
            return

        self.dataCollection.update_sun_data(self.coordinator.sun_data)

        if not self._registered_sun_update:
            await self.async_register_sun_updates()

    async def async_register_sun_updates(self):
        async def async_sun_updated(sun_data):
            if self._state != STATE_WAITING:
                return
            if not self.dataCollection.has_sun(self._entry):
                return

            should_update = self.dataCollection.update_sun_data(sun_data, self._entry)
            if should_update:
                self._state = STATE_DISABLED
                self._timer()
                self._timer = None
                self._state = STATE_WAITING
                await self.async_start_timer()

        self.coordinator.add_sun_listener(async_sun_updated)
        self._registered_sun_update = True

    async def async_update_workday_data(self):
        if not self.dataCollection or not self.dataCollection.has_workday():
            return
        self.dataCollection.update_workday_data(self.coordinator.workday_data)

        if not self._registered_workday_update:
            await self.async_register_workday_updates()

    async def async_register_workday_updates(self):
        async def async_workday_updated(workday_data):
            if self._state != STATE_WAITING:
                return
            if not self.dataCollection.has_workday(self._entry):
                return

            should_update = self.dataCollection.update_workday_data(
                workday_data, self._entry
            )
            if should_update:
                self._state = STATE_DISABLED
                self._timer()
                self._timer = None
                self._state = STATE_WAITING
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
                state = self.coordinator.hass.states.get(entity)
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
            state = self.coordinator.hass.states.get(entity)
            if (
                state is None
                or state.state == "unavailable"
                or state.state == "unknown"
            ):
                listener_handle = async_track_state_change(
                    self.coordinator.hass, entity, async_check_entities_available
                )
                listener_handles.append(listener_handle)

        def listener_handle_remover():
            while len(listener_handles):
                listener_handles.pop()()

        if len(listener_handles):
            return (False, listener_handle_remover)
        else:
            return (True, None)
