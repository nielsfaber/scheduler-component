


def get_id_from_topic(topic_name):
    parts = topic_name.split('/')
    id = parts[1]

    if not id.startswith('schedule_'):
        return None
    else:
        return id


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


def time_has_sun(time_str):
    return ('sunrise' in time_str or 'sunset' in time_str)


def parse_sun_time_string(time_str):
    if 'sunrise' in time_str:
        if '+' in time_str or '-' in time_str:
            return time_str[:7], time_str[7], time_str[8:]
        else:
            return 'sunrise', '+', '00:00'
    
    elif 'sunset' in time_str:
        if '+' in time_str or '-' in time_str:
            return time_str[:6], time_str[6], time_str[7:]
        else:
            return 'sunset', '+', '00:00'
