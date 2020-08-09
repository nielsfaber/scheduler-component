


def get_id_from_topic(topic_name):
    parts = topic_name.split('/')
    id = parts[1]

    if not id.startswith('scheduler_'):
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