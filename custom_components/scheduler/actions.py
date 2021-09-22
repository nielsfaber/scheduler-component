
import logging

from homeassistant.core import (
    HomeAssistant,
    callback,
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
)
from homeassistant.components.climate import (
    SERVICE_SET_TEMPERATURE,
    SERVICE_SET_HVAC_MODE,
    ATTR_HVAC_MODE,
    ATTR_TEMPERATURE,
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.helpers.event import (
    async_track_state_change,
    async_call_later,
)
from homeassistant.helpers.service import async_call_from_config
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import const
from .store import ScheduleEntry

_LOGGER = logging.getLogger(__name__)

ACTION_WAIT = "wait"


def parse_service_call(data: dict):
    """turn action data into a service call"""

    service_call = {
        CONF_SERVICE: data[CONF_SERVICE],
        CONF_SERVICE_DATA: data[ATTR_SERVICE_DATA],
    }
    if ATTR_ENTITY_ID in data and data[ATTR_ENTITY_ID]:
        service_call[ATTR_ENTITY_ID] = data[ATTR_ENTITY_ID]

    if (
        service_call[CONF_SERVICE] == "{}.{}".format(CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE)
        and ATTR_HVAC_MODE in service_call[CONF_SERVICE_DATA]
        and ATTR_TEMPERATURE in service_call[CONF_SERVICE_DATA]
        and len(service_call[CONF_SERVICE_DATA]) == 2
    ):
        # fix for climate integrations which don't support setting hvac_mode and temperature together
        # add small delay between service calls for integrations that have a long processing time
        service_call = [
            {
                CONF_SERVICE: "{}.{}".format(CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE),
                ATTR_ENTITY_ID: service_call[ATTR_ENTITY_ID],
                CONF_SERVICE_DATA: {
                    ATTR_HVAC_MODE: service_call[CONF_SERVICE_DATA][ATTR_HVAC_MODE]
                },
            },
            {
                CONF_SERVICE: ACTION_WAIT,
                CONF_SERVICE_DATA: {CONF_DELAY: 1}
            },
            {
                CONF_SERVICE: "{}.{}".format(CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE),
                ATTR_ENTITY_ID: service_call[ATTR_ENTITY_ID],
                CONF_SERVICE_DATA: {
                    ATTR_TEMPERATURE: service_call[CONF_SERVICE_DATA][ATTR_TEMPERATURE]
                },
            }
        ]
        return service_call
    else:
        return [service_call]


def entity_is_available(hass: HomeAssistant, entity: str):
    """evaluate whether an entity is ready for targeting"""
    state = hass.states.get(entity)
    if state is None:
        return False
    elif state.state == STATE_UNAVAILABLE:
        return False
    elif state.state != STATE_UNKNOWN:
        return True
    else:
        # only reject unknown state when scheduler is initializing
        coordinator = hass.data["scheduler"]["coordinator"]
        if coordinator.state == const.STATE_INIT:
            return False
        else:
            return True


def service_is_available(hass: HomeAssistant, service: str):
    """evaluate whether a HA service is ready for targeting"""
    if service == ACTION_WAIT:
        return True
    domain = service.split(".").pop(0)
    domain_service = service.split(".").pop(1)
    return hass.services.has_service(domain, domain_service)


def validate_condition(hass: HomeAssistant, condition: dict):
    """Validate a condition against the current state"""
    if not entity_is_available(hass, condition[ATTR_ENTITY_ID]):
        return False

    state = hass.states.get(condition[ATTR_ENTITY_ID])

    required = condition[const.ATTR_VALUE]
    actual = state.state if state else None

    if isinstance(required, int):
        try:
            actual = int(float(actual))
        except (ValueError, TypeError):
            pass
    elif isinstance(required, float):
        try:
            actual = float(actual)
        except (ValueError, TypeError):
            pass
    elif isinstance(required, str):
        actual = str(actual)

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


class ActionHandler:
    def __init__(self, hass: HomeAssistant, schedule_id: str):
        """init"""
        self.hass = hass
        self._entity_tracker = None
        self._queue = []
        self._queue_busy = False
        self._timer = None
        self.id = schedule_id

        # trigger the queue once when HA has restarted
        async_dispatcher_connect(self.hass, const.EVENT_STARTED, self.async_process_queue)

    async def async_queue_actions(self, data: ScheduleEntry):
        """add new actions to queue"""
        await self.async_empty_queue()

        conditions = data[CONF_CONDITIONS]
        actions = [
            e
            for x in data[const.ATTR_ACTIONS]
            for e in parse_service_call(x)
        ]
        condition_type = data[const.ATTR_CONDITION_TYPE]

        entities = []
        for action in actions:
            if ATTR_ENTITY_ID in action and action[ATTR_ENTITY_ID] not in entities and action[ATTR_ENTITY_ID]:
                entities.append(action[ATTR_ENTITY_ID])

        for condition in conditions:
            if ATTR_ENTITY_ID in condition and condition[ATTR_ENTITY_ID] not in entities:
                entities.append(condition[ATTR_ENTITY_ID])

        for action in actions:
            self._queue.append({
                CONF_CONDITIONS: conditions,
                "action": action,
                const.ATTR_CONDITION_TYPE: condition_type
            })

        @callback
        async def async_entity_changed(entity, old_state, new_state):
            """check if actions can be processed"""

            _LOGGER.debug("[{}]: state of {} has changed, re-evaluating actions".format(self.id, entity))
            await self.async_process_queue()

        if entities:
            self._entity_tracker = async_track_state_change(
                self.hass, entities, async_entity_changed
            )
        await self.async_process_queue()

    async def async_empty_queue(self):
        """remove the items from the queue and stop listening to entity changes"""
        if self._entity_tracker:
            self._entity_tracker()
            self._entity_tracker = None
        if self._timer:
            self._timer()
            self._timer = None
        self._queue = []

    async def async_process_queue(self):
        """walk through the list of tasks and execute the ones that are ready"""
        i = 0
        self._queue_busy = True
        while i < len(self._queue):
            item = self._queue[i]
            action = item["action"]
            conditions = item[CONF_CONDITIONS]
            condition_type = item[const.ATTR_CONDITION_TYPE]
            entities = []

            if ATTR_ENTITY_ID in action and action[ATTR_ENTITY_ID]:
                entities.append(action[ATTR_ENTITY_ID])
            for condition in conditions:
                if ATTR_ENTITY_ID in condition and condition[ATTR_ENTITY_ID] not in entities:
                    entities.append(condition[ATTR_ENTITY_ID])

            unavailable_entities = [
                x for x in entities if not entity_is_available(self.hass, x)
            ]
            if not service_is_available(self.hass, action[CONF_SERVICE]):
                i += 1
                _LOGGER.debug("[{}]: service {} is unavailable, action is postponed".format(
                    self.id, action[CONF_SERVICE]
                ))
            elif len(unavailable_entities) > 0:
                i += 1
                _LOGGER.debug("[{}]: {} is unavailable, action {} is postponed".format(
                    self.id, ", ".join(unavailable_entities),
                    action[CONF_SERVICE]
                ))
            else:
                # all entities are available, execute the task
                res = await self.async_execute_action(action, conditions, condition_type)
                self._queue.pop(i)
                if not res:
                    return

        if not len(self._queue):
            await self.async_empty_queue()

        self._queue_busy = False

    async def async_execute_action(self, service_call: dict, conditions: list, condition_type: str):
        """execute a scheduled action"""
        result = (
            all(validate_condition(self.hass, item) for item in conditions)
            if condition_type == const.CONDITION_TYPE_AND
            else any(validate_condition(self.hass, item) for item in conditions)
        ) if len(conditions) else True
        if not result:
            _LOGGER.debug("[{}]: conditions have failed, skipping execution of action {}".format(
                self.id,
                service_call[CONF_SERVICE],
            ))
        else:
            if ATTR_ENTITY_ID in service_call:
                _LOGGER.debug("[{}]: Executing service {} on entity {}".format(
                    self.id, service_call[CONF_SERVICE], service_call[ATTR_ENTITY_ID]
                ))
            else:
                _LOGGER.debug("[{}]: Executing service {}".format(self.id, service_call[CONF_SERVICE]))

            if service_call[CONF_SERVICE] == ACTION_WAIT:
                @callback
                async def async_timer_finished(_now):
                    self._queue_busy = False
                    self._timer = None
                    await self.async_process_queue()

                self._timer = async_call_later(
                    self.hass,
                    service_call[CONF_SERVICE_DATA][CONF_DELAY],
                    async_timer_finished
                )
                return False

            await async_call_from_config(
                self.hass,
                service_call,
            )

        return True
