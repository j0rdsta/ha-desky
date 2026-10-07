"""Test the sitting and standing time today sensors."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorStateClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)

from custom_components.desky_desk.const import POSTURE_SETTLE_SECONDS

from . import disconnect_desk, notify_desk

STANDING_TIME = "sensor.desky_desk_standing_time_today"
SITTING_TIME = "sensor.desky_desk_sitting_time_today"

# 14:00 local in the test time zone (US/Pacific)
AFTERNOON = "2026-10-07 14:00:00-07:00"


async def _advance(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta
) -> None:
    """Move time forward a minute at a time, as the minute tick sees it."""
    remaining = delta
    while remaining > timedelta(0):
        step = min(remaining, timedelta(minutes=1))
        freezer.tick(step)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        remaining -= step


async def _settle(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Let the desk stand still long enough for the posture to follow it."""
    await _advance(hass, freezer, timedelta(seconds=POSTURE_SETTLE_SECONDS))


def _minutes(hass: HomeAssistant, entity_id: str) -> float:
    """Return a duration sensor's value."""
    state = hass.states.get(entity_id)
    assert state is not None
    return float(state.state)


async def _set_up(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the desk, connected."""
    entry.add_to_hass(hass)
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            "homeassistant.components.bluetooth.async_ble_device_from_address",
            lambda *args, **kwargs: MagicMock(address="AA:BB:CC:DD:EE:FF"),
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def _restore(hass: HomeAssistant, minutes: float, last_reset: datetime) -> None:
    """Restore both duration sensors with a value from a given day."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(
                    entity_id,
                    str(minutes),
                    {"last_reset": last_reset.isoformat()},
                ),
                {
                    "native_value": minutes,
                    "native_unit_of_measurement": UnitOfTime.MINUTES,
                },
            )
            for entity_id in (STANDING_TIME, SITTING_TIME)
        ],
    )


