"""Test Desky Desk switch platform."""
from __future__ import annotations

from unittest.mock import AsyncMock
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.desky_desk.const import DOMAIN


async def setup_coordinator_data(hass, mock_config_entry):
    """Set up coordinator with mock data."""
    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]
    coordinator.data = {
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
        "movement_direction": None,
        "light_color": 1,  # White
        "brightness": 50,
        "lighting_enabled": True,
        "vibration_enabled": True,
        "vibration_intensity": 75,
        "lock_status": False,
        "sensitivity_level": 2,  # Medium
        "height_limit_upper": 120.0,
        "height_limit_lower": 65.0,
        "limits_enabled": True,
        "touch_mode": 0,  # One press
        "unit_preference": "cm",
    }
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    return coordinator


async def test_switch_entities_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test switch entities are set up correctly."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    await setup_coordinator_data(hass, mock_config_entry)
    
    entity_registry = er.async_get(hass)
    
    # Check vibration switch
    entity = entity_registry.async_get("switch.desky_desk_vibration")
    assert entity
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_vibration"
    
    # Check lock switch
    entity = entity_registry.async_get("switch.desky_desk_lock")
    assert entity
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_lock"
    
    # Check states
    vibration_state = hass.states.get("switch.desky_desk_vibration")
    assert vibration_state
    assert vibration_state.state == STATE_ON
    
    lock_state = hass.states.get("switch.desky_desk_lock")
    assert lock_state
    assert lock_state.state == STATE_OFF


async def test_vibration_switch_toggle(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test toggling vibration switch."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    mock_device = coordinator._device
    
    # Mock the device method
    mock_device.set_vibration = AsyncMock(return_value=True)
    
    # Vibration starts ON, so turn it off first
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.desky_desk_vibration"},
        blocking=True,
    )
    
    mock_device.set_vibration.assert_called_once_with(False)
    
    # Update coordinator data to reflect the change
    coordinator.data["vibration_enabled"] = False
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    # Turn on vibration
    mock_device.set_vibration.reset_mock()
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.desky_desk_vibration"},
        blocking=True,
    )
    
    mock_device.set_vibration.assert_called_once_with(True)


async def test_lock_switch_toggle(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test toggling lock switch."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    mock_device = coordinator._device
    
    # Mock the device method
    mock_device.set_lock_status = AsyncMock(return_value=True)
    
    # Lock starts OFF, so turn it on first
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.desky_desk_lock"},
        blocking=True,
    )
    
    mock_device.set_lock_status.assert_called_once_with(True)
    
    # Update coordinator data to reflect the change
    coordinator.data["lock_status"] = True
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    # Turn off lock
    mock_device.set_lock_status.reset_mock()
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.desky_desk_lock"},
        blocking=True,
    )
    
    mock_device.set_lock_status.assert_called_once_with(False)


async def test_switch_state_updates(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test switch states update when coordinator data changes."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    
    # Initial states (from setup_coordinator_data)
    assert hass.states.get("switch.desky_desk_vibration").state == STATE_ON
    assert hass.states.get("switch.desky_desk_lock").state == STATE_OFF
    
    # Update vibration to off
    coordinator.data["vibration_enabled"] = False
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    assert hass.states.get("switch.desky_desk_vibration").state == STATE_OFF
    
    # Update lock to on
    coordinator.data["lock_status"] = True
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    assert hass.states.get("switch.desky_desk_lock").state == STATE_ON


async def test_switches_unavailable_when_disconnected(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test switches become unavailable when disconnected."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    
    # Simulate disconnection
    coordinator.data["is_connected"] = False
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    assert hass.states.get("switch.desky_desk_vibration").state == STATE_UNAVAILABLE
    assert hass.states.get("switch.desky_desk_lock").state == STATE_UNAVAILABLE


async def test_switch_error_handling(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test error handling when switch commands fail."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    mock_device = coordinator._device
    
    # Mock the device method to fail
    mock_device.set_vibration = AsyncMock(return_value=False)
    
    # Try to turn off vibration (should fail silently)
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.desky_desk_vibration"},
        blocking=True,
    )
    
    mock_device.set_vibration.assert_called_once_with(False)
    
    # State should remain unchanged since command failed
    assert hass.states.get("switch.desky_desk_vibration").state == STATE_ON