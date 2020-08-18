
import logging
import re
import datetime
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

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


def calculate_datetime(entry: dict, sun_data):
    """Get datetime object with closest occurance based on time + weekdays input"""

    if "time" in entry:
        time = entry["time"]

        today = dt_util.start_of_local_day()
        nexttime = dt_util.as_utc(datetime.datetime.combine(today, time))

    elif "event" in entry:
        if not sun_data:
            _LOGGER.error("no sun data available")
            return
        
        time_sun = sun_data["sunrise"] if entry["event"] == "sunrise" else sun_data["sunset"]
        time_sun = datetime.datetime.strptime(
                time_sun[: len(time_sun) - 3] + time_sun[len(time_sun) - 2 :],
                "%Y-%m-%dT%H:%M:%S%z",
            )

        time_offset = entry["offset"]
        nexttime = time_sun + time_offset

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
