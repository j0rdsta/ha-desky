"""Test the Desky Desk number platform."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.number import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_STEP,
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
    NumberEntityDescription,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfLength,
)
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.desky_desk.const import MAX_HEIGHT, MIN_HEIGHT
from custom_components.desky_desk.number import DeskNumber

from . import disconnect_desk, notify_desk, set_desk_state

HEIGHT = "number.desky_desk_height"
UPPER_LIMIT = "number.desky_desk_upper_height_limit"
LOWER_LIMIT = "number.desky_desk_lower_height_limit"
VIBRATION_INTENSITY = "number.desky_desk_vibration_intensity"
NUMBERS = [HEIGHT, UPPER_LIMIT, LOWER_LIMIT, VIBRATION_INTENSITY]


async def _set_value(hass: HomeAssistant, entity_id: str, value: float) -> None:
    """Set a number through the number service."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )


async def test_height_number(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the height number reports the desk height in centimetres."""
    state = hass.states.get(HEIGHT)
    assert state is not None
    assert state.state == "80.0"
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Desky Desk Height"
    assert state.attributes[ATTR_MIN] == MIN_HEIGHT
    assert state.attributes[ATTR_MAX] == MAX_HEIGHT
    assert state.attributes[ATTR_STEP] == 0.1
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfLength.CENTIMETERS

    notify_desk(mock_desk, height_cm=95.5)
    await hass.async_block_till_done()

    assert hass.states.get(HEIGHT).state == "95.5"


@pytest.mark.parametrize("height", [MIN_HEIGHT, 85.7, 100.0, MAX_HEIGHT])
async def test_set_height(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    height: float,
) -> None:
    """Test setting the height moves the desk there and polls it for progress."""
    mock_desk.get_status.reset_mock()

    await _set_value(hass, HEIGHT, height)

    mock_desk.move_to_height.assert_awaited_once_with(height)
    # The coordinator refresh asks the desk for its status
    mock_desk.get_status.assert_awaited_once_with()


@pytest.mark.parametrize(
    ("entity_id", "friendly_name", "value", "unit", "step"),
    [
        (
            UPPER_LIMIT,
            "Desky Desk Upper height limit",
            "120.0",
            UnitOfLength.CENTIMETERS,
            1.0,
        ),
        (
            LOWER_LIMIT,
            "Desky Desk Lower height limit",
            "65.0",
            UnitOfLength.CENTIMETERS,
            1.0,
        ),
        (VIBRATION_INTENSITY, "Desky Desk Vibration intensity", "75", PERCENTAGE, 1),
    ],
)
async def test_desk_number_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id: str,
    friendly_name: str,
    value: str,
    unit: str,
    step: float,
) -> None:
    """Test the setting numbers report the desk's configured values."""
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == value
    assert state.attributes[ATTR_FRIENDLY_NAME] == friendly_name
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == unit
    assert state.attributes[ATTR_STEP] == step


@pytest.mark.parametrize(
    ("entity_id", "minimum", "maximum"),
    [
        (UPPER_LIMIT, MIN_HEIGHT, MAX_HEIGHT),
        (LOWER_LIMIT, MIN_HEIGHT, MAX_HEIGHT),
        (VIBRATION_INTENSITY, 0, 100),
    ],
)
async def test_desk_number_range(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id: str,
    minimum: float,
    maximum: float,
) -> None:
    """Test the setting numbers expose the range the desk accepts."""
    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_MIN] == minimum
    assert state.attributes[ATTR_MAX] == maximum


@pytest.mark.parametrize(
    ("entity_id", "value", "setter", "sent", "getter"),
    [
        (UPPER_LIMIT, 125.0, "set_height_limit_upper", 125.0, "get_limits"),
        (LOWER_LIMIT, 70.0, "set_height_limit_lower", 70.0, "get_limits"),
        (
            VIBRATION_INTENSITY,
            50,
            "set_vibration_intensity",
            50,
            "get_vibration_intensity",
        ),
    ],
)
async def test_set_desk_number(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    entity_id: str,
    value: float,
    setter: str,
    sent: float,
    getter: str,
) -> None:
    """Test setting a value sends it to the desk and reads it back."""
    await _set_value(hass, entity_id, value)

    getattr(mock_desk, setter).assert_awaited_once_with(sent)
    getattr(mock_desk, getter).assert_awaited_once_with()


async def test_vibration_intensity_sent_as_integer(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the vibration intensity is sent to the desk as a whole number."""
    await _set_value(hass, VIBRATION_INTENSITY, 42.0)

    mock_desk.set_vibration_intensity.assert_awaited_once_with(42)
    assert isinstance(mock_desk.set_vibration_intensity.call_args.args[0], int)


async def test_limits_enabled_attribute(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test only the height limit numbers report whether the limits are enabled."""
    assert hass.states.get(UPPER_LIMIT).attributes["limits_enabled"] is True
    assert hass.states.get(LOWER_LIMIT).attributes["limits_enabled"] is True
    assert "limits_enabled" not in hass.states.get(VIBRATION_INTENSITY).attributes
    assert "limits_enabled" not in hass.states.get(HEIGHT).attributes

    await set_desk_state(hass, init_integration, limits_enabled=False)

    assert hass.states.get(UPPER_LIMIT).attributes["limits_enabled"] is False
    assert hass.states.get(LOWER_LIMIT).attributes["limits_enabled"] is False


async def test_desk_numbers_without_values(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test settings the desk has not reported show as unknown."""
    await set_desk_state(
        hass,
        init_integration,
        height_limit_upper=None,
        height_limit_lower=None,
        vibration_intensity=None,
    )

    assert hass.states.get(UPPER_LIMIT).state == STATE_UNKNOWN
    assert hass.states.get(LOWER_LIMIT).state == STATE_UNKNOWN
    assert hass.states.get(VIBRATION_INTENSITY).state == STATE_UNKNOWN
    assert hass.states.get(HEIGHT).state == "80.0"


async def test_numbers_follow_connection(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the numbers go unavailable on disconnect and come back on reconnect."""
    disconnect_desk(mock_desk)
    await hass.async_block_till_done()
    assert all(
        hass.states.get(entity_id).state == STATE_UNAVAILABLE for entity_id in NUMBERS
    )

    # Setting an unavailable number sends nothing to the desk
    await _set_value(hass, UPPER_LIMIT, 110.0)
    mock_desk.set_height_limit_upper.assert_not_called()

    notify_desk(mock_desk, is_connected=True, height_cm=90.0)
    await hass.async_block_till_done()
    assert hass.states.get(HEIGHT).state == "90.0"
    assert hass.states.get(UPPER_LIMIT).state == "120.0"
    assert hass.states.get(LOWER_LIMIT).state == "65.0"
    assert hass.states.get(VIBRATION_INTENSITY).state == "75"


async def test_desk_number_unknown_key(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test a number with an unrecognised key has no value and sends nothing."""
    entity = DeskNumber(
        init_integration.runtime_data, NumberEntityDescription(key="unknown")
    )
    mock_desk.reset_mock()

    assert entity.available
    assert entity.native_value is None
    assert entity.extra_state_attributes is None

    await entity.async_set_native_value(42.0)

    assert mock_desk.method_calls == []
