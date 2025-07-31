"""Test the Desky Desk button platform."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.desky_desk.const import DOMAIN

async def test_button_setup(hass: HomeAssistant, init_integration):
    """Test button entities setup."""
    # First, trigger an update to set entities as available
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    # Check all preset buttons are created
    for i in range(1, 5):
        state = hass.states.get(f"button.desky_desk_preset_{i}")
        assert state is not None
        assert state.state != STATE_UNAVAILABLE
    
    # Check movement buttons are created
    state = hass.states.get("button.desky_desk_move_up")
    assert state is not None
    assert state.state != STATE_UNAVAILABLE
    
    state = hass.states.get("button.desky_desk_move_down")
    assert state is not None
    assert state.state != STATE_UNAVAILABLE

async def test_button_availability(hass: HomeAssistant, init_integration):
    """Test button availability based on connection."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # Test connected
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("button.desky_desk_preset_1")
    assert state.state != STATE_UNAVAILABLE
    
    # Test disconnected
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": False,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("button.desky_desk_preset_1")
    assert state.state == STATE_UNAVAILABLE

async def test_button_press_preset_1(hass: HomeAssistant, init_integration):
    """Test pressing preset 1 button."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # First make sure the entity is available
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    # Now replace the device with a fresh mock for testing
    mock_device = MagicMock()
    mock_device.move_to_preset = AsyncMock()
    coordinator._device = mock_device
    
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.desky_desk_preset_1"},
        blocking=True,
    )
    
    mock_device.move_to_preset.assert_called_once_with(1)

async def test_button_press_preset_2(hass: HomeAssistant, init_integration):
    """Test pressing preset 2 button."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # First make sure the entity is available
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    # Now replace the device with a fresh mock for testing
    mock_device = MagicMock()
    mock_device.move_to_preset = AsyncMock()
    coordinator._device = mock_device
    
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.desky_desk_preset_2"},
        blocking=True,
    )
    
    mock_device.move_to_preset.assert_called_once_with(2)

async def test_button_press_preset_3(hass: HomeAssistant, init_integration):
    """Test pressing preset 3 button."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # First make sure the entity is available
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    # Now replace the device with a fresh mock for testing
    mock_device = MagicMock()
    mock_device.move_to_preset = AsyncMock()
    coordinator._device = mock_device
    
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.desky_desk_preset_3"},
        blocking=True,
    )
    
    mock_device.move_to_preset.assert_called_once_with(3)

async def test_button_press_preset_4(hass: HomeAssistant, init_integration):
    """Test pressing preset 4 button."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # First make sure the entity is available
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    # Now replace the device with a fresh mock for testing
    mock_device = MagicMock()
    mock_device.move_to_preset = AsyncMock()
    coordinator._device = mock_device
    
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.desky_desk_preset_4"},
        blocking=True,
    )
    
    mock_device.move_to_preset.assert_called_once_with(4)

async def test_button_press_move_up(hass: HomeAssistant, init_integration):
    """Test pressing move up button."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # First make sure the entity is available
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    # Now replace the device with a fresh mock for testing
    mock_device = MagicMock()
    mock_device.move_up = AsyncMock()
    coordinator._device = mock_device
    
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.desky_desk_move_up"},
        blocking=True,
    )
    
    mock_device.move_up.assert_called_once()

async def test_button_press_move_down(hass: HomeAssistant, init_integration):
    """Test pressing move down button."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # First make sure the entity is available
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    # Now replace the device with a fresh mock for testing
    mock_device = MagicMock()
    mock_device.move_down = AsyncMock()
    coordinator._device = mock_device
    
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.desky_desk_move_down"},
        blocking=True,
    )
    
    mock_device.move_down.assert_called_once()

async def test_button_press_no_device(hass: HomeAssistant, init_integration):
    """Test pressing button when device is None."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    coordinator._device = None
    
    # Should not raise exception
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.desky_desk_preset_1"},
        blocking=True,
    )