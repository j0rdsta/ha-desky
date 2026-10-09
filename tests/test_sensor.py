"""Test Desky Desk sensor platform."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import (
    ATTR_OPTIONS,
    ATTR_STATE_CLASS,
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntityDescription,
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

from custom_components.desky_desk.const import POSTURE_SETTLE_SECONDS
from custom_components.desky_desk.sensor import DeskSensor

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


async def test_height_display_ignores_the_desk_display_unit(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the height display stays in centimetres while the desk shows inches."""
    await set_desk_state(hass, init_integration, unit_preference="in", height_cm=101.6)

    state = hass.states.get(HEIGHT_DISPLAY)
    assert state is not None
    assert state.state == "101.6"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfLength.CENTIMETERS


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


async def test_sensor_unknown_key(init_integration: MockConfigEntry) -> None:
    """Test a sensor with an unrecognised key has no value or unit."""
    entity = DeskSensor(
        init_integration.runtime_data, SensorEntityDescription(key="unknown")
    )

    assert entity.native_value is None
    assert entity.native_unit_of_measurement is None


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
    """Test a switch to inches on the desk keeps the height display in centimetres."""
    await set_desk_state(hass, init_integration, unit_preference="cm", height_cm=69.8)
    assert hass.states.get(HEIGHT_DISPLAY).state == "69.8"

    # The desk reports inches; its next height (27.4 in) decodes to 69.6 cm
    await set_desk_state(hass, init_integration, unit_preference="in", height_cm=69.6)

    state = hass.states.get(HEIGHT_DISPLAY)
    assert state.state == "69.6"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfLength.CENTIMETERS


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