@pytest.mark.freeze_time(AFTERNOON)
async def test_duration_sensors_describe_a_daily_total(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the sensors are daily totals in minutes, recorded as statistics."""
    for entity_id in (STANDING_TIME, SITTING_TIME):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "0.0"
        assert state.attributes[ATTR_DEVICE_CLASS] == "duration"
        assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfTime.MINUTES
        assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL
        assert state.attributes["last_reset"] == "2026-10-07T00:00:00-07:00"


@pytest.mark.freeze_time(AFTERNOON)
async def test_accumulating_standing_time(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test time is counted in the posture the desk has stopped in."""
    await _settle(hass, freezer)
    await _advance(hass, freezer, timedelta(minutes=10))
    assert _minutes(hass, SITTING_TIME) == 10.0
    assert _minutes(hass, STANDING_TIME) == 0.0

    # The desk takes 1.5 s to rise, then stands still
    for height in (90.0, 100.0, 110.0):
        notify_desk(mock_desk, height_cm=height)
        await _advance(hass, freezer, timedelta(seconds=0.5))
    await _settle(hass, freezer)
    await _advance(hass, freezer, timedelta(minutes=30))

    # Standing counts from when the desk stopped, before it was confirmed
    assert _minutes(hass, STANDING_TIME) == 30.0
    assert _minutes(hass, SITTING_TIME) == 10.0


@pytest.mark.freeze_time(AFTERNOON)
async def test_time_updates_while_the_desk_is_still(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
) -> None:
    """Test the total rises every minute without any news from the desk."""
    await _settle(hass, freezer)

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert _minutes(hass, SITTING_TIME) == 1.0


@pytest.mark.freeze_time(AFTERNOON)
async def test_time_while_disconnected_is_not_counted(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test neither total rises while the desk is unavailable."""
    await _settle(hass, freezer)
    await _advance(hass, freezer, timedelta(minutes=5))

    disconnect_desk(mock_desk)
    await hass.async_block_till_done()
    await _advance(hass, freezer, timedelta(minutes=20))
    state = hass.states.get(SITTING_TIME)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE

    mock_desk.is_connected = True
    notify_desk(mock_desk)
    await hass.async_block_till_done()
    assert _minutes(hass, SITTING_TIME) == 5.0
    assert _minutes(hass, STANDING_TIME) == 0.0

    # Counting resumes once the posture is known again
    await _settle(hass, freezer)
    await _advance(hass, freezer, timedelta(minutes=5))

    assert _minutes(hass, SITTING_TIME) == 10.0
    assert _minutes(hass, STANDING_TIME) == 0.0


@pytest.mark.freeze_time("2026-10-07 23:50:00-07:00")
async def test_midnight_reset(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test both totals reset at local midnight and count the new day."""
    await _settle(hass, freezer)
    await _advance(hass, freezer, timedelta(minutes=9) - timedelta(seconds=2))
    assert _minutes(hass, SITTING_TIME) == 9.0

    await _advance(hass, freezer, timedelta(minutes=16))

    sitting = hass.states.get(SITTING_TIME)
    assert sitting is not None
    assert float(sitting.state) == 15.0
    assert sitting.attributes["last_reset"] == "2026-10-08T00:00:00-07:00"
    assert _minutes(hass, STANDING_TIME) == 0.0


@pytest.mark.freeze_time("2026-10-07 23:50:00-07:00")
async def test_midnight_reset_without_a_desk(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test the totals reset at midnight while the desk is unavailable."""
    await _settle(hass, freezer)
    await _advance(hass, freezer, timedelta(minutes=5))
    disconnect_desk(mock_desk)
    await hass.async_block_till_done()

    await _advance(hass, freezer, timedelta(minutes=15))
    mock_desk.is_connected = True
    notify_desk(mock_desk)
    await hass.async_block_till_done()

    sitting = hass.states.get(SITTING_TIME)
    assert sitting is not None
    assert sitting.state == "0.0"
    assert sitting.attributes["last_reset"] == "2026-10-08T00:00:00-07:00"


async def test_reset_on_a_day_without_midnight(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test the reset when daylight saving time skips midnight.

    In Santiago the clocks went from 23:59:59 straight to 01:00:00 on
    6 September 2026.
    """
    await hass.config.async_set_time_zone("America/Santiago")
    freezer.move_to("2026-09-05 23:30:00-04:00")
    await _set_up(hass, mock_config_entry)
    await _settle(hass, freezer)

    await _advance(hass, freezer, timedelta(minutes=60) - timedelta(seconds=2))

    sitting = hass.states.get(SITTING_TIME)
    assert sitting is not None
    assert dt_util.now().isoformat() == "2026-09-06T01:30:00-03:00"
    assert float(sitting.state) == 30.0
    assert dt_util.parse_datetime(sitting.attributes["last_reset"]) == datetime(
        2026, 9, 6, 1, tzinfo=dt_util.get_time_zone("America/Santiago")
    )


@pytest.mark.freeze_time(AFTERNOON)
async def test_restart_during_the_day(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test a restart resumes from the totals recorded earlier today."""
    _restore(hass, 120.0, dt_util.start_of_local_day())
    mock_desk.height_cm = 110.0

    await _set_up(hass, mock_config_entry)
    assert _minutes(hass, STANDING_TIME) == 120.0
    assert _minutes(hass, SITTING_TIME) == 120.0

    await _settle(hass, freezer)
    await _advance(hass, freezer, timedelta(minutes=1) - timedelta(seconds=2))

    assert _minutes(hass, STANDING_TIME) == 121.0
    assert _minutes(hass, SITTING_TIME) == 120.0


@pytest.mark.freeze_time(AFTERNOON)
async def test_restart_after_midnight(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test totals from an earlier day are not restored."""
    _restore(hass, 120.0, dt_util.start_of_local_day() - timedelta(days=1))

    await _set_up(hass, mock_config_entry)

    for entity_id in (STANDING_TIME, SITTING_TIME):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "0.0"
        assert state.attributes["last_reset"] == "2026-10-07T00:00:00-07:00"


@pytest.mark.freeze_time(AFTERNOON)
async def test_restore_without_last_reset(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test a restored state without a reset time starts from zero."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(STANDING_TIME, "120.0"),
                {"native_value": 120.0, "native_unit_of_measurement": "min"},
            )
        ],
    )

    await _set_up(hass, mock_config_entry)

    assert _minutes(hass, STANDING_TIME) == 0.0


@pytest.mark.freeze_time(AFTERNOON)
async def test_reload_keeps_todays_totals(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
) -> None:
    """Test reloading the desk, as saving the options does, keeps the totals."""
    await _settle(hass, freezer)
    await _advance(hass, freezer, timedelta(minutes=10))

    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert _minutes(hass, SITTING_TIME) == 10.0
