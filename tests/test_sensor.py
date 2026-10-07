"""Test Desky Desk sensor platform."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import ATTR_OPTIONS, SensorEntityDescription
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfLength,
)
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.desky_desk.const import LIGHT_COLORS, POSTURE_SETTLE_SECONDS
from custom_components.desky_desk.sensor import DeskSensor

from . import disconnect_desk, notify_desk, set_desk_state

HEIGHT_DISPLAY = "sensor.desky_desk_height_display"
LED_COLOR = "sensor.desky_desk_led_color"
VIBRATION_INTENSITY = "sensor.desky_desk_vibration_intensity_display"
POSTURE = "sensor.desky_desk_posture"


async def test_sensor_states(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the sensors report the desk's state with their units and attributes."""
    height = hass.states.get(HEIGHT_DISPLAY)
    assert height is not None
    assert height.state == "80.0"
    assert height.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfLength.CENTIMETERS
    assert height.attributes["height_cm"] == 80.0
    assert height.attributes["upper_limit_cm"] == 120.0
    assert height.attributes["lower_limit_cm"] == 65.0

    led_color = hass.states.get(LED_COLOR)
    assert led_color is not None
    assert led_color.state == "White"
    assert led_color.attributes["color_value"] == 1
    assert led_color.attributes["brightness"] == 50
    assert led_color.attributes["lighting_enabled"] is True

    vibration = hass.states.get(VIBRATION_INTENSITY)
    assert vibration is not None
    assert vibration.state == "75"
    assert vibration.attributes[ATTR_UNIT_OF_MEASUREMENT] == PERCENTAGE
    assert vibration.attributes["vibration_enabled"] is True


async def test_height_display_in_inches(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the height display follows the desk's display unit."""
    await set_desk_state(hass, init_integration, unit_preference="in", height_cm=101.6)

    state = hass.states.get(HEIGHT_DISPLAY)
    assert state is not None
    assert state.state == "40.0"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfLength.INCHES
    assert state.attributes["height_cm"] == 101.6

    await set_desk_state(hass, init_integration, unit_preference="cm")

    state = hass.states.get(HEIGHT_DISPLAY)
    assert state is not None
    assert state.state == "101.6"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfLength.CENTIMETERS


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


async def test_height_display_without_limits(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the height limit attributes are only present while limits are enabled."""
    await set_desk_state(hass, init_integration, limits_enabled=False)

    state = hass.states.get(HEIGHT_DISPLAY)
    assert state is not None
    assert state.attributes["height_cm"] == 80.0
    assert "upper_limit_cm" not in state.attributes
    assert "lower_limit_cm" not in state.attributes


@pytest.mark.parametrize(("light_color", "name"), LIGHT_COLORS.items())
async def test_led_color(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    light_color: int,
    name: str,
) -> None:
    """Test the LED colour sensor names every known colour."""
    await set_desk_state(hass, init_integration, light_color=light_color)

    state = hass.states.get(LED_COLOR)
    assert state is not None
    assert state.state == name
    assert state.attributes["color_value"] == light_color


@pytest.mark.parametrize("light_color", [99, 0, None])
async def test_led_color_unknown(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    light_color: int | None,
) -> None:
    """Test the LED colour sensor reports Unknown for an unrecognised colour."""
    await set_desk_state(hass, init_integration, light_color=light_color)

    state = hass.states.get(LED_COLOR)
    assert state is not None
    assert state.state == "Unknown"


@pytest.mark.parametrize(
    ("intensity", "expected"),
    [(0, "0"), (25, "25"), (100, "100"), (None, "0")],
)
async def test_vibration_intensity(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    intensity: int | None,
    expected: str,
) -> None:
    """Test the vibration intensity sensor, which reads 0 before the desk reports."""
    await set_desk_state(hass, init_integration, vibration_intensity=intensity)

    state = hass.states.get(VIBRATION_INTENSITY)
    assert state is not None
    assert state.state == expected
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == PERCENTAGE


async def test_sensors_unavailable_when_disconnected(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the sensors become unavailable when the desk disconnects."""
    disconnect_desk(mock_desk)
    await hass.async_block_till_done()

    for entity_id in (HEIGHT_DISPLAY, LED_COLOR, VIBRATION_INTENSITY):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_UNAVAILABLE


async def test_sensor_unknown_key(init_integration: MockConfigEntry) -> None:
    """Test a sensor with an unrecognised key has no value, unit or attributes."""
    entity = DeskSensor(
        init_integration.runtime_data, SensorEntityDescription(key="unknown")
    )

    assert entity.native_value is None
    assert entity.native_unit_of_measurement is None
    assert entity.extra_state_attributes is None


async def test_height_display_while_unit_unreported(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the height display uses centimetres until the desk reports a unit."""
    await set_desk_state(hass, init_integration, unit_preference=None, height_cm=69.8)

    state = hass.states.get(HEIGHT_DISPLAY)
    assert state is not None
    assert state.state == "69.8"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfLength.CENTIMETERS


async def test_height_display_unit_changed_while_connected(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test a switch to inches at 69.8 cm shows about 27.4 in, keeping height_cm."""
    await set_desk_state(hass, init_integration, unit_preference="cm", height_cm=69.8)
    assert hass.states.get(HEIGHT_DISPLAY).state == "69.8"

    # The desk reports inches; its next height (27.4 in) decodes to 69.6 cm
    await set_desk_state(hass, init_integration, unit_preference="in", height_cm=69.6)

    state = hass.states.get(HEIGHT_DISPLAY)
    assert state.state == "27.4"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfLength.INCHES
    assert abs(state.attributes["height_cm"] - 69.8) < 0.5


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
