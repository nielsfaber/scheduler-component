"""Regression tests for timeslots that start when the workday sensor changes state."""

import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from custom_components.scheduler import const
from custom_components.scheduler import timer as timer_module
from custom_components.scheduler.timer import TimerHandler

from homeassistant.const import STATE_OFF, STATE_ON

UTC = datetime.timezone.utc

# Sunday 2026-11-22; the next day is a Monday.
SUNDAY = datetime.datetime(2026, 11, 22, tzinfo=UTC)


def at(day: datetime.datetime, hour=0, minute=0, second=0, microsecond=0):
    return day.replace(hour=hour, minute=minute, second=second, microsecond=microsecond)


MONDAY = SUNDAY + datetime.timedelta(days=1)
THURSDAY = SUNDAY + datetime.timedelta(days=4)
FRIDAY = SUNDAY + datetime.timedelta(days=5)


class Harness:
    """A TimerHandler with a controllable clock, workday sensor, timers and dispatcher."""

    def __init__(self, weekdays, starts):
        self.now = None
        self.workday = SimpleNamespace(state=STATE_ON, attributes={})
        self.hass = Mock()
        self.hass.data = {}  # no coordinator: day types come from the workday sensor only
        self.hass.states.get = lambda entity_id: (
            self.workday if entity_id == const.WORKDAY_ENTITY else None
        )
        self.timers = []  # (callback, point in time, unsubscribe mock) per timer set
        self.listeners = {}  # dispatcher signal -> callback
        self.sent = []  # dispatcher signals sent

        def track_point_in_time(_hass, action, point):
            unsub = Mock()
            self.timers.append((action, point, unsub))
            return unsub

        def dispatcher_connect(_hass, signal, target):
            self.listeners[signal] = target
            return Mock(side_effect=lambda: self.listeners.pop(signal, None))

        self._patches = [
            patch.object(timer_module, "async_track_point_in_time", track_point_in_time),
            patch.object(timer_module, "async_dispatcher_connect", dispatcher_connect),
            patch.object(
                timer_module,
                "async_dispatcher_send",
                lambda _hass, signal, *args: self.sent.append(signal),
            ),
            patch.object(timer_module.dt_util, "utcnow", lambda: self.now),
            patch.object(TimerHandler, "async_reload_data", Mock()),
        ]
        for p in self._patches:
            p.start()

        self.handler = TimerHandler(self.hass, "abc123")
        self.handler._weekdays = weekdays
        self.handler._start_date = None
        self.handler._end_date = None
        stops = starts[1:] + ["00:00:00"]
        self.handler._timeslots = [
            {const.ATTR_START: start, const.ATTR_STOP: stop}
            for start, stop in zip(starts, stops)
        ]

    def stop(self):
        for p in self._patches:
            p.stop()

    @property
    def live_timer(self):
        """The timer that is set and not cancelled, if any."""
        live = [t for t in self.timers if not t[2].called]
        assert len(live) <= 1
        return live[0] if live else None

    async def workday_changes(self, when, state):
        self.now = when
        self.workday.state = state
        await self.listeners[const.EVENT_WORKDAY_SENSOR_UPDATED]()


@pytest.fixture
def harness():
    created = []

    def make(weekdays, starts):
        h = Harness(weekdays, starts)
        created.append(h)
        return h

    yield make
    for h in created:
        h.stop()


@pytest.mark.asyncio
async def test_workday_slot_at_midnight_runs_when_sensor_updates_first(harness):
    """Monday 00:00: the sensor turns on just before the 00:00 timer finishes."""
    h = harness([const.DAY_TYPE_WORKDAY], ["00:00:00", "13:00:00"])
    h.now = at(SUNDAY, 20)
    h.workday.state = STATE_OFF
    await h.handler.async_start_timer()
    assert h.live_timer[1] == at(MONDAY)

    await h.workday_changes(at(MONDAY, microsecond=4000), STATE_ON)

    action, point, _ = h.live_timer
    assert action == h.handler.async_timer_finished
    assert point == at(MONDAY)
    await action(point)
    assert h.handler.current_slot == 0
    assert h.sent[-1] == const.EVENT_TIMER_FINISHED


@pytest.mark.asyncio
async def test_weekend_slot_at_midnight_runs_on_a_holiday(harness):
    """Friday 00:00 is a holiday: the sensor turns off and the weekend 00:00 slot must run."""
    h = harness([const.DAY_TYPE_WEEKEND], ["00:00:00", "01:00:00", "07:00:00"])
    h.now = at(THURSDAY, 20)
    await h.handler.async_start_timer()
    assert h.live_timer[1] == at(FRIDAY + datetime.timedelta(days=1))

    await h.workday_changes(at(FRIDAY, microsecond=4000), STATE_OFF)

    action, point, _ = h.live_timer
    assert point == at(FRIDAY)
    await action(point)
    assert h.handler.current_slot == 0


@pytest.mark.asyncio
async def test_workday_slot_does_not_run_on_a_holiday(harness):
    """Friday 00:00 is a holiday: the workday 00:00 slot is cancelled, not run."""
    h = harness([const.DAY_TYPE_WORKDAY], ["00:00:00", "13:00:00"])
    # just after the end-of-day timer of Thursday's last slot (23:59:59) restarted the timer
    h.now = at(THURSDAY, 23, 59, 59, 500000)
    await h.handler.async_start_timer()
    assert h.live_timer[1] == at(FRIDAY)

    await h.workday_changes(at(FRIDAY, microsecond=4000), STATE_OFF)

    assert h.live_timer[1] == at(MONDAY + datetime.timedelta(days=7))


@pytest.mark.asyncio
async def test_later_workday_update_does_not_rerun_a_slot(harness):
    """The daily 00:05 poll of the workday sensor must not run the 00:00 slot again."""
    h = harness([const.DAY_TYPE_WORKDAY], ["00:00:00", "13:00:00"])
    h.now = at(MONDAY, 0, 1)
    await h.handler.async_start_timer()
    assert h.live_timer[1] == at(MONDAY, 13)

    await h.workday_changes(at(MONDAY, 0, 5), STATE_ON)

    assert h.live_timer[1] == at(MONDAY, 13)
    assert h.handler._next_slot == 1
