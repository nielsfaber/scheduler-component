"""Tests for the holiday-aware workday status cache."""

import datetime
from types import SimpleNamespace

from custom_components.scheduler import async_get_workday_statuses, const
from custom_components.scheduler.timer import TimerHandler
import pytest

from homeassistant.const import ATTR_ENTITY_ID, STATE_ON
from homeassistant.core import ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
import homeassistant.util.dt as dt_util

FRIDAY = datetime.date(2026, 8, 28)
HOLIDAY = datetime.date(2026, 8, 31)  # Monday


def is_workday(date: datetime.date) -> bool:
    """Monday to Friday, except the holiday."""
    return date.weekday() < 5 and date != HOLIDAY


def register_check_date(hass, calls=None):
    """Register a stand-in for the workday.check_date action."""

    def check_date(call: ServiceCall):
        if calls is not None:
            calls.append(call)
        date = dt_util.parse_date(call.data["check_date"])
        return {const.WORKDAY_ENTITY: {"workday": is_workday(date)}}

    hass.services.async_register(
        const.WORKDAY_DOMAIN,
        const.WORKDAY_SERVICE_CHECK_DATE,
        check_date,
        supports_response=SupportsResponse.ONLY,
    )


def make_timer(hass, weekdays, workday_cache):
    """Create a timer handler without loading a schedule from the store."""
    hass.data[const.DOMAIN] = {
        "coordinator": SimpleNamespace(workday_cache=workday_cache)
    }
    timer = TimerHandler.__new__(TimerHandler)
    timer.hass = hass
    timer.id = "schedule-id"
    timer._weekdays = weekdays
    timer._start_date = None
    timer._end_date = None
    return timer


def local_time(date: datetime.date, hour: int) -> datetime.datetime:
    return datetime.datetime.combine(
        date, datetime.time(hour), tzinfo=dt_util.get_default_time_zone()
    )


def workday_cache(start: datetime.date, days: int) -> dict:
    dates = [start + datetime.timedelta(days=i) for i in range(days)]
    return {date: is_workday(date) for date in dates}


@pytest.mark.asyncio
async def test_statuses_are_read_with_check_date(hass):
    """Each date is checked for the workday sensor, including holidays."""
    calls = []
    hass.states.async_set(const.WORKDAY_ENTITY, STATE_ON)
    register_check_date(hass, calls)
    dates = [FRIDAY + datetime.timedelta(days=i) for i in range(4)]

    statuses = await async_get_workday_statuses(hass, dates)

    assert statuses == {
        datetime.date(2026, 8, 28): True,
        datetime.date(2026, 8, 29): False,
        datetime.date(2026, 8, 30): False,
        datetime.date(2026, 8, 31): False,
    }
    assert [call.data[ATTR_ENTITY_ID] for call in calls] == [const.WORKDAY_ENTITY] * 4


@pytest.mark.asyncio
async def test_no_statuses_without_sensor_or_action(hass):
    """Without the workday sensor or the action, nothing is cached."""
    register_check_date(hass)
    assert await async_get_workday_statuses(hass, [FRIDAY]) == {}

    hass.services.async_remove(const.WORKDAY_DOMAIN, const.WORKDAY_SERVICE_CHECK_DATE)
    hass.states.async_set(const.WORKDAY_ENTITY, STATE_ON)
    assert await async_get_workday_statuses(hass, [FRIDAY]) == {}


@pytest.mark.asyncio
async def test_no_statuses_when_check_date_fails(hass):
    """A failing action leaves the cache empty, so the old logic is used."""

    def check_date(call: ServiceCall):
        raise HomeAssistantError("not available")

    hass.states.async_set(const.WORKDAY_ENTITY, STATE_ON)
    hass.services.async_register(
        const.WORKDAY_DOMAIN,
        const.WORKDAY_SERVICE_CHECK_DATE,
        check_date,
        supports_response=SupportsResponse.ONLY,
    )

    assert await async_get_workday_statuses(hass, [FRIDAY]) == {}


@pytest.mark.asyncio
async def test_workday_next_trigger_skips_future_holiday(hass):
    """On Friday, the next workday trigger is Tuesday when Monday is a holiday."""
    now = local_time(FRIDAY, 10)

    timer = make_timer(hass, [const.DAY_TYPE_WORKDAY], workday_cache(FRIDAY, 10))
    assert timer.calculate_timestamp("07:00:00", now) == local_time(
        datetime.date(2026, 9, 1), 7
    )

    timer = make_timer(hass, [const.DAY_TYPE_WORKDAY], {})
    assert timer.calculate_timestamp("07:00:00", now) == local_time(HOLIDAY, 7)


@pytest.mark.asyncio
async def test_weekend_next_trigger_includes_future_holiday(hass):
    """On Sunday, the next weekend trigger is Monday when it is a holiday."""
    sunday = datetime.date(2026, 8, 30)
    now = local_time(sunday, 10)

    timer = make_timer(hass, [const.DAY_TYPE_WEEKEND], workday_cache(sunday, 10))
    assert timer.calculate_timestamp("07:00:00", now) == local_time(HOLIDAY, 7)

    timer = make_timer(hass, [const.DAY_TYPE_WEEKEND], {})
    assert timer.calculate_timestamp("07:00:00", now) == local_time(
        datetime.date(2026, 9, 5), 7
    )
