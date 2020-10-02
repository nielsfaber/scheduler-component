"""Config flow for the Scheduler component."""
import secrets

from homeassistant import config_entries

from . import DOMAIN


class SchedulerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Scheduler."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        id = secrets.token_hex(6)

        await self.async_set_unique_id(id)
        self._abort_if_unique_id_configured(updates=user_input)

        return self.async_create_entry(title="Scheduler integration", data={})
