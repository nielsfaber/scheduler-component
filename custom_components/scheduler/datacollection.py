import logging
import re
import datetime
from functools import reduce

import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

EntryPattern = re.compile("^D([0-9]+)T([0-9SR]+)T?([0-9SR]+)?([A0-9]+)$")

FixedTimePattern = re.compile("^([0-9]{2})([0-9]{2})$")
SunTimePattern = re.compile(
    "^(([0-9]{2})([0-9]{2}))?(S[SR])(([0-9]{2})([0-9]{2}))?$"
)

from .helpers import calculate_next_start_time, is_between_start_time_and_end_time, timedelta_to_string


class DataCollection:
    """Defines a base schedule entity."""

    def __init__(self):
        self.entries = []
        self.actions = []

    def import_from_service(self, data: dict):
        for action in data["actions"]:
            service = action["service"]
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

            my_action = {"service": "{}.{}".format(domain, service)}

            if entity is not None:
                my_action["entity"] = entity

            for arg in service_data.keys():
                my_action[arg] = service_data[arg]

            self.actions.append(my_action)
        
        def import_time_input(input):
            res = {}
            if type(input) is datetime.time:
                res["at"] = input.strftime("%H:%M")
            else:
                res["event"] = input["event"]
                res["offset"] = timedelta_to_string(input["offset"])
            return res

        for entry in data["entries"]:
            my_entry = {}

            if "time" in entry:
                my_entry["time"] = import_time_input(entry["time"])

            if "end_time" in entry:
                my_entry["end_time"] = import_time_input(entry["end_time"])

            if "days" in entry:
                my_entry["days"] = entry["days"]
                my_entry["days"].sort()
            else:
                my_entry["days"] = [0]

            my_entry["actions"] = entry["actions"]

            self.entries.append(my_entry)

    def get_next_entry(self, sun_data=None):
        """Find the closest timer from now"""

        now = dt_util.now().replace(microsecond=0)
        timestamps = []

        for entry in self.entries:
            next_time = calculate_next_start_time(entry, sun_data)
            timestamps.append(next_time)

        closest_timestamp = reduce(
            lambda x, y: x if (x - now) < (y - now) else y, timestamps
        )

        for i in range(len(timestamps)):
            if timestamps[i] == closest_timestamp:
                return i

    def has_overlapping_timeslot(self, sun_data=None):
        """Check if there are timeslots which overlapping with now"""

        now = dt_util.now().replace(microsecond=0)

        for i in range(len(self.entries)):
            entry = self.entries[i]
            if "end_time" in entry and is_between_start_time_and_end_time(entry, sun_data):
                return i, True

        return None, False

    def get_timestamp_for_entry(self, entry, sun_data):
        """Get a timestamp for a specific entry"""
        entry = self.entries[entry]
        return calculate_next_start_time(entry, sun_data)

    def get_service_calls_for_entry(self, entry):
        """Get the service call (action) for a specific entry"""
        calls = []
        actions = self.entries[entry]["actions"]
        for action in actions:
            if len(self.actions) > action:
                action_data = self.actions[action]
                call = {"service": action_data["service"]}
                domain = action_data["service"].split(".").pop(0)
                if "entity" in action_data:
                    call["entity_id"] = "{}.{}".format(
                        domain, action_data["entity"]
                    )
                for attr in action_data:
                    if attr == "service" or attr == "entity":
                        continue
                    if not "data" in call:
                        call["data"] = {}
                    call["data"][attr] = action_data[attr]

                calls.append(call)

        return calls

    def import_data(self, data):
        """Import datacollection from restored entity"""
        if not "actions" in data or not "entries" in data:
            _LOGGER.debug("failed to import data")
            return

        self.actions = data["actions"]

        def import_time_input(time_str):
            fixed_time_pattern = FixedTimePattern.match(time_str)
            sun_time_pattern = SunTimePattern.match(time_str)
            res = {}

            if fixed_time_pattern:
                res["at"] = "{}:{}".format(
                    fixed_time_pattern.group(1),
                    fixed_time_pattern.group(2),
                )
            elif sun_time_pattern:
                res["event"] = (
                    "sunrise"
                    if sun_time_pattern.group(4) == "SR"
                    else "sunset"
                )

                if (
                    sun_time_pattern.group(1) is not None
                ):  # negative offset
                    res["offset"] = "-{}:{}".format(
                        sun_time_pattern.group(2),
                        sun_time_pattern.group(3),
                    )
                else:
                    res["offset"] = "+{}:{}".format(
                        sun_time_pattern.group(6),
                        sun_time_pattern.group(7),
                    )
            else:
                _LOGGER.debug("failed to parse time {}".format(time_str))
            return res
                

        for entry in data["entries"]:
            res = EntryPattern.match(entry)

            if not res:
                return False

            my_entry = {}

            my_entry["time"] = import_time_input(str(res.group(2)))
            if res.group(3):
                my_entry["end_time"] = import_time_input(str(res.group(3)))

            days_list = list(res.group(1))
            days_list = [int(i) for i in days_list]
            my_entry["days"] = days_list

            action_list = res.group(4).split("A")
            action_list = list(filter(None, action_list))
            action_list = [int(i) for i in action_list]
            my_entry["actions"] = action_list

            self.entries.append(my_entry)

        return True

    def export_data(self):
        output = {"entries": [], "actions": self.actions}

        def export_time(entry_time):
            if "at" in entry_time:
                time_str = entry_time["at"].replace(":", "")
            elif "event" in entry_time:
                event_string = (
                    "SR" if entry_time["event"] == "sunrise" else "SS"
                )

                if "+" in entry_time["offset"]:
                    time_str = "{}{}".format(
                        event_string,
                        entry_time["offset"].replace("+", "").replace(":", ""),
                    )
                else:
                    time_str = "{}{}".format(
                        entry_time["offset"].replace("-", "").replace(":", ""),
                        event_string,
                    )
            else:
                _LOGGER.debug("failed to parse time object")
                _LOGGER.debug(entry_time)
                return ""
            return time_str


        for entry in self.entries:
            time_string = export_time(entry["time"])
            end_time_string = export_time(entry["end_time"]) if "end_time" in entry else None

            days_arr = [str(i) for i in entry["days"]]
            days_string = "".join(days_arr)
            action_arr = [str(i) for i in entry["actions"]]
            action_string = "A".join(action_arr)

            entry_str = ""
            entry_str += "D{}".format(days_string)
            entry_str += "T{}".format(time_string)
            if end_time_string:
                entry_str += "T{}".format(end_time_string)
            entry_str += "A{}".format(action_string)

            output["entries"].append(entry_str)

        return output
