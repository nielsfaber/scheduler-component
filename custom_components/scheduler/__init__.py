import logging
import voluptuous as vol
import json
import datetime
from homeassistant.helpers.json import JSONEncoder
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.entity import ToggleEntity, Entity
from homeassistant.util import convert, dt as dt_util, location as loc_util
from homeassistant.helpers import (
    config_validation as cv,
    service,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers.event import async_track_state_change
from homeassistant.components.timer import TimerStorageCollection
from homeassistant.helpers import collection
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_point_in_utc_time
import homeassistant.util.dt as dt_util

from .const import (
    DOMAIN,
    STATE_INITIALIZING,
    STATE_WAITING,
    STATE_TRIGGERED,
    STATE_DISABLED,
    STATE_INVALID,
    SERVICE_TURN_ON,
    SERVICE_TURN_OFF,
    SERVICE_TEST,
    SERVICE_REMOVE,
    SERVICE_EDIT,
    SERVICE_ADD,
    SCHEMA_ENTITY,
    SCHEMA_EDIT,
    SCHEMA_ADD,
    MQTT_DISCOVERY_TOPIC,
    MQTT_STORAGE_TOPIC,
    EXPOSED_ENTITY_PROPERTIES,
    STORED_ENTITY_PROPERTIES,
    SUN_ENTITY,
    # STORAGE_KEY, STORAGE_VERSION,
)

from .helpers import (
    get_id_from_topic,
    entity_exists_in_hass,
    service_exists_in_hass,
    parse_sun_time_string,
    time_has_sun,
)

_LOGGER = logging.getLogger(__name__)

ENTITY_ID_FORMAT = DOMAIN + ".{}"
DEPENDENCIES = ["mqtt"]


async def async_setup(hass, config):
    mqtt = hass.components.mqtt
    component = EntityComponent(_LOGGER, DOMAIN, hass)
    _LOGGER.debug("setting up scheduler component")
    # set up storage for timers
    # _LOGGER.debug("setting up storage")
    # id_manager = collection.IDManager()
    # storage_collection = TimerStorageCollection(
    #     Store(hass, STORAGE_VERSION, STORAGE_KEY),
    #     logging.getLogger(f"{__name__}.storage_collection"),
    #     id_manager,
    # )
    # collection.attach_entity_component_collection(component, storage_collection, SchedulerEntity)
    # await storage_collection.async_load()
    # collection.attach_entity_registry_cleaner(hass, DOMAIN, DOMAIN, storage_collection)
    # _LOGGER.debug("done setting up storage")

    async def async_handle_discovery(msg):
        entity_id = get_id_from_topic(msg.topic)

        if entity_id is None:
            return
        elif entity_exists_in_hass(hass, ENTITY_ID_FORMAT.format(entity_id)):
            return
        elif msg.payload is None:
            return

        _LOGGER.debug("discovered entity %s" % entity_id)
        data = json.loads(msg.payload)

        await component.async_add_entities([SchedulerEntity(hass, entity_id, data)])

    _LOGGER.debug("subscribing to %s" % MQTT_DISCOVERY_TOPIC)
    await mqtt.async_subscribe(MQTT_DISCOVERY_TOPIC, async_handle_discovery)

    component.async_register_entity_service(
        SERVICE_TURN_ON, SCHEMA_ENTITY, "async_turn_on"
    )

    component.async_register_entity_service(
        SERVICE_TURN_OFF, SCHEMA_ENTITY, "async_turn_off"
    )

    component.async_register_entity_service(
        SERVICE_TEST, SCHEMA_ENTITY, "async_execute_command"
    )

    component.async_register_entity_service(
        SERVICE_REMOVE, SCHEMA_ENTITY, "async_service_remove"
    )

    component.async_register_entity_service(
        SERVICE_EDIT, SCHEMA_EDIT, "async_service_edit"
    )

    async def async_service_add(data):
        # TODO: add validation
        output = dict(data.data)
        output["enabled"] = True

        num = 1
        while entity_exists_in_hass(hass, ENTITY_ID_FORMAT.format("schedule_%i" % num)):
            num = num + 1

        await component.async_add_entities(
            [SchedulerEntity(hass, "schedule_%i" % num, output, True)]
        )

    service.async_register_admin_service(
        hass, DOMAIN, SERVICE_ADD, async_service_add, SCHEMA_ADD
    )

    return True


class SchedulerEntity(ToggleEntity):
    def __init__(self, hass, id, data, is_new_entity=False):
        self.entity_id = ENTITY_ID_FORMAT.format(id)
        self.id = id
        self._properties = data
        self.hass = hass
        self._state = STATE_INITIALIZING
        self._timer = None

        if is_new_entity:
            self.store_entity_state()

    @property
    def should_poll(self):
        return False

    @property
    def name(self):
        return self.id

    @property
    def icon(self):
        return "mdi:calendar-clock"

    @property
    def state(self):
        return self._state

    @property
    def is_on(self):
        """Return true if entity is on."""
        return self._properties["enabled"]

    @property
    def state_attributes(self):
        attributes = {}
        for key, value in self._properties.items():
            if key in EXPOSED_ENTITY_PROPERTIES and value is not None:
                if key == "days":
                    attributes[key] = json.dumps(value)
                else:
                    attributes[key] = value

        return attributes

    def get_service_call(self):
        if not self._properties["service"]:
            return None
        command = {}

        # if service has no domain provided, assume the service is intended for the entity
        if "." in self._properties["service"]:
            command["service"] = self._properties["service"]
        else:
            command["service"] = "%s.%s" % (
                self._properties["entity"].split(".")[0],
                self._properties["service"],
            )
            command["entity_id"] = self._properties["entity"]

        if "service_data" in self._properties:
            service_data = self._properties["service_data"]
            if "entity_id" in service_data:
                command["entity_id"] = service_data["entity_id"]
                del service_data["entity_id"]
            if len(service_data) > 0:
                command["data"] = service_data

        return command

    def validate_configuration(self):
        init = True
        for key, value in self._properties.items():
            if value is None:
                init = False

        if init:
            valid = None
            service_call = self.get_service_call()

            return True

            # temporary bypass of validation --> at startup the services and entities may not been loaded yet, this requires a different approach!
            #
            # if not service_exists_in_hass(self.hass, service_call['service']):
            #     self._state = STATE_INVALID
            # elif 'entity_id' in service_call and not entity_exists_in_hass(self.hass, service_call['entity_id']):
            #     self._state = STATE_INVALID
            # elif time_has_sun(self._properties['time']) and not entity_exists_in_hass(self.hass, SUN_ENTITY):
            #     self._state = STATE_INVALID
            # else:
            #     return True

        return False

    async def async_execute_command(self):
        service_call = self.get_service_call()
        _LOGGER.debug("executing service %s" % service_call["service"])
        await service.async_call_from_config(
            self.hass, service_call,
        )

    async def async_turn_on(self):
        if self._properties["enabled"] == True:
            return
        self._properties["enabled"] = True
        self.store_entity_state()
        await self.async_start_timer()

    async def async_turn_off(self):
        if self._properties["enabled"] == False:
            return
        self._properties["enabled"] = False

        self._state = STATE_DISABLED
        if self._timer:
            self._timer()
            self._timer = None
            self._properties["next_trigger"] = None

        self.store_entity_state()
        await self.async_update_ha_state()

    async def async_service_remove(self):
        _LOGGER.debug("removing entity %s" % self.id)

        self._state = STATE_DISABLED
        if self._timer:
            self._timer()
            self._timer = None
            self._properties["next_trigger"] = None

        await self.async_remove()
        self.hass.components.mqtt.publish(MQTT_STORAGE_TOPIC(self.id), None, None, True)
        return

    async def async_service_edit(self, time=None, days=None):
        if time is not None or days is not None:
            message = {}
            if time is not None:
                self._properties["time"] = time
            if days is not None:
                self._properties["days"] = days

            self.store_entity_state()

            await self.async_start_timer()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        if self.validate_configuration() is True:
            if self._properties["enabled"] is True:
                await self.async_start_timer()
            else:
                self._state = STATE_DISABLED
            # if time_has_sun(self._properties['time']):
            #     #homeassistant.helpers.event.async_track_state_change
            #     #homeassistant.helpers.event.async_track_sunrise

    async def async_will_remove_from_hass(self):
        _LOGGER.debug("async_will_remove_from_hass")

    def store_entity_state(self):
        output = {}
        for key, value in self._properties.items():
            if key in STORED_ENTITY_PROPERTIES and value is not None:
                output[key] = value

        output = json.dumps(output)
        self.hass.components.mqtt.publish(
            MQTT_STORAGE_TOPIC(self.id), output, None, True
        )

    async def async_start_timer(self):
        self._state = STATE_INITIALIZING
        if self._timer:
            self._timer()
            self._timer = None

        time_string = self._properties["time"]

        if time_has_sun(time_string):

            sunrise_sunset, sign, offset_string = parse_sun_time_string(time_string)
            sun_state = self.hass.states.get(SUN_ENTITY)
            if sunrise_sunset == "sunrise":
                time_sun = sun_state.attributes["next_rising"]
            else:
                time_sun = sun_state.attributes["next_setting"]

            time_sun = datetime.datetime.strptime(
                time_sun[: len(time_sun) - 3] + time_sun[len(time_sun) - 2 :],
                "%Y-%m-%dT%H:%M:%S%z",
            )
            # _LOGGER.debug("%s is at: %s" % (sunrise_sunset, dt_util.as_local(time_sun)))

            time_offset = datetime.datetime.strptime(offset_string, "%H:%M")
            time_offset = datetime.timedelta(
                hours=time_offset.hour, minutes=time_offset.minute
            )

            if sign == "+":
                next = time_sun + time_offset
            else:
                next = time_sun - time_offset
        else:
            time = dt_util.parse_time(time_string)
            today = dt_util.start_of_local_day()
            next = dt_util.as_utc(datetime.datetime.combine(today, time))

        # check if time has already passed for today
        now = dt_util.now().replace(microsecond=0)
        delta = next - now
        while delta.total_seconds() < 0:
            next = next + datetime.timedelta(days=1)
            delta = next - now

        # check if timer is restricted in days of the week
        allowed_weekdays = self._properties["days"]
        if len(allowed_weekdays) > 0:
            weekday = (dt_util.as_local(next).weekday() + 1) % 7
            while weekday not in allowed_weekdays:
                next = next + datetime.timedelta(days=1)
                weekday = (
                    dt_util.as_local(next).weekday() + 1
                ) % 7  # convert to Sunday=0, Saturday=6

        next_localized = dt_util.as_local(next)

        self._properties["next_trigger"] = next_localized.isoformat()
        self._state = STATE_WAITING

        self._timer = async_track_point_in_utc_time(
            self.hass, self.async_timer_finished, next
        )

        _LOGGER.debug("timer for %s triggers in %s" % (self.entity_id, (next - now)))
        await self.async_update_ha_state()

    async def async_timer_finished(self, time):
        self._timer = None

        if self._state != STATE_WAITING:
            return

        _LOGGER.debug("timer for %s is triggered" % self.entity_id)

        self._state = STATE_TRIGGERED
        self._properties["next_trigger"] = None
        await self.async_update_ha_state()

        # execute the action
        await self.async_execute_command()

        # wait 1 minute before restarting
        now = dt_util.now().replace(microsecond=0)
        next = now + datetime.timedelta(minutes=1)

        self._timer = async_track_point_in_utc_time(
            self.hass, self.async_cooldown_timer_finished, next
        )

    async def async_cooldown_timer_finished(self, time):
        _LOGGER.debug("async_cooldown_timer_finished")
        self._timer = None

        if self._state != STATE_TRIGGERED:
            return

        await self.async_start_timer()
