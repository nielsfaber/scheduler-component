import logging
import re
import datetime
import homeassistant.util.dt as dt_util
from functools import reduce

_LOGGER = logging.getLogger(__name__)

EntryPattern = re.compile('^D([0-9]+)T([0-9\+]+)([A0-9]+)$')

def get_timestamp_from_entry(entry):
    now = dt_util.now().replace(microsecond=0)
    today = dt_util.start_of_local_day()

    time_str = entry["time"]
    time_str = time_str[:2] + ":" + time_str[2:]
    time = dt_util.parse_time(time_str)

    nexttime = dt_util.as_utc(datetime.datetime.combine(today, time))

    # check if time has already passed for today
    delta = nexttime - now
    while delta.total_seconds() < 0:
        nexttime = nexttime + datetime.timedelta(days=1)
        delta = nexttime - now

    # check if timer is restricted in days of the week
    allowed_weekdays = entry["days"]
    if len(allowed_weekdays) > 0 and not 0 in allowed_weekdays:
        weekday = dt_util.as_local(nexttime).isoweekday()
        while weekday not in allowed_weekdays:
            nexttime = nexttime + datetime.timedelta(days=1)
            weekday = dt_util.as_local(nexttime).isoweekday()

    return nexttime

class DataCollection:
    """Defines a base schedule entity."""

    def __init__(self):
        self.entries = []
        self.actions = []
        _LOGGER.debug("__init__")


    def import_from_service(self, data: dict):

        service = data['service']
        service_data = {}
        entity = None
        domain = None

        if "." in service:
            domain = service.split(".").pop(0)
            service = service.split(".").pop(1)

        if "service_data" in data and data["service_data"]:
            _LOGGER.debug(data["service_data"])
            service_data = data["service_data"]
            if "entity_id" in service_data:
                entity = service_data["entity_id"]
                del service_data["entity_id"]
        
        if "entity" in data and entity is None:
            entity = data["entity"]
        
        if entity is not None:
            entity_domain = entity.split(".").pop(0)
            if domain is None:
                domain = entity_domain
            
            if domain == entity_domain:
                entity = entity.split(".").pop(1)
    
        action = {}

        action["service"] = "{}.{}".format(domain, service)

        if entity is not None:
            action["entity"] = entity

        for arg in service_data.keys():
            action[arg] = service_data[arg]

        self.actions.append(action)

        days = data['days']
        days.sort()
        time = data['time']
        time = time.replace(':', '')

        for day in days:
            self.entries.append({
                "days": days,
                "time": time,
                "actions": [0] 
            })
        
        next_entry = self.get_next_entry()

    def get_next_entry(self):
        """Find the closest timer from now"""
        
        now = dt_util.now().replace(microsecond=0)
        timestamps = []

        for entry in self.entries:
            next_time = get_timestamp_from_entry(entry)
            timestamps.append(next_time)
        
        closest_timestamp = reduce(lambda x, y: x if (x-now) < (y-now) else y, timestamps)
        for i in range(len(timestamps)):
            if timestamps[i] == closest_timestamp:
                return i

    def import_data(self, data):
        """Import datacollection from restored entity"""

        self.actions = data["actions"]

        for entry in data["entries"]:
            res = EntryPattern.findall(entry)

            days_list = list(res[0][0])
            days_list = [int(i) for i in days_list] 

            action_list = res[0][2].split("A")
            action_list = list(filter(None, action_list))
            action_list = [int(i) for i in action_list] 

            self.entries.append({
                "days": days_list,
                "time": res[0][1],
                "actions": action_list,
            })
        
        next_entry = self.get_next_entry()

    def export_data(self):
        output = {
            "entries": [],
            "actions": self.actions
        }

        for entry in self.entries:
            days_arr = [str(i) for i in entry["days"]] 
            days_string = "".join(days_arr)
            action_arr = [str(i) for i in entry["actions"]] 
            action_string = "A".join(action_arr)
            
            output["entries"].append("D{}T{}A{}".format(days_string, entry["time"], action_string))
            
        return output