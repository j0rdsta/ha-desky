"""Test the Desky Desk number platform."""
from __future__ import annotations

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


@pytest.mark.asyncio
async def test_number_setup(hass: HomeAssistant, init_integration):
    """Test number entity setup."""
    state = hass.states.get("number.desky_desk_height")
    
    assert state is not None
    assert state.state == "80.0"
    assert state.attributes.get("min") == MIN_HEIGHT
    assert state.attributes.get("max") == MAX_HEIGHT
    assert state.attributes.get("step") == 0.1
    assert state.attributes.get("unit_of_measurement") == UnitOfLength.CENTIMETERS


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_number_set_value_up(hass: HomeAssistant, init_integration):
    """Test setting number value to move desk up."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    mock_device = MagicMock()
    mock_device.move_up = AsyncMock()
    mock_device.move_down = AsyncMock()
    coordinator._device = mock_device
    
    # Set current height to 80cm
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    # Set target height to 100cm (should move up)
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.desky_desk_height",
            ATTR_VALUE: 100.0,
        },
        blocking=True,
    )
    
    mock_device.move_up.assert_called_once()
    mock_device.move_down.assert_not_called()


@pytest.mark.asyncio
async def test_number_set_value_down(hass: HomeAssistant, init_integration):
    """Test setting number value to move desk down."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    mock_device = MagicMock()
    mock_device.move_up = AsyncMock()
    mock_device.move_down = AsyncMock()
    coordinator._device = mock_device
    
    # Set current height to 80cm
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    # Set target height to 65cm (should move down)
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.desky_desk_height",
            ATTR_VALUE: 65.0,
        },
        blocking=True,
    )
    
    mock_device.move_down.assert_called_once()
    mock_device.move_up.assert_not_called()


@pytest.mark.asyncio
async def test_number_set_value_within_tolerance(hass: HomeAssistant, init_integration):
    """Test setting number value within tolerance (no movement)."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    mock_device = MagicMock()
    mock_device.move_up = AsyncMock()
    mock_device.move_down = AsyncMock()
    coordinator._device = mock_device
    
    # Set current height to 80cm
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    # Set target height to 80.3cm (within 0.5cm tolerance)
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.desky_desk_height",
            ATTR_VALUE: 80.3,
        },
        blocking=True,
    )
    
    mock_device.move_up.assert_not_called()
    mock_device.move_down.assert_not_called()


@pytest.mark.asyncio
async def test_number_no_data(hass: HomeAssistant, init_integration):
    """Test number when no data available."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # Set data to None and notify listeners
    coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()
    
    state = hass.states.get("number.desky_desk_height")
    assert state.state == STATE_UNAVAILABLE