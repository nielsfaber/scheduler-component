import copy
import logging
import re

from homeassistant.const import SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET

from .const import CONDITION_TYPE_AND, CONDITION_TYPE_OR

ENTRY_PATTERN_SUNRISE = "SR"
ENTRY_PATTERN_SUNSET = "SS"
ENTRY_PATTERN_DAILY = "0"
ENTRY_PATTERN_WORKDAY = "15"
ENTRY_PATTERN_WEEKEND = "67"

_LOGGER = logging.getLogger(__name__)

EntryPattern = re.compile(
    "^([0-9]+)?D([0-9]+)?T([0-9SRDUW]+)T?([0-9SRDUW]+)?A([A0-9]+)+(C([C0-9]+))?(F([F0-9]+))?$"
)

FixedTimePattern = re.compile("^([0-9]{2})([0-9]{2})$")
SunTimePattern = re.compile(
    "^(([0-9]{2})([0-9]{2}))?([SRDUW]{2})(([0-9]{2})([0-9]{2}))?$"
)


def migrate_old_entity(data: dict, entity_id: str):
    """Import datacollection from restored entity"""

    def import_time_input(time_str):
        fixed_time_pattern = FixedTimePattern.match(time_str)
        sun_time_pattern = SunTimePattern.match(time_str)
        res = {}

        if fixed_time_pattern:
            res = "{}:{}:00".format(
                fixed_time_pattern.group(1),
                fixed_time_pattern.group(2),
            )
        elif sun_time_pattern:
            if sun_time_pattern.group(4) == ENTRY_PATTERN_SUNRISE:
                event = SUN_EVENT_SUNRISE
            elif sun_time_pattern.group(4) == ENTRY_PATTERN_SUNSET:
                event = SUN_EVENT_SUNSET

            if sun_time_pattern.group(1) is not None:  # negative offset
                offset = "-{}:{}:00".format(
                    sun_time_pattern.group(2),
                    sun_time_pattern.group(3),
                )
            else:
                offset = "+{}:{}:00".format(
                    sun_time_pattern.group(6),
                    sun_time_pattern.group(7),
                )
            res = "{}{}".format(event, offset)
        else:
            raise Exception("failed to parse time {}".format(time_str))
        return res

    entries = []
    weekdays = []
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
        if days_setting:
            if days_setting == ENTRY_PATTERN_DAILY:
                weekdays = ["daily"]
            elif days_setting == ENTRY_PATTERN_WORKDAY:
                weekdays = ["workday"]
            elif days_setting == ENTRY_PATTERN_WEEKEND:
                weekdays = ["weekend"]

        elif days_list:
            days_list = list(res.group(2))
            days_list = [int(i) for i in days_list]
            if len(days_list) == 1 and days_list[0] == 0:  # for backwards compatibility
                weekdays = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            else:
                weekdays = []
                if 1 in days_list:
                    weekdays.append("mon")
                if 2 in days_list:
                    weekdays.append("tue")
                if 3 in days_list:
                    weekdays.append("wed")
                if 4 in days_list:
                    weekdays.append("thu")
                if 5 in days_list:
                    weekdays.append("fri")
                if 6 in days_list:
                    weekdays.append("sat")
                if 7 in days_list:
                    weekdays.append("sun")

        # parse time
        my_entry["start"] = import_time_input(str(time_str))
        if end_time_str:
            my_entry["stop"] = import_time_input(str(end_time_str))

        # parse action
        actions = []
        action_list = list(filter(None, action_list))
        action_list = [int(i) for i in action_list]
        for num in action_list:
            if num < len(data["actions"]):
                action = {}
                item = copy.copy(data["actions"][num])
                if "entity" in item:
                    action["entity_id"] = item["entity"]
                    del item["entity"]
                if "service" in item:
                    service = item["service"]
                    if "." not in service and "." in action["entity_id"]:
                        service = "{}.{}".format(
                            action["entity_id"].split(".").pop(0), service
                        )
                    action["service"] = service
                    del item["service"]
                if item:
                    action["service_data"] = item

                actions.append(action)

        my_entry["actions"] = actions

        # parse condition
        if condition_list:
            conditions = []
            condition_type = CONDITION_TYPE_OR
            conditions_list = []
            conditions_or = condition_list.split("C")
            for group in conditions_or:
                if len(group) > 1:
                    condition_type = CONDITION_TYPE_AND
                    conditions_list = [int(i) for i in group]
            if condition_type == CONDITION_TYPE_OR:
                for group in conditions_or:
                    conditions_list = [int(i) for i in group]

            for num in conditions_list:
                if num < len(data["conditions"]):
                    item = data["conditions"][num]
                    condition = {
                        "entity_id": item["entity"],
                        "attribute": "state",
                        "value": item["state"],
                        "match_type": item["match_type"],
                    }
                    conditions.append(condition)
            my_entry["conditions"] = conditions
            my_entry["condition_type"] = condition_type

        entries.append(my_entry)

    repeat_type = "repeat"
    if "options" in data:
        if "run_once" in data["options"]:
            repeat_type = "pause"

    name = None
    if "friendly_name" in data and "#" not in data["friendly_name"]:
        name = data["friendly_name"]

    return {
        "schedule_id": entity_id.replace("schedule_", ""),
        "weekdays": weekdays,
        "timeslots": entries,
        "repeat_type": repeat_type,
        "name": name,
    }
