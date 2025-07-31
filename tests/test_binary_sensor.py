"""Test the Desky Desk binary sensor platform."""
from __future__ import annotations

import pytest

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.desky_desk.const import DOMAIN

async def test_binary_sensor_setup(hass: HomeAssistant, init_integration):
    """Test binary sensor entity setup."""
    # First, trigger an update to set entities as available
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("binary_sensor.desky_desk_collision_detected")
    
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes.get("device_class") == "problem"

async def test_binary_sensor_collision_detection(hass: HomeAssistant, init_integration):
    """Test collision detection states."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # Test no collision
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("binary_sensor.desky_desk_collision_detected")
    assert state.state == STATE_OFF
    
    # Test collision detected
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": True,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("binary_sensor.desky_desk_collision_detected")
    assert state.state == STATE_ON

async def test_binary_sensor_availability(hass: HomeAssistant, init_integration):
    """Test binary sensor availability based on connection."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # Test connected
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("binary_sensor.desky_desk_collision_detected")
    assert state.state == STATE_OFF
    
    # Test disconnected
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": False,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("binary_sensor.desky_desk_collision_detected")
    assert state.state == STATE_UNAVAILABLE

async def test_binary_sensor_no_data(hass: HomeAssistant, init_integration):
    """Test binary sensor when no data available."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # Set data to None and notify listeners
    coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()
    
    state = hass.states.get("binary_sensor.desky_desk_collision_detected")
    assert state.state == STATE_UNAVAILABLE