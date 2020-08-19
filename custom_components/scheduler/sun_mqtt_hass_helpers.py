"""Helper functions for other files."""


def get_id_from_topic(topic_name):
    """Get an ID from a topic."""
    parts = topic_name.split("/")
    topicid = parts[1]
    return topicid if topicid.startswith("schedule_") else None


def entity_exists_in_hass(hass, entity_id):
    """Check whether an entity ID exists."""
    return hass.states.get(entity_id) is not None


def service_exists_in_hass(hass, service_name):
    """Check whether a service exists."""
    parts = service_name.split(".")
    return (
        len(parts) == 2
        and hass.services.has_service(parts[0], parts[1]) is not None
    )


def time_has_sun(time_str):
    """Check whether a time string is a sunrise/sunset offset."""
    return "sunrise" in time_str or "sunset" in time_str


def parse_sun_time_string(time_str):
    """Parse a time string into a tuple."""
    if "sunrise" in time_str:
        if "+" in time_str or "-" in time_str:
            return time_str[:7], time_str[7], time_str[8:]
        return "sunrise", "+", "00:00"

    elif "sunset" in time_str:
        if "+" in time_str or "-" in time_str:
            return time_str[:6], time_str[6], time_str[7:]
        return "sunset", "+", "00:00"
