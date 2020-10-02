import datetime
import logging
import re
from functools import reduce

import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

EntryPattern = re.compile(
    "^([0-9]+)?D([0-9]+)?T([0-9SRDUW]+)T?([0-9SRDUW]+)?A([A0-9]+)+(C([C0-9]+))?$"
)

FixedTimePattern = re.compile("^([0-9]{2})([0-9]{2})$")
SunTimePattern = re.compile(
    "^(([0-9]{2})([0-9]{2}))?([SRDUW]{2})(([0-9]{2})([0-9]{2}))?$"
)

from .const import (
    CONDITION_TYPE_AND,
    CONDITION_TYPE_OR,
    DAY_TYPE_CUSTOM,
    DAY_TYPE_DAILY,
    DAY_TYPE_WEEKEND,
    DAY_TYPE_WORKDAY,
    ENTRY_PATTERN_DAILY,
    ENTRY_PATTERN_DAWN,
    ENTRY_PATTERN_DUSK,
    ENTRY_PATTERN_SUNRISE,
    ENTRY_PATTERN_SUNSET,
    ENTRY_PATTERN_WEEKEND,
    ENTRY_PATTERN_WORKDAY,
    MATCH_TYPE_ABOVE,
    MATCH_TYPE_BELOW,
    MATCH_TYPE_EQUAL,
    MATCH_TYPE_UNEQUAL,
    TIME_EVENT_DAWN,
    TIME_EVENT_DUSK,
    TIME_EVENT_SUNRISE,
    TIME_EVENT_SUNSET,
)
from .helpers import (
    calculate_next_start_time,
    is_between_start_time_and_end_time,
    parse_iso_timestamp,
    timedelta_to_string,
)


