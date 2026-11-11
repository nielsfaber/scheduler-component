"""Regression tests for workday sensor tracking initialization.

The workday sensor may not exist yet when the scheduler integration is
initialized, e.g. right after a restart while the workday integration is
still setting up, or when the workday config entry is added later. Workday
tracking must be installed anyway; otherwise workday schedules silently
degrade to the mon-fri weekday mask until the next restart, and run on
public holidays.
"""

from types import MethodType, SimpleNamespace

from homeassistant.helpers.dispatcher import async_dispatcher_connect

from custom_components.scheduler import SchedulerCoordinator, const


def _coordinator(hass):
    """Build a minimal coordinator with the real workday tracking methods."""
    coordinator = SimpleNamespace(
        hass=hass,
        _workday_tracker=None,
        _workday_timer=None,
    )
    coordinator.async_reset_workday_timer = MethodType(
        SchedulerCoordinator.async_reset_workday_timer, coordinator
    )
    coordinator.async_init_workday_sensor = MethodType(
        SchedulerCoordinator.async_init_workday_sensor, coordinator
    )
    return coordinator


async def test_workday_tracking_installed_when_sensor_is_missing(hass):
    """Initialization must not depend on the workday sensor being ready."""
    coordinator = _coordinator(hass)

    updates = []
    async_dispatcher_connect(
        hass, const.EVENT_WORKDAY_SENSOR_UPDATED, lambda: updates.append(1)
    )

    # the workday sensor does not exist yet when the scheduler initializes
    assert hass.states.get(const.WORKDAY_ENTITY) is None
    await coordinator.async_init_workday_sensor()

    # the state tracker and the daily 00:05 poll must be installed anyway
    assert coordinator._workday_tracker is not None
    assert coordinator._workday_timer is not None

    # the workday sensor appears afterwards and flips state
    hass.states.async_set(
        const.WORKDAY_ENTITY, "on", {"workdays": ["mon", "tue", "wed", "thu", "fri"]}
    )
    await hass.async_block_till_done()

    hass.states.async_set(
        const.WORKDAY_ENTITY, "off", {"workdays": ["mon", "tue", "wed", "thu", "fri"]}
    )
    await hass.async_block_till_done()

    # state changes must dispatch workday_sensor_updated, which is the
    # signal workday schedules listen to for re-arming their timers
    assert updates
