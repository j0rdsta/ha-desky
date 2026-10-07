"""Test the Desky Desk button platform."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

from homeassistant.components.button import (
    DOMAIN as BUTTON_DOMAIN,
    SERVICE_PRESS,
    ButtonEntity,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.desky_desk.button import (
    DeskyMoveDownButton,
    DeskyMoveUpButton,
    DeskyPresetButton,
)
from custom_components.desky_desk.coordinator import DeskUpdateCoordinator

from . import disconnect_desk, notify_desk

BUTTONS = [
    "button.desky_desk_preset_1",
    "button.desky_desk_preset_2",
    "button.desky_desk_preset_3",
    "button.desky_desk_preset_4",
    "button.desky_desk_move_up",
    "button.desky_desk_move_down",
]


async def _press(hass: HomeAssistant, entity_id: str) -> None:
    """Press a button through the button service."""
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )


@pytest.mark.parametrize("preset", [1, 2, 3, 4])
async def test_preset_button(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    preset: int,
) -> None:
    """Test each preset button is named from its number and moves to that preset."""
    entity_id = f"button.desky_desk_preset_{preset}"
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN
    assert state.attributes["friendly_name"] == f"Desky Desk Preset {preset}"

    await _press(hass, entity_id)

    mock_desk.move_to_preset.assert_awaited_once_with(preset)
    mock_desk.move_up.assert_not_called()
    mock_desk.move_down.assert_not_called()
    # A pressed button records when it was last pressed
    assert hass.states.get(entity_id).state != STATE_UNKNOWN


@pytest.mark.parametrize(
    ("entity_id", "friendly_name", "command"),
    [
        ("button.desky_desk_move_up", "Desky Desk Move up", "move_up"),
        ("button.desky_desk_move_down", "Desky Desk Move down", "move_down"),
    ],
)
async def test_move_button(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    entity_id: str,
    friendly_name: str,
    command: str,
) -> None:
    """Test the move buttons send their movement command."""
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["friendly_name"] == friendly_name

    await _press(hass, entity_id)

    getattr(mock_desk, command).assert_awaited_once_with()
    mock_desk.move_to_preset.assert_not_called()


async def test_buttons_follow_connection(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the buttons go unavailable on disconnect and come back on reconnect."""
    assert all(
        hass.states.get(entity_id).state == STATE_UNKNOWN for entity_id in BUTTONS
    )

    disconnect_desk(mock_desk)
    await hass.async_block_till_done()
    assert all(
        hass.states.get(entity_id).state == STATE_UNAVAILABLE for entity_id in BUTTONS
    )

    # Pressing an unavailable button sends nothing to the desk
    await _press(hass, "button.desky_desk_preset_1")
    mock_desk.move_to_preset.assert_not_called()

    notify_desk(mock_desk, is_connected=True)
    await hass.async_block_till_done()
    assert all(
        hass.states.get(entity_id).state == STATE_UNKNOWN for entity_id in BUTTONS
    )


@pytest.mark.parametrize(
    "button_factory",
    [
        lambda coordinator: DeskyPresetButton(coordinator, 1),
        DeskyMoveUpButton,
        DeskyMoveDownButton,
    ],
)
async def test_press_without_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    button_factory: Callable[[DeskUpdateCoordinator], ButtonEntity],
) -> None:
    """Test a press is ignored when the coordinator has no BLE device yet."""
    # A coordinator that never connected has no device
    coordinator = DeskUpdateCoordinator(hass, init_integration)
    assert coordinator.device is None

    await button_factory(coordinator).async_press()

    mock_desk.move_to_preset.assert_not_called()
    mock_desk.move_up.assert_not_called()
    mock_desk.move_down.assert_not_called()
