import logging
import re
import datetime
import homeassistant.util.dt as dt_util
from functools import reduce

_LOGGER = logging.getLogger(__name__)

EntryPattern = re.compile('^D([0-9]+)T([0-9SR]+)([A0-9]+)$')

FixedTimePattern = re.compile('^([0-9]{2})([0-9]{2})$')
SunTimePattern = re.compile('^(([0-9]{2})([0-9]{2}))?(S[SR])(([0-9]{2})([0-9]{2}))?$')

from .helpers import (
    calculate_datetime,
    timedelta_to_string
)

class DataCollection:
    """Defines a base schedule entity."""

    def __init__(self):
        self.entries = []
        self.actions = []


    def import_from_service(self, data: dict):
        for action in data["actions"]:
            service = action['service']
            service_data = {}
            entity = None
            domain = None

            if "." in service:
                domain = service.split(".").pop(0)
                service = service.split(".").pop(1)

            if "service_data" in action:
                service_data = action["service_data"]
                if "entity_id" in service_data:
                    entity = service_data["entity_id"]
                    del service_data["entity_id"]
        
            if "entity" in action and entity is None:
                entity = action["entity"]
        
            if entity is not None:
                entity_domain = entity.split(".").pop(0)
                if domain is None:
                    domain = entity_domain
                
                if domain == entity_domain:
                    entity = entity.split(".").pop(1)
    
            my_action = {
                "service": "{}.{}".format(domain, service)
            }

            if entity is not None:
                my_action["entity"] = entity

            for arg in service_data.keys():
                my_action[arg] = service_data[arg]

            self.actions.append(my_action)

        for entry in data["entries"]:
            my_entry = { }
            if "time" in entry:
                my_entry["time"] = entry["time"].strftime("%H:%M")
            else:
                my_entry["event"] = entry['event']
                my_entry["offset"] = timedelta_to_string(entry['offset'])

            if "days" in entry:
                my_entry["days"] = entry['days']
                my_entry["days"].sort()
            else:
                my_entry["days"] = [0]

            my_entry["actions"] = entry["actions"]
            self.entries.append(my_entry)

    def get_next_entry(self, sun_data = None):
        """Find the closest timer from now"""

        now = dt_util.now().replace(microsecond=0)
        timestamps = []

        for entry in self.entries:
            next_time = calculate_datetime(entry, sun_data)
            timestamps.append(next_time)
        
        closest_timestamp = reduce(lambda x, y: x if (x-now) < (y-now) else y, timestamps)
        for i in range(len(timestamps)):
            if timestamps[i] == closest_timestamp:
                return i

    def get_timestamp_for_entry(self, entry, sun_data):
        """Get a timestamp for a specific entry"""
        entry = self.entries[entry]
        return calculate_datetime(entry, sun_data)

    def get_service_calls_for_entry(self, entry):
        """Get the service call (action) for a specific entry"""
        calls = []
        actions = self.entries[entry]["actions"]
        for action in actions:
            if len(self.actions) > action:
                action_data = self.actions[action]
                call = {
                    "service": action_data["service"]
                }
                domain = action_data["service"].split(".").pop(0)
                if "entity" in action_data: call["entity_id"] = "{}.{}".format(domain,action_data["entity"])
                for attr in action_data:
                    if attr == "service" or attr == "entity": continue
                    if not "data" in call: call["data"] = {}
                    call["data"][attr] = action_data[attr]

                calls.append(call)

        return calls

    def import_data(self, data):
        """Import datacollection from restored entity"""
        if(not "actions" in data or not "entries" in data):
            _LOGGER.debug("failed to import data")
            return

        self.actions = data["actions"]

        for entry in data["entries"]:
            res = EntryPattern.match(entry)

            if not res:
                return False
            
            my_entry = {  }

            time_str = res.group(2)
            fixed_time_pattern = FixedTimePattern.match(time_str)
            sun_time_pattern = SunTimePattern.match(time_str)

            if fixed_time_pattern:
                my_entry["time"] = "{}:{}".format(fixed_time_pattern.group(1), fixed_time_pattern.group(2))
            elif sun_time_pattern:
                my_entry["event"] = "sunrise" if sun_time_pattern.group(4) == "SR" else "sunset"

                if sun_time_pattern.group(1) is not None: # negative offset
                    my_entry["offset"] = "-{}:{}".format(sun_time_pattern.group(2), sun_time_pattern.group(3))
                else:
                    my_entry["offset"] = "+{}:{}".format(sun_time_pattern.group(6), sun_time_pattern.group(7))

            days_list = list(res.group(1))
            days_list = [int(i) for i in days_list] 
            my_entry["days"] = days_list

            action_list = res.group(3).split("A")
            action_list = list(filter(None, action_list))
            action_list = [int(i) for i in action_list]
            my_entry["actions"] = action_list

            self.entries.append(my_entry)

        return True

    def export_data(self):
        output = {
            "entries": [],
            "actions": self.actions
        }

        for entry in self.entries:
            if "time" in entry:
                time = entry["time"].replace(":", "")
            else:
                event_string = "SR" if entry["event"] == "sunrise" else "SS"

                if "+" in entry["offset"]:
                    time = "{}{}".format(event_string, entry["offset"].replace("+", "").replace(":", ""))
                else:
                    time = "{}{}".format(entry["offset"].replace("-", "").replace(":", ""), event_string)

            days_arr = [str(i) for i in entry["days"]] 
            days_string = "".join(days_arr)
            action_arr = [str(i) for i in entry["actions"]] 
            action_string = "A".join(action_arr)
            
            output["entries"].append("D{}T{}A{}".format(days_string, time, action_string))

        return output