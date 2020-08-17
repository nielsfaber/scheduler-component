"""Config flow for the Scheduler component."""
import voluptuous as vol

from homeassistant import config_entries
#from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PORT
#from homeassistant.core import callback
#from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import DOMAIN  # pylint: disable=unused-import

# DATA_SCHEMA = {
#     vol.Required(CONF_HOST): str,
#     vol.Optional(CONF_EMAIL): str,
#     vol.Required(CONF_PORT): vol.Coerce(int),
# }


class SchedulerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Scheduler."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        id = 'myid1234567'

        await self.async_set_unique_id(id)
        self._abort_if_unique_id_configured(updates=user_input)

        return self.async_create_entry(title=id, data=user_input)

    # @callback
    # async def _show_form(self, errors=None):
    #     """Show the form to the user."""
    #     return self.async_show_form(
    #         step_id="user",
    #         data_schema=vol.Schema(DATA_SCHEMA),
    #         errors=errors if errors else {},
    #     )