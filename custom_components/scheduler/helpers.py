import datetime
import logging
import math

import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

from .const import (
    DAY_TYPE_DAILY,
    DAY_TYPE_WORKDAY,
    DAY_TYPE_WEEKEND,
    DAY_TYPE_CUSTOM,
)


def entity_exists_in_hass(hass, entity_id):
    """Check whether an entity ID exists."""
    if hass.states.get(entity_id) is None:
        return False
    else:
        return True


def service_exists_in_hass(hass, service_name):
    """Check whether a service exists."""
    parts = service_name.split(".")
    if len(parts) != 2:
        return False
    elif hass.services.has_service(parts[0], parts[1]) is None:
        return False
    else:
        return True


def timedelta_to_string(time_input: datetime.timedelta):
    seconds = time_input.total_seconds()
    if seconds >= 0:
        hours = math.floor(seconds / 3600)
        seconds = seconds - hours * 3600
        minutes = round(seconds / 60)
        sign = "+"
    else:
        hours = abs(math.ceil(seconds / 3600))
        seconds = seconds + hours * 3600
        minutes = abs(round(seconds / 60))
        sign = "-"

    return "{}{}:{}".format(sign, str(hours).zfill(2), str(minutes).zfill(2))


def calculate_datetime_from_entry(time_entry: dict, sun_data):
    if "at" in time_entry:
        time = dt_util.parse_time(time_entry["at"])

        today = dt_util.start_of_local_day()
        time_obj = dt_util.as_utc(datetime.datetime.combine(today, time))

    elif "event" in time_entry:
        if not sun_data:
            raise Exception("no sun data available")

        offset_sign = time_entry["offset"][0]
        offset_string = time_entry["offset"][1:]

        time_offset = datetime.datetime.strptime(offset_string, "%H:%M")
        time_offset = datetime.timedelta(
            hours=time_offset.hour, minutes=time_offset.minute
        )

        sun_event = time_entry["event"]
        time_sun = sun_data[sun_event]

        time_sun = parse_iso_timestamp(time_sun)

        if offset_sign == "+":
            time_obj = time_sun + time_offset
        else:
            time_obj = time_sun - time_offset

    else:
        raise Exception("cannot parse timestamp")

    return time_obj

def convert_days_to_numbers(day_arr):
    def day_string_to_number(day_string):
        if day_string == "mon":
            return 1
        elif day_string == "tue":
            return 2
        elif day_string == "wed":
            return 3
        elif day_string == "thu":
            return 4
        elif day_string == "fri":
            return 5
        elif day_string == "sat":
            return 6
        elif day_string == "sun":
            return 7
        else:
            raise Exception("cannot read workday data")

    day_list = []
    for day_str in day_arr:
        num = day_string_to_number(day_str)
        day_list.append(num)

    day_list.sort()
    return day_list


def is_allowed_day(date_obj: datetime.datetime, day_entry: dict, workday_data):
    day = dt_util.as_local(date_obj).isoweekday()
    workday_list = [1,2,3,4,5]
    weekend_list = [6,7]
    day_type = day_entry["type"]

    if workday_data:
        # update the list of workdays and weekend days with data from workday sensor
        workday_list = workday_data["workdays"]
        weekend_list = [1,2,3,4,5,6,7]
        for val in workday_list:
            weekend_list = list(filter(lambda x : x != val, weekend_list))

        today = dt_util.as_local(date_obj).date()
        date_obj_date = dt_util.now().replace(microsecond=0).date()

        # check if today is a workday according to the sensor (includes holidays)
        if today == date_obj_date:
            if day_type == DAY_TYPE_WORKDAY:
                return workday_data["today_is_workday"]
            elif day_type == DAY_TYPE_WEEKEND:
                return (not workday_data["today_is_workday"])
    
    if day_type == DAY_TYPE_DAILY:
        return True
    elif day_type == DAY_TYPE_WORKDAY:
        return (day in workday_list)
    elif day_type == DAY_TYPE_WEEKEND:
        return (day in weekend_list)
    elif day_type == DAY_TYPE_CUSTOM:
        day_list = day_entry["list"]
        return (day in day_list)


def calculate_next_start_time(entry: dict, sun_data, workday_data):
    """Get datetime object with closest occurance based on time + weekdays input"""
    nexttime = calculate_datetime_from_entry(entry["time"], sun_data)

    now = dt_util.now().replace(microsecond=0)

    # check if time has already passed for today
    iterations = 0
    delta = nexttime - now
    while delta.total_seconds() <= 0 and iterations<100:
        nexttime = nexttime + datetime.timedelta(days=1)
        delta = nexttime - now
        iterations = iterations + 1

    # check if timer is restricted in days of the week
    while not is_allowed_day(nexttime, entry["days"], workday_data) and iterations<100:
        nexttime = nexttime + datetime.timedelta(days=1)
        iterations = iterations + 1

    if iterations==100:
        _LOGGER.error(entry)
        raise Exception("failed to calculate timestamp")
    return nexttime


def is_between_start_time_and_end_time(entry: dict, sun_data, workday_data):
    """Get datetime object with closest occurance based on time + weekdays input"""

    start_time = calculate_datetime_from_entry(entry["time"], sun_data)
    end_time = calculate_datetime_from_entry(entry["end_time"], sun_data)

    if end_time < start_time:
        end_time = end_time + datetime.timedelta(days=1)

    now = dt_util.now().replace(microsecond=0)

    # check if time has already passed for today
    iterations = 0
    delta = end_time - now
    while delta.total_seconds() <= 0 and iterations<100:
        end_time = end_time + datetime.timedelta(days=1)
        start_time = start_time + datetime.timedelta(days=1)
        delta = end_time - now
        iterations = iterations + 1

    # check if timer is restricted in days of the week
    while not is_allowed_day(start_time, entry["days"], workday_data) and iterations<100:
        start_time = start_time + datetime.timedelta(days=1)
        end_time = end_time + datetime.timedelta(days=1)
        iterations = iterations + 1

    if iterations==100:
        _LOGGER.error(entry)
        raise Exception("failed to calculate timestamp")
    
    delta_start = (start_time - now).total_seconds()
    delta_end = (end_time - now).total_seconds()

    if delta_start < 0 and delta_end > 0:
        return True
    else:
        return False


def parse_iso_timestamp(time_string):
    time_obj = datetime.datetime.strptime(
        time_string[: len(time_string) - 3] + time_string[len(time_string) - 2 :],
        "%Y-%m-%dT%H:%M:%S%z",
    )

    return time_obj
