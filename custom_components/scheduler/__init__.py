import logging
import voluptuous as vol
import json
from homeassistant.helpers.json import JSONEncoder
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.entity import (
    ToggleEntity,
    Entity
)
from homeassistant.util import convert, dt as dt_util, location as loc_util
from datetime import datetime
from homeassistant.helpers import (
    config_validation as cv,
    service,
)
from homeassistant.const import (
    ATTR_ENTITY_ID
)
from homeassistant.helpers.event import async_track_state_change

from .const import (
    DOMAIN, 
    STATE_INITIALIZING, STATE_WAITING, STATE_TRIGGERED, STATE_DISABLED, STATE_INVALID,
    SERVICE_TURN_ON, SERVICE_TURN_OFF, SERVICE_TEST, SERVICE_REMOVE, SERVICE_EDIT, SERVICE_ADD,
    SCHEMA_ENTITY, SCHEMA_EDIT, SCHEMA_ADD,
    MQTT_DISCOVERY_RESPONSE_TOPIC, MQTT_DISCOVERY_REQUEST_TOPIC, MQTT_DISCOVERY_REQUEST_PAYLOAD,
    MQTT_AVAILABILITY_TOPIC, MQTT_AVAILABILITY_PAYLOAD,
    MQTT_INITIALIZATION_REQUEST_TOPIC, MQTT_INITIALIZATION_REQUEST_PAYLOAD, MQTT_INITIALIZATION_RESPONSE_TOPIC,
    MQTT_TURN_ON_TOPIC, MQTT_TURN_ON_PAYLOAD,
    MQTT_TURN_OFF_TOPIC, MQTT_TURN_OFF_PAYLOAD,
    MQTT_REMOVE_TOPIC, MQTT_REMOVE_PAYLOAD,
    MQTT_ADD_TOPIC, MQTT_EDIT_TOPIC,
    INITIAL_ENTITY_PROPERTIES, EXPOSED_ENTITY_PROPERTIES, LISTENING_ENTITY_PROPERTIES,
    SUN_ENTITY, MQTT_SUNRISE_TOPIC, MQTT_SUNSET_TOPIC,
)

from .helpers import (
    get_id_from_topic,
    entity_exists_in_hass,
    service_exists_in_hass,
)

_LOGGER = logging.getLogger(__name__)

ENTITY_ID_FORMAT = DOMAIN + '.{}'
DEPENDENCIES = ["mqtt"]

async def async_setup(hass, config):
    mqtt = hass.components.mqtt
    component = EntityComponent(_LOGGER, DOMAIN, hass)
    _LOGGER.debug("setting up scheduler component")

    async def async_handle_discovery(msg):
        entity_id = get_id_from_topic(msg.topic)

        if entity_id is None:
            return
        elif entity_exists_in_hass(hass, entity_id):
            return
        
        _LOGGER.debug("discovered entitity %s" % entity_id)
        await component.async_add_entities([
            SchedulerRule(
                hass,
                entity_id
            )
        ])

    await mqtt.async_subscribe(MQTT_DISCOVERY_RESPONSE_TOPIC, async_handle_discovery)
    mqtt.publish(MQTT_DISCOVERY_REQUEST_TOPIC, MQTT_DISCOVERY_REQUEST_PAYLOAD)


    component.async_register_entity_service(
        SERVICE_TURN_ON,
        SCHEMA_ENTITY,
        'async_turn_on'
    )

    component.async_register_entity_service(
        SERVICE_TURN_OFF,
        SCHEMA_ENTITY,
        'async_turn_off'
    )

    component.async_register_entity_service(
        SERVICE_TEST,
        SCHEMA_ENTITY,
        'async_service_test'
    )

    component.async_register_entity_service(
        SERVICE_REMOVE,
        SCHEMA_ENTITY,
        'async_service_remove'
    )

    component.async_register_entity_service(
        SERVICE_EDIT,
        SCHEMA_EDIT,
        'async_service_edit'
    )

    async def async_service_add(data):
        # TODO: add validation
        output = dict(data.data)
        mqtt.publish(MQTT_ADD_TOPIC, json.dumps(output))
    
    service.async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_ADD,
        async_service_add,
        SCHEMA_ADD
    )

    async def update_sun(sun_entity, old_state, new_state):
        _LOGGER.debug("The sun entity has changed")
        next_rising = new_state.attributes["next_rising"]
        next_setting = new_state.attributes["next_setting"]
        
        mqtt.publish(MQTT_SUNRISE_TOPIC, next_rising, None, True)
        mqtt.publish(MQTT_SUNSET_TOPIC, next_setting, None, True)


    if entity_exists_in_hass(hass, SUN_ENTITY):

        async_track_state_change(
            hass,
            SUN_ENTITY,
            update_sun
        )

        # state = hass.states.get(SUN_ENTITY)
        # next_rising = state.attributes["next_rising"]
        # next_setting = state.attributes["next_setting"]
        
        # mqtt.publish(MQTT_SUNRISE_TOPIC, next_rising)
        # mqtt.publish(MQTT_SUNSET_TOPIC, next_setting)
        




    return True


