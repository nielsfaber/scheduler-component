import datetime
import logging
import math

import homeassistant.util.dt as dt_util
from homeassistant.const import SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET

from .const import (
    DAY_TYPE_DAILY,
    DAY_TYPE_WEEKEND,
    DAY_TYPE_WORKDAY,
    OffsetTimePattern,
)

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

    return "{}{}:{}".format(sign, str(hours).zfill(2), str(minutes).zfill(2))


def calculate_datetime_from_entry(time: str, sun_data=None):
    res = OffsetTimePattern.match(time)
    if not res:
        time = dt_util.parse_time(time)
        time = time.replace(tzinfo=dt_util.now().tzinfo)

        today = dt_util.now().date()
        time_obj = datetime.datetime.combine(today, time)
    else:
        sun_event = (
            SUN_EVENT_SUNRISE if res.group(1) == SUN_EVENT_SUNRISE else SUN_EVENT_SUNSET
        )
        offset_sign = res.group(2)
        offset_string = res.group(3)

        if not sun_data:
            raise Exception("no sun data available")

        time_offset = datetime.datetime.strptime(offset_string, "%H:%M:%S")
        time_offset = datetime.timedelta(
            hours=time_offset.hour, minutes=time_offset.minute
        )

        time_sun = sun_data[sun_event]

        time_sun = parse_iso_timestamp(time_sun)

        if offset_sign == "+":
            time_obj = time_sun + time_offset
        else:
            time_obj = time_sun - time_offset

    return time_obj


def convert_number_to_weekday(day_arr):
    def day_number_to_weekday(day_string):
        if day_string == 1:
            return "mon"
        elif day_string == 2:
            return "tue"
        elif day_string == 3:
            return "wed"
        elif day_string == 4:
            return "thu"
        elif day_string == 5:
            return "fri"
        elif day_string == 6:
            return "sat"
        elif day_string == 7:
            return "sun"
        else:
            raise Exception("cannot read workday data")

    if type(day_arr) is list:
        day_list = []
        day_arr.sort()
        for num in day_arr:
            val = day_number_to_weekday(num)
            day_list.append(val)

        return day_list
    else:
        return day_number_to_weekday(day_arr)


def is_allowed_day(date_obj: datetime.datetime, weekdays=None, workday_data=None):
    day = convert_number_to_weekday(dt_util.as_local(date_obj).isoweekday())
    workday_list = ["mon", "tue", "wed", "thu", "fri"]
    weekend_list = ["sat", "sun"]

    if workday_data:
        # update the list of workdays and weekend days with data from workday sensor
        workday_list = workday_data["workdays"]
        weekend_list = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        for val in workday_list:
            weekend_list = list(filter(lambda x: x != val, weekend_list))

        today = dt_util.as_local(date_obj).date()
        date_obj_date = dt_util.now().replace(microsecond=0).date()

        # check if today is a workday according to the sensor (includes holidays)
        if today == date_obj_date:
            if DAY_TYPE_WORKDAY in weekdays:
                return workday_data["today_is_workday"]
            elif DAY_TYPE_WEEKEND in weekdays:
                return not workday_data["today_is_workday"]

    if DAY_TYPE_DAILY in weekdays:
        return True
    elif DAY_TYPE_WORKDAY in weekdays and day in workday_list:
        return True
    elif DAY_TYPE_WEEKEND in weekdays and day in weekend_list:
        return True
    return day in weekdays


def calculate_next_start_time(
    start=None, weekdays=None, sun_data=None, workday_data=None, now=None
):
    """Get datetime object with closest occurance based on time + weekdays input"""
    nexttime = calculate_datetime_from_entry(start, sun_data=sun_data)
    if not now:
        now = dt_util.now().replace(microsecond=0)

    # check if time has already passed for today
    iterations = 0
    delta = nexttime - now
    while delta.total_seconds() <= 0 and iterations < 100:
        nexttime = nexttime + datetime.timedelta(days=1)
        delta = nexttime - now
        iterations = iterations + 1

    # check if timer is restricted in days of the week
    while (
        not is_allowed_day(nexttime, weekdays=weekdays, workday_data=workday_data)
        and iterations < 100
    ):
        nexttime = nexttime + datetime.timedelta(days=1)
        iterations = iterations + 1

    if iterations == 100:
        raise Exception("failed to calculate timestamp")

    return nexttime


def is_between_start_time_and_end_time(
    start=None, stop=None, weekdays=None, sun_data=None, workday_data=None, time=None
):
    """Get datetime object with closest occurance based on time + weekdays input"""

    start_time = calculate_datetime_from_entry(start, sun_data)
    if stop:
        end_time = calculate_datetime_from_entry(stop, sun_data)
    else:
        end_time = start_time + datetime.timedelta(minutes=1)

    if end_time < start_time:
        end_time = end_time + datetime.timedelta(days=1)

    if time:
        now = time
    else:
        now = dt_util.now().replace(microsecond=0)

    # check if time has already passed for today
    iterations = 0
    delta = end_time - now
    while delta.total_seconds() <= 0 and iterations < 100:
        end_time = end_time + datetime.timedelta(days=1)
        start_time = start_time + datetime.timedelta(days=1)
        delta = end_time - now
        iterations = iterations + 1

    # check if timer is restricted in days of the week
    if not time:
        while (
            not is_allowed_day(start_time, weekdays=weekdays, workday_data=workday_data)
            and iterations < 100
        ):
            start_time = start_time + datetime.timedelta(days=1)
            end_time = end_time + datetime.timedelta(days=1)
            iterations = iterations + 1

        if iterations == 100:
            raise Exception("failed to calculate timestamp")

    delta_start = (start_time - now).total_seconds()
    delta_end = (end_time - now).total_seconds()

    if delta_start <= 0 and delta_end > 0:
        return True
    else:
        return False


def parse_iso_timestamp(time_string):
    time_obj = datetime.datetime.strptime(
        time_string[: len(time_string) - 3] + time_string[len(time_string) - 2:],
        "%Y-%m-%dT%H:%M:%S%z",
    )

    return time_obj


def has_overlapping_timeslot(
    slots, weekdays=None, sun_data=None, workday_data=None, time=None
):
    """Check if there are timeslots which overlapping with now"""

    for i in range(len(slots)):
        slot = slots[i]
        if is_between_start_time_and_end_time(
            start=slot["start"],
            stop=slot["stop"],
            weekdays=weekdays,
            sun_data=sun_data,
            workday_data=workday_data,
            time=time,
        ):
            return i

    return None
