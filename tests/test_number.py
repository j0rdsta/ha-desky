"""Test the Desky Desk number platform."""
from __future__ import annotations

from custom_components.desky_desk.const import DOMAIN

from unittest.mock import AsyncMock, MagicMock
import pytest

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, UnitOfLength
from homeassistant.core import HomeAssistant

from custom_components.desky_desk.const import (
    DEFAULT_HEIGHT,
    DOMAIN,
    MAX_HEIGHT,
    MIN_HEIGHT,
)

async def test_number_setup(hass: HomeAssistant, init_integration):
    """Test number entity setup."""
    # First, trigger an update to set entities as available
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("number.desky_desk_height")
    
    assert state is not None
    assert state.state == "80.0"
    assert state.attributes.get("min") == MIN_HEIGHT
    assert state.attributes.get("max") == MAX_HEIGHT
    assert state.attributes.get("step") == 0.1
    assert state.attributes.get("unit_of_measurement") == UnitOfLength.CENTIMETERS

async def test_number_value_updates(hass: HomeAssistant, init_integration):
    """Test number value updates from coordinator."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # Test value update
    coordinator.async_set_updated_data({
        "height_cm": 95.5,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("number.desky_desk_height")
    assert state.state == "95.5"

async def test_number_availability(hass: HomeAssistant, init_integration):
    """Test number availability based on connection."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # Test disconnected
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": False,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("number.desky_desk_height")
    assert state.state == STATE_UNAVAILABLE

async def test_number_set_value_direct_height(hass: HomeAssistant, init_integration):
    """Test setting number value uses move_to_height."""
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
    mock_device.move_to_height = AsyncMock()
    coordinator._device = mock_device
    coordinator.async_request_refresh = AsyncMock()
    
    # Test setting to 100cm
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.desky_desk_height",
            ATTR_VALUE: 100.0,
        },
        blocking=True,
    )
    
    mock_device.move_to_height.assert_called_once_with(100.0)
    coordinator.async_request_refresh.assert_called_once()
    
    # Reset mocks
    mock_device.move_to_height.reset_mock()
    coordinator.async_request_refresh.reset_mock()
    
    # Test setting to minimum height
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.desky_desk_height",
            ATTR_VALUE: MIN_HEIGHT,
        },
        blocking=True,
    )
    
    mock_device.move_to_height.assert_called_once_with(MIN_HEIGHT)
    
    # Reset mocks
    mock_device.move_to_height.reset_mock()
    
    # Test setting to maximum height
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.desky_desk_height",
            ATTR_VALUE: MAX_HEIGHT,
        },
        blocking=True,
    )
    
    mock_device.move_to_height.assert_called_once_with(MAX_HEIGHT)

async def test_number_set_value_edge_cases(hass: HomeAssistant, init_integration):
    """Test setting number value with edge cases."""
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
    mock_device.move_to_height = AsyncMock()
    coordinator._device = mock_device
    coordinator.async_request_refresh = AsyncMock()
    
    # Test decimal precision
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.desky_desk_height",
            ATTR_VALUE: 85.7,
        },
        blocking=True,
    )
    
    mock_device.move_to_height.assert_called_once_with(85.7)

async def test_number_no_data(hass: HomeAssistant, init_integration):
    """Test number when no data available."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # Set data to None and notify listeners
    coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()
    
    state = hass.states.get("number.desky_desk_height")
    assert state.state == STATE_UNAVAILABLE