class DataCollection:
    """Defines a base schedule entity."""

    def __init__(self):
        self.entries = []
        self.actions = []
        self.conditions = []
        self.name = None
        self.icon = None
        self.sun_data = None
        self.workday_data = None

    def import_from_service(self, data: dict):
        for action in data["actions"]:
            service = action["service"]
            service_data = {}
            entity = None
            domain = None

            if "service_data" in action:
                service_data = action["service_data"]
                if "entity_id" in service_data:
                    entity = service_data["entity_id"]
                    del service_data["entity_id"]

            if "entity" in action and entity is None:
                entity = action["entity"]

            if entity is not None:
                entity_domain = entity.split(".").pop(0)
                service_domain = service.split(".").pop(0)
                if entity_domain is None:
                    entity = "{}.{}".format(service_domain, entity)
                elif entity_domain == service_domain:
                    service = service.split(".").pop(1)

            my_action = {"service": service}

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
                my_entry["days"] = {}
                my_entry["days"]["type"] = entry["days"]["type"]

                if entry["days"]["type"] == DAY_TYPE_CUSTOM:
                    if not "list" in entry["days"]:
                        my_entry["days"] = {"type": DAY_TYPE_DAILY}
                    else:
                        days_list = entry["days"]["list"]
                        if len(days_list) == 1 and days_list[0] == 0:
                            my_entry["days"] = {"type": DAY_TYPE_DAILY}
                        else:
                            days_list.sort()
                            my_entry["days"]["list"] = days_list
            else:
                my_entry["days"] = {"type": DAY_TYPE_DAILY}

            my_entry["actions"] = entry["actions"]

            if "conditions" in entry:
                my_entry["conditions"] = entry["conditions"]

            self.entries.append(my_entry)

        if "name" in data:
            self.name = data["name"]

        if "conditions" in data:
            self.conditions = data["conditions"]

    def get_next_entry(self):
        """Find the closest timer from now"""

        now = dt_util.now().replace(microsecond=0)
        timestamps = []

        for entry in self.entries:
            next_time = calculate_next_start_time(
                entry, self.sun_data, self.workday_data
            )
            timestamps.append(next_time)

        closest_timestamp = reduce(
            lambda x, y: x if (x - now) < (y - now) else y, timestamps
        )

        for i in range(len(timestamps)):
            if timestamps[i] == closest_timestamp:
                return i

    def has_overlapping_timeslot(self):
        """Check if there are timeslots which overlapping with now"""

        now = dt_util.now().replace(microsecond=0)

        for i in range(len(self.entries)):
            entry = self.entries[i]
            if "end_time" in entry and is_between_start_time_and_end_time(
                entry, self.sun_data, self.workday_data
            ):
                return i, True

        return None, False

    def get_timestamp_for_entry(self, entry, sun_data=None, workday_data=None):
        """Get a timestamp for a specific entry"""
        if not sun_data:
            sun_data = self.sun_data
        if not workday_data:
            workday_data = self.workday_data
        entry = self.entries[entry]
        return calculate_next_start_time(entry, sun_data, workday_data)

    def get_service_calls_for_entry(self, entry):
        """Get the service call (action) for a specific entry"""
        calls = []
        actions = self.entries[entry]["actions"]
        for action in actions:
            if len(self.actions) > action:
                action_data = self.actions[action]
                call = {"service": action_data["service"]}

                if "entity" in action_data:
                    call["entity_id"] = action_data["entity"]

                if not "." in call["service"]:
                    domain = call["entity_id"].split(".").pop(0)
                    call["service"] = "{}.{}".format(domain, call["service"])
                elif "entity_id" in call and not "." in call["entity_id"]:
                    domain = call["service"].split(".").pop(0)
                    call["entity_id"] = "{}.{}".format(domain, call["entity_id"])

                if (
                    "entity_id" in action_data
                ):  # overwrite the default entity if it is provided
                    call["entity_id"] = action_data["entity_id"]

                for attr in action_data:
                    if attr == "service" or attr == "entity" or attr == "entity_id":
                        continue
                    if not "data" in call:
                        call["data"] = {}
                    call["data"][attr] = action_data[attr]

                calls.append(call)

        return calls

    def import_data(self, data):
        """Import datacollection from restored entity"""
        if not "actions" in data or not "entries" in data:
            return False

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
                if sun_time_pattern.group(4) == ENTRY_PATTERN_SUNRISE:
                    res["event"] = TIME_EVENT_SUNRISE
                elif sun_time_pattern.group(4) == ENTRY_PATTERN_SUNSET:
                    res["event"] = TIME_EVENT_SUNSET
                elif sun_time_pattern.group(4) == ENTRY_PATTERN_DAWN:
                    res["event"] = TIME_EVENT_DAWN
                elif sun_time_pattern.group(4) == ENTRY_PATTERN_DUSK:
                    res["event"] = TIME_EVENT_DUSK

                if sun_time_pattern.group(1) is not None:  # negative offset
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
                raise Exception("failed to parse time {}".format(time_str))
            return res

        for entry in data["entries"]:
            res = EntryPattern.match(entry)

            if not res:
                return False

            # split the entry string in parts
            days_setting = res.group(1)
            days_list = res.group(2)
            time_str = res.group(3)
            end_time_str = res.group(4)
            action_list = res.group(5).split("A")
            condition_list = res.group(7)

            my_entry = {}

            # parse days
            my_entry["days"] = {}
            if days_setting:
                if days_setting == ENTRY_PATTERN_DAILY:
                    my_entry["days"]["type"] = DAY_TYPE_DAILY
                elif days_setting == ENTRY_PATTERN_WORKDAY:
                    my_entry["days"]["type"] = DAY_TYPE_WORKDAY
                elif days_setting == ENTRY_PATTERN_WEEKEND:
                    my_entry["days"]["type"] = DAY_TYPE_WEEKEND
                else:
                    my_entry["days"]["type"] = DAY_TYPE_CUSTOM

            elif days_list:
                days_list = list(res.group(2))
                days_list = [int(i) for i in days_list]
                if (
                    len(days_list) == 1 and days_list[0] == 0
                ):  # for backwards compatibility
                    my_entry["days"]["type"] = DAY_TYPE_DAILY
                else:
                    my_entry["days"]["type"] = DAY_TYPE_CUSTOM
                    my_entry["days"]["list"] = days_list

            # parse time
            my_entry["time"] = import_time_input(str(time_str))
            if end_time_str:
                my_entry["end_time"] = import_time_input(str(end_time_str))

            # parse action
            action_list = list(filter(None, action_list))
            action_list = [int(i) for i in action_list]
            my_entry["actions"] = action_list

            # parse condition
            if condition_list:
                my_entry["conditions"] = {"type": CONDITION_TYPE_OR, "list": []}
                conditions_or = condition_list.split("C")
                for group in conditions_or:
                    if len(group) > 1:
                        my_entry["conditions"]["type"] = CONDITION_TYPE_AND
                        conditions_list = [int(i) for i in group]
                        my_entry["conditions"]["list"].extend(conditions_list)
                if my_entry["conditions"]["type"] == CONDITION_TYPE_OR:
                    for group in conditions_or:
                        conditions_list = [int(i) for i in group]
                        my_entry["conditions"]["list"].extend(conditions_list)

            self.entries.append(my_entry)

        if "friendly_name" in data:
            self.name = data["friendly_name"]

        if "icon" in data:
            self.icon = data["icon"]

        if "conditions" in data:
            self.conditions = data["conditions"]

        return True

    def export_data(self):
        output = {"entries": [], "actions": self.actions}

        def export_time(entry_time):
            if "at" in entry_time:
                time_str = entry_time["at"].replace(":", "")
            elif "event" in entry_time:
                if entry_time["event"] == TIME_EVENT_SUNRISE:
                    event_string = ENTRY_PATTERN_SUNRISE
                elif entry_time["event"] == TIME_EVENT_SUNSET:
                    event_string = ENTRY_PATTERN_SUNSET
                elif entry_time["event"] == TIME_EVENT_DAWN:
                    event_string = ENTRY_PATTERN_DAWN
                elif entry_time["event"] == TIME_EVENT_DUSK:
                    event_string = ENTRY_PATTERN_DUSK

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
                raise Exception("failed to parse time object")
            return time_str

        for entry in self.entries:

            entry_str = ""

            # parse days
            if entry["days"]["type"] == DAY_TYPE_DAILY:
                entry_str += "{}D".format(ENTRY_PATTERN_DAILY)
            elif entry["days"]["type"] == DAY_TYPE_WORKDAY:
                entry_str += "{}D".format(ENTRY_PATTERN_WORKDAY)
            elif entry["days"]["type"] == DAY_TYPE_WEEKEND:
                entry_str += "{}D".format(ENTRY_PATTERN_WEEKEND)
            else:
                days_arr = [str(i) for i in entry["days"]["list"]]
                days_string = "".join(days_arr)
                entry_str += "D{}".format(days_string)

            # parse time
            time_string = export_time(entry["time"])
            entry_str += "T{}".format(time_string)
            if "end_time" in entry:
                end_time_string = export_time(entry["end_time"])
                entry_str += "T{}".format(end_time_string)

            # parse actions
            action_arr = [str(i) for i in entry["actions"]]
            action_string = "A".join(action_arr)
            entry_str += "A{}".format(action_string)

            # parse conditions
            if "conditions" in entry:
                condition_arr = [str(i) for i in entry["conditions"]["list"]]
                if entry["conditions"]["type"] == CONDITION_TYPE_AND:
                    condition_string = "".join(condition_arr)
                else:
                    condition_string = "C".join(condition_arr)
                entry_str += "C{}".format(condition_string)

            output["entries"].append(entry_str)

        if self.conditions:
            output["conditions"] = self.conditions

        return output

    def has_sun(self, entry_num=None):
        if entry_num == None:
            for entry in self.entries:
                if "time" in entry and "event" in entry["time"]:
                    return True

            return False
        else:
            entry = self.entries[entry_num]
            return "time" in entry and "event" in entry["time"]

    def update_sun_data(self, sun_data, entry=None):
        if not self.sun_data:
            self.sun_data = sun_data
            return False

        if entry is not None:
            ts_old = self.get_timestamp_for_entry(
                entry, self.sun_data, self.workday_data
            )
            ts_new = self.get_timestamp_for_entry(entry, sun_data, self.workday_data)

            delta = (ts_old - ts_new).total_seconds()

            if (
                abs(delta) >= 60 and abs(delta) <= 3600
            ):  # only reschedule if the drift is more than 1 min, and not hours (next day)
                return True
                self.sun_data = sun_data

        return False

    def has_workday(self, entry_num=None):
        if entry_num == None:
            for entry in self.entries:
                if entry["days"]["type"] == DAY_TYPE_WORKDAY:
                    return True
                elif entry["days"]["type"] == DAY_TYPE_WEEKEND:
                    return True

            return False
        else:
            entry = self.entries[entry_num]
            if entry["days"]["type"] == DAY_TYPE_WORKDAY:
                return True
            elif entry["days"]["type"] == DAY_TYPE_WEEKEND:
                return True
            else:
                return False

    def update_workday_data(self, workday_data, entry=None):
        if not self.workday_data:
            self.workday_data = workday_data
            return False

        if entry is not None:
            ts_old = self.get_timestamp_for_entry(
                entry, self.sun_data, self.workday_data
            )
            ts_new = self.get_timestamp_for_entry(entry, self.sun_data, workday_data)

            delta = (ts_old - ts_new).total_seconds()

            if abs(delta) >= 3600:  # item needs to be rescheduled
                return True
                self.workday_data = workday_data

        return False

    def get_condition_entities_for_entry(self, entry):
        """Get the conditions for a specific entry"""
        entity_list = []
        if not self.conditions or not "conditions" in self.entries[entry]:
            return None

        for entry_condition in self.entries[entry]["conditions"]["list"]:
            entity = self.conditions[entry_condition]["entity"]
            entity_list.append(entity)

        return entity_list

    def validate_conditions_for_entry(self, entry, states):
        """Validate the set of conditions against the results"""
        if not self.conditions or not "conditions" in self.entries[entry]:
            return None

        results = []
        for item in self.entries[entry]["conditions"]["list"]:
            condition_item = self.conditions[item]

            required = condition_item["state"]
            actual = (
                states[condition_item["entity"]]
                if condition_item["entity"] in states
                else None
            )

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

            if actual == None or actual == "unavailable" or actual == "unknown":
                result = False
            elif condition_item["match_type"] == MATCH_TYPE_EQUAL:
                result = actual == required
            elif condition_item["match_type"] == MATCH_TYPE_UNEQUAL:
                result = actual != required
            elif condition_item["match_type"] == MATCH_TYPE_BELOW:
                result = actual < required
            elif condition_item["match_type"] == MATCH_TYPE_ABOVE:
                result = actual > required
            else:
                result = False

            # _LOGGER.debug("validating condition for {}: required={}, actual={}, match_type={}, result={}".format(condition_item["entity"], required,actual,condition_item["match_type"], result))
            results.append(result)

        condition_type = self.entries[entry]["conditions"]["type"]
        if condition_type == CONDITION_TYPE_AND:
            return all(results)
        else:
            return any(results)
