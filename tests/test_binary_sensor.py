"""Test the Desky Desk binary sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from . import disconnect_desk, notify_desk

ENTITY_ID = "binary_sensor.desky_desk_collision_detected"


async def test_collision_sensor_setup(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Test the collision sensor is a diagnostic problem sensor."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_DEVICE_CLASS] == BinarySensorDeviceClass.PROBLEM
    assert "connected" not in state.attributes

    entry = entity_registry.async_get(ENTITY_ID)
    assert entry is not None
    assert entry.unique_id == "AA:BB:CC:DD:EE:FF_collision"
    assert entry.translation_key == "collision"
    assert entry.entity_category is EntityCategory.DIAGNOSTIC


@pytest.mark.parametrize(
    ("collision", "expected_state"),
    [(True, STATE_ON), (False, STATE_OFF)],
)
async def test_collision_detection(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    collision: bool,
    expected_state: str,
) -> None:
    """Test the sensor follows the desk's collision detection."""
    notify_desk(mock_desk, collision_detected=collision)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == expected_state


async def test_collision_sensor_availability(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test the sensor is unavailable while disconnected and recovers on reconnect."""
    notify_desk(mock_desk, collision_detected=True)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_ON

    disconnect_desk(mock_desk)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    notify_desk(mock_desk, is_connected=True, collision_detected=False)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_OFF
