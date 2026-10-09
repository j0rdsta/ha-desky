"""Test Desky Desk sensor platform."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import (
    ATTR_OPTIONS,
    ATTR_STATE_CLASS,
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfLength,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.desky_desk.const import DOMAIN, POSTURE_SETTLE_SECONDS

from . import disconnect_desk, notify_desk, set_desk_state

HEIGHT_DISPLAY = "sensor.desky_desk_height_display"
POSTURE = "sensor.desky_desk_posture"


async def test_height_display(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the height display is a distance in centimetres with no extra attributes."""
    height = hass.states.get(HEIGHT_DISPLAY)
    assert height is not None
    assert height.state == "80.0"
    assert height.attributes == {
        ATTR_FRIENDLY_NAME: "Desky Desk Height display",
        ATTR_DEVICE_CLASS: SensorDeviceClass.DISTANCE,
        ATTR_STATE_CLASS: SensorStateClass.MEASUREMENT,
        ATTR_UNIT_OF_MEASUREMENT: UnitOfLength.CENTIMETERS,
    }


@pytest.mark.parametrize("unit", [None, "cm", "in"])
async def test_height_display_ignores_the_desk_display_unit(
    hass: HomeAssistant, init_integration: MockConfigEntry, unit: str | None
) -> None:
    """Test the height display is in centimetres whatever unit the desk shows."""
    await set_desk_state(hass, init_integration, unit_preference=unit, height_cm=69.6)

    state = hass.states.get(HEIGHT_DISPLAY)
    assert state is not None
    assert state.state == "69.6"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfLength.CENTIMETERS


async def test_height_display_keeps_inches_after_upgrade(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test a height display that showed inches before 2.0.0 still shows inches."""
    mock_config_entry.add_to_hass(hass)
    entity_registry.async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        f"{mock_config_entry.unique_id}_height_display",
        suggested_object_id="desky_desk_height_display",
        config_entry=mock_config_entry,
        unit_of_measurement=UnitOfLength.INCHES,
    )

    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=MagicMock(address=mock_config_entry.unique_id),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(HEIGHT_DISPLAY)
    assert state is not None
    # The desk is at 80.0 cm
    assert float(state.state) == pytest.approx(31.5, abs=0.05)
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfLength.INCHES


async def test_height_display_in_the_unit_the_user_picks(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Test a user who picks inches in the entity settings sees inches."""
    entity_registry.async_update_entity_options(
        HEIGHT_DISPLAY, SENSOR_DOMAIN, {"unit_of_measurement": UnitOfLength.INCHES}
    )
    await set_desk_state(hass, init_integration, height_cm=101.6)

    state = hass.states.get(HEIGHT_DISPLAY)
    assert state is not None
    assert float(state.state) == pytest.approx(40.0)
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfLength.INCHES
    assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.MEASUREMENT


@pytest.mark.parametrize(
    ("height_cm", "expected"),
    [
        (65.0, "65.0"),
        (80.5, "80.5"),
        (100.25, "100.2"),  # 100.25 is stored just below .25, so it rounds down
        (120.99, "121.0"),
    ],
)
async def test_height_display_precision(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    height_cm: float,
    expected: str,
) -> None:
    """Test the height display is rounded to one decimal place."""
    await set_desk_state(hass, init_integration, height_cm=height_cm)

    state = hass.states.get(HEIGHT_DISPLAY)
    assert state is not None
    assert state.state == expected


async def test_height_display_unknown_before_the_first_height(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the 0 cm placeholder before the desk reports a height is not recorded."""
    await set_desk_state(hass, init_integration, height_cm=0.0)

    assert hass.states.get(HEIGHT_DISPLAY).state == STATE_UNKNOWN


async def test_sensors_unavailable_when_disconnected(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the sensors become unavailable when the desk disconnects."""
    disconnect_desk(mock_desk)
    await hass.async_block_till_done()

    for entity_id in (HEIGHT_DISPLAY, POSTURE):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_UNAVAILABLE


async def test_posture_sensor(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test the posture sensor follows the desk, and is unknown until it settles."""
    state = hass.states.get(POSTURE)
    assert state is not None
    assert state.state == STATE_UNKNOWN
    assert state.attributes[ATTR_OPTIONS] == ["sitting", "standing"]

    freezer.tick(timedelta(seconds=POSTURE_SETTLE_SECONDS))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(POSTURE)
    assert state is not None
    assert state.state == "sitting"

    notify_desk(mock_desk, height_cm=110.0)
    freezer.tick(timedelta(seconds=POSTURE_SETTLE_SECONDS))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(POSTURE)
    assert state is not None
    assert state.state == "standing"

    disconnect_desk(mock_desk)
    await hass.async_block_till_done()
    state = hass.states.get(POSTURE)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE
