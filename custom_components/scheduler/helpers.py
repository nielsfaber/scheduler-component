
import logging
import re
import datetime
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

FixedTimePattern = re.compile('^([0-9]{2})([0-9]{2})$')
SunTimePattern = re.compile('^(S[SR])([\+\-])([0-9]+)$')


def entity_exists_in_hass(hass, entity_id):
    if hass.states.get(entity_id) is None:
        return False
    else:
        return True


def service_exists_in_hass(hass, service_name):
    parts = service_name.split('.')
    if len(parts) != 2:
        return False
    elif hass.services.has_service(parts[0], parts[1]) is None:
        return False
    else:
        return True


def calculate_datetime(time_str: str, day_list: list, sun_data):
    """Get datetime object with closest occurance based on time + weekdays input"""

    is_fixed_time = FixedTimePattern.match(time_str)
    is_sun_time = SunTimePattern.match(time_str)

    if is_fixed_time:
        time_str = "{}:{}".format(is_fixed_time.group(1), is_fixed_time.group(2))
        time = dt_util.parse_time(time_str)

        today = dt_util.start_of_local_day()
        nexttime = dt_util.as_utc(datetime.datetime.combine(today, time))

    elif is_sun_time:
        if not sun_data:
            _LOGGER.error("no sun data available")
            return
        
        time_sun = sun_data["sunrise"] if is_sun_time.group(1) == "SR" else sun_data["sunset"]
        time_sun = datetime.datetime.strptime(
                time_sun[: len(time_sun) - 3] + time_sun[len(time_sun) - 2 :],
                "%Y-%m-%dT%H:%M:%S%z",
            )

        offset_string = is_sun_time.group(3)
        time_offset = datetime.datetime.strptime(offset_string, "%H%M")
        time_offset = datetime.timedelta(
            hours=time_offset.hour, minutes=time_offset.minute
        )

        nexttime = time_sun + time_offset if is_sun_time.group(2) == "+" else time_sun - time_offset    

    now = dt_util.now().replace(microsecond=0)

    # check if time has already passed for today
    delta = nexttime - now
    while delta.total_seconds() <= 0:
        nexttime = nexttime + datetime.timedelta(days=1)
        delta = nexttime - now

    # check if timer is restricted in days of the week
    if len(day_list) > 0 and not 0 in day_list:
        weekday = dt_util.as_local(nexttime).isoweekday()
        while weekday not in day_list:
            nexttime = nexttime + datetime.timedelta(days=1)
            weekday = dt_util.as_local(nexttime).isoweekday()

    return nexttime
