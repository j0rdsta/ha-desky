"""Test the Desky Desk cover platform."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_POSITION,
    DOMAIN as COVER_DOMAIN,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_SET_COVER_POSITION,
    SERVICE_STOP_COVER,
    CoverEntityFeature,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_OPEN,
    STATE_OPENING,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.desky_desk.const import DOMAIN, MAX_HEIGHT, MIN_HEIGHT

from . import disconnect_desk, notify_desk, set_desk_state

ENTITY_ID = "cover.desky_desk"


async def _call(hass: HomeAssistant, service: str, **data: object) -> None:
    """Call a cover service on the desk."""
    await hass.services.async_call(
        COVER_DOMAIN,
        service,
        {ATTR_ENTITY_ID: ENTITY_ID, **data},
        blocking=True,
    )


async def test_cover_setup(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Test the cover takes the device name and has no device class."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OPEN
    # (80 - 60) / (130 - 60) * 100, truncated
    assert state.attributes[ATTR_CURRENT_POSITION] == 28
    assert ATTR_DEVICE_CLASS not in state.attributes
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    entry = entity_registry.async_get(ENTITY_ID)
    assert entry is not None
    assert entry.unique_id == "AA:BB:CC:DD:EE:FF_cover"
    assert entry.translation_key == "desk"
    assert entry.original_name is None
    assert entry.original_device_class is None


@pytest.mark.parametrize(
    ("height", "expected_state", "expected_position"),
    [
        (50.0, STATE_CLOSED, 0),  # Below the range clamps to closed
        (MIN_HEIGHT, STATE_CLOSED, 0),
        (60.5, STATE_CLOSED, 0),  # Truncates to 0, so still closed
        (61.0, STATE_OPEN, 1),
        (95.0, STATE_OPEN, 50),
        (MAX_HEIGHT, STATE_OPEN, 100),
        (140.0, STATE_OPEN, 100),  # Above the range clamps to fully open
    ],
)
async def test_cover_position(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    height: float,
    expected_state: str,
    expected_position: int,
) -> None:
    """Test the desk height maps onto a 0-100 cover position."""
    notify_desk(mock_desk, height_cm=height)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == expected_state
    assert state.attributes[ATTR_CURRENT_POSITION] == expected_position


@pytest.mark.parametrize(
    ("is_moving", "direction", "expected_state"),
    [
        (True, "up", STATE_OPENING),
        (True, "down", STATE_CLOSING),
        (True, None, STATE_OPEN),
        (False, "up", STATE_OPEN),
        (False, "down", STATE_OPEN),
        (False, None, STATE_OPEN),
    ],
)
async def test_cover_movement(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    is_moving: bool,
    direction: str | None,
    expected_state: str,
) -> None:
    """Test the cover is opening or closing only while the desk moves."""
    notify_desk(mock_desk, is_moving=is_moving, movement_direction=direction)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == expected_state


@pytest.mark.parametrize(
    ("service", "command"),
    [
        (SERVICE_OPEN_COVER, "move_up"),
        (SERVICE_CLOSE_COVER, "move_down"),
        (SERVICE_STOP_COVER, "stop"),
    ],
)
async def test_cover_commands(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    service: str,
    command: str,
) -> None:
    """Test open, close and stop send the matching desk command."""
    await _call(hass, service)

    getattr(mock_desk, command).assert_awaited_once_with()


@pytest.mark.parametrize(
    ("position", "height"),
    [
        (0, MIN_HEIGHT),
        (50, 95.0),
        (75, 112.5),
        (100, MAX_HEIGHT),
    ],
)
async def test_cover_set_position(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    position: int,
    height: float,
) -> None:
    """Test setting a position moves the desk to the matching height."""
    # Without limits every position is allowed
    await set_desk_state(
        hass, init_integration, height_limit_upper=None, height_limit_lower=None
    )
    mock_desk.get_status.reset_mock()

    await _call(hass, SERVICE_SET_COVER_POSITION, **{ATTR_POSITION: position})
    await hass.async_block_till_done()

    mock_desk.move_to_height.assert_awaited_once_with(height)
    # The cover asks the coordinator to refresh so it tracks the movement
    mock_desk.get_status.assert_awaited_once_with()


async def test_cover_availability(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test the cover is unavailable while disconnected and recovers on reconnect."""
    disconnect_desk(mock_desk)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    notify_desk(mock_desk, is_connected=True, height_cm=MAX_HEIGHT)
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_OPEN
    assert state.attributes[ATTR_CURRENT_POSITION] == 100


async def test_set_position_outside_limits_rejected(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test a position whose height is outside the desk's limits is refused."""
    await set_desk_state(
        hass, init_integration, height_limit_upper=110.0, height_limit_lower=70.0
    )
    mock_desk.reset_mock()

    # Position 10 is 67 cm, below the 70 cm lower limit
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, SERVICE_SET_COVER_POSITION, **{ATTR_POSITION: 10})

    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "height_out_of_range"
    mock_desk.move_to_height.assert_not_awaited()
