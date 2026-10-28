"""Regression tests for Scheduler config-entry unload."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from homeassistant.core import HomeAssistant

from custom_components.scheduler import async_unload_entry


class UnloadTests(unittest.IsolatedAsyncioTestCase):
    """Keep schedules running when Home Assistant refuses to unload them."""

    async def test_failed_platform_unload_keeps_coordinator(self):
        """A failed platform unload must leave the coordinator running."""
        coordinator = SimpleNamespace(async_unload=AsyncMock())
        entry = object()
        unload_platform = AsyncMock(return_value=False)
        hass = Mock(
            spec=HomeAssistant,
            data={"scheduler": {"coordinator": coordinator}},
            config_entries=SimpleNamespace(async_forward_entry_unload=unload_platform),
        )

        self.assertFalse(await async_unload_entry(hass, entry))

        unload_platform.assert_awaited_once_with(entry, "switch")
        coordinator.async_unload.assert_not_awaited()
        self.assertIs(hass.data["scheduler"]["coordinator"], coordinator)

    async def test_successful_platform_unload_stops_coordinator(self):
        """A successful platform unload must still dispose the coordinator."""
        coordinator = SimpleNamespace(async_unload=AsyncMock())
        entry = object()
        unload_platform = AsyncMock(return_value=True)
        hass = Mock(
            spec=HomeAssistant,
            data={"scheduler": {"coordinator": coordinator}},
            config_entries=SimpleNamespace(async_forward_entry_unload=unload_platform),
        )

        self.assertTrue(await async_unload_entry(hass, entry))

        unload_platform.assert_awaited_once_with(entry, "switch")
        coordinator.async_unload.assert_awaited_once_with()
