import datetime
import logging
import math

import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)


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

    return "{}{}:{}".format(
        sign, str(hours).zfill(2), str(minutes).zfill(2)
    )


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

        if time_entry["event"] == "sunrise":
            time_sun = sun_data["sunrise"]
        elif time_entry["event"] == "sunset":
            time_sun = sun_data["sunset"]
        elif time_entry["event"] == "dawn":
            time_sun = sun_data["dawn"]
        elif time_entry["event"] == "dusk":
            time_sun = sun_data["dusk"]
        
        time_sun = parse_iso_timestamp(time_sun)

        if offset_sign == "+":
            time_obj = time_sun + time_offset
        else:
            time_obj = time_sun - time_offset

    else:
        raise Exception("cannot parse timestamp")
    
    return time_obj


def calculate_next_start_time(entry: dict, sun_data):
    """Get datetime object with closest occurance based on time + weekdays input"""
    nexttime = calculate_datetime_from_entry(entry["time"], sun_data)

    now = dt_util.now().replace(microsecond=0)

    # check if time has already passed for today
    delta = nexttime - now
    while delta.total_seconds() <= 0:
        nexttime = nexttime + datetime.timedelta(days=1)
        delta = nexttime - now

    # check if timer is restricted in days of the week
    day_list = entry["days"]
    if len(day_list) > 0 and not 0 in day_list:
        weekday = dt_util.as_local(nexttime).isoweekday()
        while weekday not in day_list:
            nexttime = nexttime + datetime.timedelta(days=1)
            weekday = dt_util.as_local(nexttime).isoweekday()

    return nexttime


def is_between_start_time_and_end_time(entry: dict, sun_data):
    """Get datetime object with closest occurance based on time + weekdays input"""

    start_time = calculate_datetime_from_entry(entry["time"], sun_data)
    end_time = calculate_datetime_from_entry(entry["end_time"], sun_data)

    if end_time < start_time: 
        end_time = end_time + datetime.timedelta(days=1)

    now = dt_util.now().replace(microsecond=0)

    # check if time has already passed for today
    delta = end_time - now
    while delta.total_seconds() <= 0:
        end_time = end_time + datetime.timedelta(days=1)
        start_time = start_time + datetime.timedelta(days=1)
        delta = end_time - now

    # check if timer is restricted in days of the week
    day_list = entry["days"]
    if len(day_list) > 0 and not 0 in day_list:
        weekday = dt_util.as_local(start_time).isoweekday()
        while weekday not in day_list:
            start_time = start_time + datetime.timedelta(days=1)
            end_time = end_time + datetime.timedelta(days=1)
            weekday = dt_util.as_local(start_time).isoweekday()

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