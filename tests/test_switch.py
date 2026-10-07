"""Test the Desky Desk switch platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    SwitchEntityDescription,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.desky_desk.switch import SWITCH_DESCRIPTIONS, DeskSwitch

from . import disconnect_desk, notify_desk, set_desk_state

VIBRATION = "switch.desky_desk_vibration"
LOCK = "switch.desky_desk_lock"

DESCRIPTIONS = {description.key: description for description in SWITCH_DESCRIPTIONS}


@pytest.mark.parametrize(
    ("entity_id", "unique_id_suffix", "entity_category", "state"),
    [
        (VIBRATION, "vibration", EntityCategory.CONFIG, STATE_ON),
        (LOCK, "lock", None, STATE_OFF),
    ],
)
async def test_switch_setup(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
    entity_id: str,
    unique_id_suffix: str,
    entity_category: EntityCategory | None,
    state: str,
) -> None:
    """Test each switch is registered with the desk's state."""
    entry = entity_registry.async_get(entity_id)
    assert entry is not None
    assert entry.unique_id == f"{init_integration.unique_id}_{unique_id_suffix}"
    assert entry.entity_category == entity_category

    assert hass.states.get(entity_id).state == state


@pytest.mark.parametrize(
    ("entity_id", "field", "value", "expected"),
    [
        (VIBRATION, "vibration_enabled", True, STATE_ON),
        (VIBRATION, "vibration_enabled", False, STATE_OFF),
        # The desk has not reported its vibration setting yet
        (VIBRATION, "vibration_enabled", None, STATE_OFF),
        (LOCK, "lock_status", True, STATE_ON),
        (LOCK, "lock_status", False, STATE_OFF),
    ],
)
async def test_switch_state(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id: str,
    field: str,
    value: Any,
    expected: str,
) -> None:
    """Test each switch follows the desk's reported state."""
    await set_desk_state(hass, init_integration, **{field: value})

    assert hass.states.get(entity_id).state == expected


@pytest.mark.parametrize(
    ("entity_id", "service", "command", "argument", "follow_up"),
    [
        (VIBRATION, SERVICE_TURN_ON, "set_vibration", True, "get_vibration_status"),
        (VIBRATION, SERVICE_TURN_OFF, "set_vibration", False, "get_vibration_status"),
        (LOCK, SERVICE_TURN_ON, "set_lock_status", True, "get_lock_status"),
        (LOCK, SERVICE_TURN_OFF, "set_lock_status", False, "get_lock_status"),
    ],
)
async def test_switch_commands(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    entity_id: str,
    service: str,
    command: str,
    argument: bool,
    follow_up: str,
) -> None:
    """Test turning a switch on or off sends the command, then reads it back."""
    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    getattr(mock_desk, command).assert_awaited_once_with(argument)
    getattr(mock_desk, follow_up).assert_awaited_once_with()


@pytest.mark.parametrize(
    ("entity_id", "service", "field", "value", "before", "after"),
    [
        (VIBRATION, SERVICE_TURN_OFF, "vibration_enabled", False, STATE_ON, STATE_OFF),
        (LOCK, SERVICE_TURN_ON, "lock_status", True, STATE_OFF, STATE_ON),
    ],
)
async def test_switch_state_follows_desk(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    entity_id: str,
    service: str,
    field: str,
    value: bool,
    before: str,
    after: str,
) -> None:
    """Test a switch only changes once the desk reports the new state.

    A command the desk ignores leaves the switch as it was.
    """
    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == before

    notify_desk(mock_desk, **{field: value})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == after


async def test_vibration_intensity_attribute(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the vibration switch reports the intensity only when it is known."""
    assert hass.states.get(VIBRATION).attributes["intensity"] == 75
    assert "intensity" not in hass.states.get(LOCK).attributes

    await set_desk_state(hass, init_integration, vibration_intensity=40)
    assert hass.states.get(VIBRATION).attributes["intensity"] == 40

    await set_desk_state(hass, init_integration, vibration_intensity=None)
    assert "intensity" not in hass.states.get(VIBRATION).attributes


async def test_switches_unavailable_when_disconnected(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the switches become unavailable and send nothing while disconnected."""
    disconnect_desk(mock_desk)
    await hass.async_block_till_done()

    assert hass.states.get(VIBRATION).state == STATE_UNAVAILABLE
    assert hass.states.get(LOCK).state == STATE_UNAVAILABLE

    # Home Assistant skips unavailable entities, so call the entities directly too
    for service in (SERVICE_TURN_ON, SERVICE_TURN_OFF):
        await hass.services.async_call(
            SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: [VIBRATION, LOCK]}, blocking=True
        )
    for description in SWITCH_DESCRIPTIONS:
        entity = DeskSwitch(init_integration.runtime_data, description)
        await entity.async_turn_on()
        await entity.async_turn_off()

    mock_desk.set_vibration.assert_not_awaited()
    mock_desk.set_lock_status.assert_not_awaited()


async def test_switch_unknown_key(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test a switch with an unrecognised key is off and sends nothing."""
    entity = DeskSwitch(
        init_integration.runtime_data, SwitchEntityDescription(key="unknown")
    )

    assert entity.is_on is False
    assert entity.extra_state_attributes is None

    await entity.async_turn_on()
    await entity.async_turn_off()

    mock_desk.set_vibration.assert_not_awaited()
    mock_desk.set_lock_status.assert_not_awaited()
    mock_desk.get_vibration_status.assert_not_awaited()
    mock_desk.get_lock_status.assert_not_awaited()
