import logging

from homeassistant.core import (
    HomeAssistant,
    callback,
    CoreState,
)
from homeassistant.const import (
    CONF_SERVICE,
    ATTR_SERVICE_DATA,
    CONF_SERVICE_DATA,
    CONF_DELAY,
    ATTR_ENTITY_ID,
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
    CONF_CONDITIONS,
    CONF_ATTRIBUTE,
    CONF_STATE
)
from homeassistant.components.climate import (
    SERVICE_SET_TEMPERATURE,
    SERVICE_SET_HVAC_MODE,
    ATTR_HVAC_MODE,
    ATTR_TEMPERATURE,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_HIGH,
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.helpers.event import (
    async_track_state_change,
    async_call_later,
)
from homeassistant.helpers.service import async_call_from_config
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from . import const
from .store import ScheduleEntry

_LOGGER = logging.getLogger(__name__)

ACTION_WAIT = "wait"
ACTION_WAIT_STATE_CHANGE = "wait_state_change"


def parse_service_call(data: dict):
    """turn action data into a service call"""

    service_call = {
        CONF_SERVICE: data[CONF_SERVICE],
        CONF_SERVICE_DATA: data[ATTR_SERVICE_DATA],
    }
    if ATTR_ENTITY_ID in data and data[ATTR_ENTITY_ID]:
        service_call[ATTR_ENTITY_ID] = data[ATTR_ENTITY_ID]

    if (
        service_call[CONF_SERVICE]
        == "{}.{}".format(CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE)
        and ATTR_HVAC_MODE in service_call[CONF_SERVICE_DATA]
        and ATTR_ENTITY_ID in service_call
    ):
        # fix for climate integrations which don't support setting hvac_mode and temperature together
        # add small delay between service calls for integrations that have a long processing time
        # set temperature setpoint again for integrations which lose setpoint after switching hvac_mode
        _service_call = [
            {
                CONF_SERVICE: "{}.{}".format(CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE),
                ATTR_ENTITY_ID: service_call[ATTR_ENTITY_ID],
                CONF_SERVICE_DATA: {
                    ATTR_HVAC_MODE: service_call[CONF_SERVICE_DATA][ATTR_HVAC_MODE]
                },
            }
        ]
        if (
            ATTR_TEMPERATURE in service_call[CONF_SERVICE_DATA]
            or ATTR_TARGET_TEMP_LOW in service_call[CONF_SERVICE_DATA]
            or ATTR_TARGET_TEMP_HIGH in service_call[CONF_SERVICE_DATA]
        ):
            _service_call.extend([
                {
                    CONF_SERVICE: ACTION_WAIT_STATE_CHANGE,
                    ATTR_ENTITY_ID: service_call[ATTR_ENTITY_ID],
                    CONF_SERVICE_DATA: {
                        CONF_DELAY: 50,
                        CONF_STATE: service_call[CONF_SERVICE_DATA][ATTR_HVAC_MODE]
                    },
                },
                {
                    CONF_SERVICE: "{}.{}".format(CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE),
                    ATTR_ENTITY_ID: service_call[ATTR_ENTITY_ID],
                    CONF_SERVICE_DATA: {
                        x: service_call[CONF_SERVICE_DATA][x]
                        for x in service_call[CONF_SERVICE_DATA]
                        if x != ATTR_HVAC_MODE
                    },
                },
            ])
        return _service_call
    else:
        return [service_call]


def entity_is_available(hass: HomeAssistant, entity, is_target_entity=False):
    """evaluate whether an entity is ready for targeting"""
    state = hass.states.get(entity)
    if state is None:
        return False
    elif state.state == STATE_UNAVAILABLE:
        return False
    elif state.state != STATE_UNKNOWN:
        return True
    elif is_target_entity:
        # only reject unknown state when scheduler is initializing
        coordinator = hass.data["scheduler"]["coordinator"]
        if coordinator.state == const.STATE_INIT:
            return False
        else:
            return True
    else:
        #  for condition entities the unknown state is not allowed
        return False


def service_is_available(hass: HomeAssistant, service: str):
    """evaluate whether a HA service is ready for targeting"""
    if service in [ACTION_WAIT, ACTION_WAIT_STATE_CHANGE]:
        return True
    domain = service.split(".").pop(0)
    domain_service = service.split(".").pop(1)
    return hass.services.has_service(domain, domain_service)


def validate_condition(hass: HomeAssistant, condition: dict, *args):
    """Validate a condition against the current state"""

    if not entity_is_available(hass, condition[ATTR_ENTITY_ID], True):
        return False

    state = hass.states.get(condition[ATTR_ENTITY_ID])

    required = condition[const.ATTR_VALUE]
    actual = state.state if state else None
    if len(args):
        actual = args[0]

    if (
        condition[const.ATTR_MATCH_TYPE]
        in [
            const.MATCH_TYPE_BELOW,
            const.MATCH_TYPE_ABOVE,
        ]
        and isinstance(required, str)
    ):
        # parse condition as numeric if should be smaller or larger than X
        required = float(required)

    if isinstance(required, int):
        try:
            actual = int(float(actual))
        except (ValueError, TypeError):
            return False
    elif isinstance(required, float):
        try:
            actual = float(actual)
        except (ValueError, TypeError):
            return False
    elif isinstance(required, str):
        actual = str(actual).lower()
        required = required.lower()

    if condition[const.ATTR_MATCH_TYPE] == const.MATCH_TYPE_EQUAL:
        result = actual == required
    elif condition[const.ATTR_MATCH_TYPE] == const.MATCH_TYPE_UNEQUAL:
        result = actual != required
    elif condition[const.ATTR_MATCH_TYPE] == const.MATCH_TYPE_BELOW:
        result = actual < required
    elif condition[const.ATTR_MATCH_TYPE] == const.MATCH_TYPE_ABOVE:
        result = actual > required
    else:
        result = False

    # _LOGGER.debug(
    #     "validating condition for {}: required={}, actual={}, match_type={}, result={}"
    #     .format(condition[ATTR_ENTITY_ID], required, actual, condition[const.ATTR_MATCH_TYPE], result)
    # )
    return result


def action_has_effect(action: dict, hass: HomeAssistant):
    """check if action has an effect on the entity"""
    if ATTR_ENTITY_ID not in action:
        return True

    domain = action[CONF_SERVICE].split(".").pop(0)
    service = action[CONF_SERVICE].split(".").pop(1)
    state = hass.states.get(action[ATTR_ENTITY_ID])
    current_state = state.state if state else None

    if (
        domain == CLIMATE_DOMAIN
        and service in [SERVICE_SET_HVAC_MODE, SERVICE_SET_TEMPERATURE]
        and state
    ):
        if (
            ATTR_HVAC_MODE in action[CONF_SERVICE_DATA]
            and action[CONF_SERVICE_DATA][ATTR_HVAC_MODE] != current_state
        ):
            return True
        if ATTR_TEMPERATURE in action[CONF_SERVICE_DATA] and float(
            state.attributes.get(ATTR_TEMPERATURE, 0) or 0
        ) != float(action[CONF_SERVICE_DATA].get(ATTR_TEMPERATURE)):
            return True
        if ATTR_TARGET_TEMP_LOW in action[CONF_SERVICE_DATA] and float(
            state.attributes.get(ATTR_TARGET_TEMP_LOW, 0) or 0
        ) != float(action[CONF_SERVICE_DATA].get(ATTR_TARGET_TEMP_LOW)):
            return True
        if ATTR_TARGET_TEMP_HIGH in action[CONF_SERVICE_DATA] and float(
            state.attributes.get(ATTR_TARGET_TEMP_HIGH, 0) or 0
        ) != float(action[CONF_SERVICE_DATA].get(ATTR_TARGET_TEMP_HIGH)):
            return True
        return False

    return True


class ActionHandler:
    def __init__(self, hass: HomeAssistant, schedule_id: str):
        """init"""
        self.hass = hass
        self._queues = {}
        self._timer = None
        self.id = schedule_id

        async_dispatcher_connect(
            self.hass, "action_queue_finished", self.async_cleanup_queues
        )

    async def async_queue_actions(self, data: ScheduleEntry, skip_initial_execution = False):
        """add new actions to queue"""
        await self.async_empty_queue()

        conditions = data[CONF_CONDITIONS]
        actions = [e for x in data[const.ATTR_ACTIONS] for e in parse_service_call(x)]
        condition_type = data[const.ATTR_CONDITION_TYPE]
        track_conditions = data[const.ATTR_TRACK_CONDITIONS]

        # create an ActionQueue object per targeted entity (such that the tasks are handled independently)
        for action in actions:
            entity = action[ATTR_ENTITY_ID] if ATTR_ENTITY_ID in action else "none"

            if entity not in self._queues:
                self._queues[entity] = ActionQueue(
                    self.hass, self.id, conditions, condition_type, track_conditions
                )

            self._queues[entity].add_action(action)

        for queue in self._queues.values():
            await queue.async_start(skip_initial_execution)

    async def async_cleanup_queues(self, id: str = None):
        """remove all objects from queue which have no remaining tasks"""
        if id is not None and id != self.id or not len(self._queues.keys()):
            return

        # remove all items which are either finished executing
        # or have all their entities available (i.e. conditions have failed beforee)
        queue_items = list(self._queues.keys())
        for key in queue_items:
            if self._queues[key].is_finished() or (
                self._queues[key].is_available() and not self._queues[key].queue_busy
            ):
                await self._queues[key].async_clear()
                self._queues.pop(key)

        if not len(self._queues.keys()):
            _LOGGER.debug("[{}]: Finished execution of actions".format(self.id))

    async def async_empty_queue(self, **kwargs):
        """remove all objects from queue"""
        restore_time = kwargs.get("restore_time")

        async def async_clear_queue(_now=None):
            """clear queue"""
            if self._timer:
                self._timer()
                self._timer = None

            while len(self._queues.keys()):
                key = list(self._queues.keys())[0]
                await self._queues[key].async_clear()
                self._queues.pop(key)

        if restore_time:
            await self.async_cleanup_queues()
            if not len(self._queues):
                return

            _LOGGER.debug(
                "Waiting for unavailable entities to be restored for {} mins".format(
                    restore_time
                )
            )
            self._timer = async_call_later(
                self.hass, restore_time * 60, async_clear_queue
            )
        else:
            await async_clear_queue()


class ActionQueue:
    def __init__(
        self,
        hass: HomeAssistant,
        id: str,
        conditions: list,
        condition_type: str,
        track_conditions: bool,
    ):
        """create a new action queue"""
        self.hass = hass
        self.id = id
        self._timer = None
        self._action_entities = []
        self._condition_entities = []
        self._listeners = []
        self._state_update_listener = None
        self._conditions = conditions
        self._condition_type = condition_type
        self._queue = []
        self.queue_busy = False
        self._track_conditions = track_conditions
        self._wait_for_available = True

        for condition in conditions:
            if (
                ATTR_ENTITY_ID in condition
                and condition[ATTR_ENTITY_ID] not in self._condition_entities
            ):
                self._condition_entities.append(condition[ATTR_ENTITY_ID])

    def add_action(self, action: dict):
        """add an action to the queue"""
        if (
            ATTR_ENTITY_ID in action
            and action[ATTR_ENTITY_ID]
            and action[ATTR_ENTITY_ID] not in self._action_entities
        ):
            self._action_entities.append(action[ATTR_ENTITY_ID])

        self._queue.append(action)

    async def async_start(self, skip_initial_execution):
        """start execution of the actions in the queue"""

        @callback
        async def async_entity_changed(entity, old_state, new_state):
            """check if actions can be processed"""

            old_state = old_state.state if old_state else None
            new_state = new_state.state if new_state else None

            if old_state == new_state:
                # no change
                return

            if self.queue_busy:
                return

            if entity not in self._condition_entities and not self._wait_for_available:
                # only watch until entity becomes available in the action entities
                return

            if (
                entity in self._condition_entities
                and old_state
                and new_state
                and old_state not in [STATE_UNAVAILABLE, STATE_UNKNOWN]
                and new_state not in [STATE_UNAVAILABLE, STATE_UNKNOWN]
            ):
                conditions = list(filter(lambda e: e[ATTR_ENTITY_ID] == entity, self._conditions))
                if all([
                    validate_condition(self.hass, item, old_state) == validate_condition(self.hass, item, new_state)
                    for item in conditions
                ]):
                    # ignore if state change has no effect on condition rules
                    return

            _LOGGER.debug(
                "[{}]: State of {} has changed, re-evaluating actions".format(
                    self.id, entity
                )
            )
            await self.async_process_queue()

        watched_entities = list(set(self._condition_entities + self._action_entities))
        if len(watched_entities):
            self._listeners.append(
                async_track_state_change(
                    self.hass, watched_entities, async_entity_changed
                )
            )


        if not skip_initial_execution:
            await self.async_process_queue()

            # trigger the queue once when HA has restarted
            if self.hass.state != CoreState.running:
                self._listeners.append(
                    async_dispatcher_connect(
                        self.hass, const.EVENT_STARTED, self.async_process_queue
                    )
                )
        else:
            self._wait_for_available = False

    async def async_clear(self):
        """clear action queue object"""
        if self._timer:
            self._timer()
        self._timer = None

        while len(self._listeners):
            self._listeners.pop()()

        if self._state_update_listener:
            self._state_update_listener()
        self._state_update_listener = None

    def is_finished(self):
        """check whether all queue items are finished"""
        return len(self._queue) == 0

    def is_available(self):
        """check if all services and entities involved in the task are available"""

        # check services
        required_services = [action[CONF_SERVICE] for action in self._queue]
        failed_service = next(
            (x for x in required_services if not service_is_available(self.hass, x)),
            None,
        )
        if failed_service:
            _LOGGER.debug(
                "[{}]: Service {} is unavailable, scheduled action cannot be executed".format(
                    self.id, failed_service
                )
            )
            return False

        # check entities
        watched_entities = list(set(self._condition_entities + self._action_entities))
        failed_entity = next(
            (
                x
                for x in watched_entities
                if not entity_is_available(self.hass, x, x in self._action_entities)
            ),
            None,
        )
        if failed_entity:
            _LOGGER.debug(
                "[{}]: Entity {} is unavailable, scheduled action cannot be executed".format(
                    self.id, failed_entity
                )
            )
            return False

        if self._wait_for_available:
            self._wait_for_available = False

        return True

    async def async_process_queue(self, task_idx=0):
        """walk through the list of tasks and execute the ones that are ready"""
        if self.queue_busy or not self.is_available():
            return

        self.queue_busy = True

        # verify conditions
        conditions_passed = (
            (
                all(validate_condition(self.hass, item) for item in self._conditions)
                if self._condition_type == const.CONDITION_TYPE_AND
                else any(
                    validate_condition(self.hass, item) for item in self._conditions
                )
            )
            if len(self._conditions)
            else True
        )

        if not conditions_passed and len(self._queue):
            _LOGGER.debug(
                "[{}]: Conditions have failed, skipping execution of actions".format(
                    self.id
                )
            )
            if self._track_conditions:
                # postpone tasks
                self.queue_busy = False
                return

            else:
                # abort all items in queue
                while len(self._queue):
                    self._queue.pop()

        skip_action = False

        while task_idx < len(self._queue):
            action = self._queue[task_idx]

            if action[CONF_SERVICE] in [ACTION_WAIT, ACTION_WAIT_STATE_CHANGE]:
                if skip_action:
                    task_idx = task_idx + 1
                    continue
                elif action[CONF_SERVICE] == ACTION_WAIT_STATE_CHANGE:
                    state = self.hass.states.get(action[ATTR_ENTITY_ID])
                    if CONF_ATTRIBUTE in action[CONF_SERVICE_DATA]:
                        state = state.attributes.get(action[CONF_SERVICE_DATA][CONF_ATTRIBUTE])
                    else:
                        state = state.state
                    if state == action[CONF_SERVICE_DATA][CONF_STATE]:
                        _LOGGER.debug(
                            "[{}]: Entity {} is already set to {}, proceed with next action".format(
                                self.id,
                                action[ATTR_ENTITY_ID],
                                state,
                            )
                        )
                        task_idx = task_idx + 1
                        continue

                @callback
                async def async_timer_finished(_now):
                    self._timer = None
                    if self._state_update_listener:
                        self._state_update_listener()
                    self._state_update_listener = None
                    self.queue_busy = False
                    await self.async_process_queue(task_idx + 1)

                self._timer = async_call_later(
                    self.hass,
                    action[CONF_SERVICE_DATA][CONF_DELAY],
                    async_timer_finished,
                )
                _LOGGER.debug(
                    "[{}]: Postponing next action for {} seconds".format(
                        self.id, action[CONF_SERVICE_DATA][CONF_DELAY]
                    )
                )

                @callback
                async def async_entity_changed(entity, old_state, new_state):
                    if CONF_ATTRIBUTE in action[CONF_SERVICE_DATA]:
                        old_state = old_state.attributes.get(action[CONF_SERVICE_DATA][CONF_ATTRIBUTE])
                        new_state = new_state.attributes.get(action[CONF_SERVICE_DATA][CONF_ATTRIBUTE])
                    else:
                        old_state = old_state.state
                        new_state = new_state.state
                    if old_state == new_state:
                        return
                    _LOGGER.debug(
                        "[{}]: Entity {} was updated from {} to {}".format(
                            self.id,
                            entity,
                            old_state,
                            new_state
                        )
                    )
                    if new_state == action[CONF_SERVICE_DATA][CONF_STATE]:
                        _LOGGER.debug("[{}]: Stop postponing next action".format(self.id))
                        if self._timer:
                            self._timer()
                        self._timer = None
                        self._state_update_listener()
                        self._state_update_listener = None
                        self.queue_busy = False
                        await self.async_process_queue(task_idx + 1)

                if action[CONF_SERVICE] == ACTION_WAIT_STATE_CHANGE:
                    self._state_update_listener = async_track_state_change(
                        self.hass, action[ATTR_ENTITY_ID], async_entity_changed
                    )
                return

            if ATTR_ENTITY_ID in action:
                _LOGGER.debug(
                    "[{}]: Executing service {} on entity {}".format(
                        self.id, action[CONF_SERVICE], action[ATTR_ENTITY_ID]
                    )
                )
            else:
                _LOGGER.debug(
                    "[{}]: Executing service {}".format(self.id, action[CONF_SERVICE])
                )

            skip_action = not action_has_effect(action, self.hass)
            if skip_action:
                _LOGGER.debug("[{}]: Action has no effect, skipping".format(self.id))
            else:
                await async_call_from_config(
                    self.hass,
                    action,
                )
            task_idx = task_idx + 1

        self.queue_busy = False

        if not self._track_conditions or not len(self._conditions):
            while len(self._queue):
                self._queue.pop()

            async_dispatcher_send(self.hass, "action_queue_finished", self.id)
        else:
            _LOGGER.debug(
                "[{}]: Done for now, Waiting for conditions to change".format(self.id)
            )