class SchedulerRule(ToggleEntity):
    def __init__(self, hass, id):
        self.entity_id = ENTITY_ID_FORMAT.format(id)
        self.id = id
        self._properties = INITIAL_ENTITY_PROPERTIES.copy()
        self.hass = hass
        self._available = None
        self._initialized = False
        self._valid = False
        self.relative_time = None

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
        if not self._initialized:
            return STATE_INITIALIZING
        elif not self._valid:
            return STATE_INVALID
        elif self._properties['enabled'] != 'true':
            return STATE_DISABLED
        elif self._properties['triggered'] == 'true':
            return STATE_TRIGGERED
        else:
            return STATE_WAITING
        # elif self.relative_time is not None:
        #     return "waiting (%s)" % self.relative_time

    @property
    def available(self):
        return (self._available == True)

    @property
    def is_on(self):
        """Return true if entity is on."""
        return (self._properties['enabled'] == 'true')

    @property
    def state_attributes(self):
        attributes = {}
        for key,value in self._properties.items():
            if key in EXPOSED_ENTITY_PROPERTIES and value is not None:
                attributes[key] = value
        
        return attributes

    def request_configuration(self):
        _LOGGER.debug("Requesting configuration for entity %s" % self.id)
        self.hass.components.mqtt.publish(MQTT_INITIALIZATION_REQUEST_TOPIC(self.id), MQTT_INITIALIZATION_REQUEST_PAYLOAD)
        # TODO clean up old entities

    def get_service_call(self):
        if not self._initialized:
            return None
        command = { }

        if "." in self._properties["service"]:
            command["service"] = self._properties["service"]
        else:
            command["service"] = "%s.%s" % (self._properties["entity"].split(".")[0], self._properties["service"])
            command["entity_id"] = self._properties["entity"]
        
        if "service_data" in self._properties:
            service_data = json.loads(self._properties["service_data"])
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
            
            self._initialized = init

            if init:
                valid = None
                service_call = self.get_service_call()
                _LOGGER.debug(service_call)
                if not service_exists_in_hass(self.hass, service_call['service']):
                    valid = False
                elif 'entity_id' in service_call and not entity_exists_in_hass(self.hass, service_call['entity_id']):
                    valid = False
                else: 
                    valid = True
                self._valid = valid
        
    async def async_execute_command(self):
        service_call = self.get_service_call()
        await service.async_call_from_config(
            self.hass,
            service_call,
        )
        _LOGGER.debug("executed service %s" % service_call["service"])


    async def async_handle_availability(self, msg):
        available = (msg.payload == MQTT_AVAILABILITY_PAYLOAD)

        if available is not self._available:
            if not available:
                self._properties = INITIAL_ENTITY_PROPERTIES.copy()
                self.validate_configuration()
            elif self._available == False:
                self.request_configuration()

            self._available = available
            await self.async_update_ha_state()

    async def handle_input_data(self, msg):
        parts = msg.topic.split('/')
        key = parts[-1]

        if key in LISTENING_ENTITY_PROPERTIES:
            self._properties[key] = msg.payload
            self.validate_configuration()

            # if key == 'next_trigger':
            #     ts = datetime.strptime(self._properties['next_trigger'], "%Y-%m-%dT%H:%M:%S.%fZ")
            #     now = datetime.utcnow()

            #     if not ts.tzinfo:
            #         ts = dt_util.as_local(ts)
                
            #     if not now.tzinfo:
            #         now = dt_util.as_local(now)
                
            #     time_from_now = ts-now
            #     ts_inverted = now - time_from_now
            #     self.relative_time = dt_util.get_age(ts_inverted)

            if key == 'triggered':
                if self._properties['triggered'] == 'true':
                    _LOGGER.debug("triggered entity %s" % self.id)
                    await self.async_execute_command()


            await self.async_update_ha_state()
        elif key == 'removed':
            _LOGGER.debug("removing entity %s" % self.id)
            await self.async_remove()

           

    async def async_turn_on(self):
        self.hass.components.mqtt.publish(MQTT_TURN_ON_TOPIC(self.id), MQTT_TURN_ON_PAYLOAD)

    async def async_turn_off(self):
        self.hass.components.mqtt.publish(MQTT_TURN_OFF_TOPIC(self.id), MQTT_TURN_OFF_PAYLOAD)
    
    async def async_service_remove(self):
        self.hass.components.mqtt.publish(MQTT_REMOVE_TOPIC(self.id), MQTT_REMOVE_PAYLOAD)

    async def async_service_test(self):
            _LOGGER.debug("testing entity %s" % self.id)
            await self.async_execute_command()

    async def async_service_edit(self, time=None, days=None):
        if time is not None or days is not None:
            message = { }
            if time is not None:
                message['time'] = time
            if days is not None:
                message['days'] = days
            
            self.hass.components.mqtt.publish(MQTT_EDIT_TOPIC(self.id), json.dumps(message))


    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        await self.hass.components.mqtt.async_subscribe(MQTT_AVAILABILITY_TOPIC, self.async_handle_availability)
        await self.hass.components.mqtt.async_subscribe(MQTT_INITIALIZATION_RESPONSE_TOPIC(self.id), self.handle_input_data)
        self.request_configuration()

    async def async_will_remove_from_hass(self):
        _LOGGER.debug("async_will_remove_from_hass")
    




