import logging
import re
import datetime
import homeassistant.util.dt as dt_util
from functools import reduce
import math

_LOGGER = logging.getLogger(__name__)

EntryPattern = re.compile('^D([0-9]+)T([0-9\+\-SR]+)([A0-9]+)$')

FixedTimePattern = re.compile('^([0-9]{2})([0-9]{2})$')
SunTimePattern = re.compile('^(S[SR])([\+\-])([0-9]+)$')

from .helpers import (
    calculate_datetime,
)

class DataCollection:
    """Defines a base schedule entity."""

    def __init__(self):
        self.entries = []
        self.actions = []
        _LOGGER.debug("__init__")


    def import_from_service(self, data: dict):
        _LOGGER.debug("import_from_service")
        _LOGGER.debug(data)

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
                my_entry["time"] = entry['time']
            else:
                my_entry["event"] = entry['event']
                my_entry["offset"] = entry['offset']

            if "days" in my_entry:
                my_entry["days"] = my_entry['days']
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
        self.actions = data["actions"]

        for entry in data["entries"]:
            res = EntryPattern.match(entry)

            if not res:
                return False
            
            my_entry = {  }

            time_str = res.group(2)
            is_fixed_time = FixedTimePattern.match(time_str)
            is_sun_time = SunTimePattern.match(time_str)

            if is_fixed_time:
                time_str = "{}:{}".format(is_fixed_time.group(1), is_fixed_time.group(2))
                my_entry["time"] = dt_util.parse_time(time_str)
            elif is_sun_time:                
                my_entry["event"] = "sunrise" if is_sun_time.group(1) == "SR" else "sunset"

                offset_string = is_sun_time.group(3)
                time_offset = datetime.datetime.strptime(offset_string, "%H%M")
                time_offset = datetime.timedelta(
                    hours=time_offset.hour, minutes=time_offset.minute
                )
                if is_sun_time.group(2) == "-":
                    time_offset = -time_offset
                my_entry["offset"] = time_offset
            
            
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
                time = "{}{}".format(str(entry["time"].hour).zfill(2), str(entry["time"].minute).zfill(2))
            else:
                offset_time = entry["offset"].total_seconds()
                if offset_time >= 0:
                    offset_hours = math.floor(offset_time/3600)
                    offset_mins = math.floor(offset_time/60-offset_hours*60)
                    offset_hours = "+{}".format(str(abs(offset_hours)).zfill(2))
                    offset_mins = str(offset_mins).zfill(2)
                else:
                    offset_hours = math.ceil(offset_time/3600)
                    offset_mins = math.floor(offset_time/60-offset_hours*60)
                    offset_hours = "-{}".format(str(abs(offset_hours)).zfill(2))
                    offset_mins = str(abs(offset_mins)).zfill(2)

                offset_time = "{}{}".format(offset_hours,offset_mins)
                if entry["event"] == "sunrise":
                    time = "SR{}".format(offset_time)
                else:
                    time = "SS{}".format(offset_time)

            days_arr = [str(i) for i in entry["days"]] 
            days_string = "".join(days_arr)
            action_arr = [str(i) for i in entry["actions"]] 
            action_string = "A".join(action_arr)
            
            output["entries"].append("D{}T{}A{}".format(days_string, time, action_string))

        return output