"""Test the Desky Desk cover platform."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from homeassistant.components.cover import (
    ATTR_POSITION,
    DOMAIN as COVER_DOMAIN,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_SET_COVER_POSITION,
    SERVICE_STOP_COVER,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.desky_desk.const import DOMAIN, MAX_HEIGHT, MIN_HEIGHT


@pytest.mark.asyncio
async def test_cover_setup(hass: HomeAssistant, init_integration):
    """Test cover entity setup."""
    state = hass.states.get("cover.desky_desk")
    
    assert state is not None
    assert state.state == "open"  # Default position
    assert state.attributes.get("current_position") == 28  # (80-60)/(130-60)*100


@pytest.mark.asyncio
async def test_cover_position_calculations(hass: HomeAssistant, init_integration):
    """Test cover position calculations."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # Test minimum height (closed)
    coordinator.async_set_updated_data({
        "height_cm": MIN_HEIGHT,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("cover.desky_desk")
    assert state.state == "closed"
    assert state.attributes.get("current_position") == 0
    
    # Test maximum height (open)
    coordinator.async_set_updated_data({
        "height_cm": MAX_HEIGHT,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("cover.desky_desk")
    assert state.state == "open"
    assert state.attributes.get("current_position") == 100
    
    # Test mid position
    coordinator.async_set_updated_data({
        "height_cm": 95.0,  # Midpoint between 60 and 130
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("cover.desky_desk")
    assert state.state == "open"
    assert state.attributes.get("current_position") == 50


@pytest.mark.asyncio
async def test_cover_availability(hass: HomeAssistant, init_integration):
    """Test cover availability based on connection."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # Test disconnected
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": False,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("cover.desky_desk")
    assert state.state == STATE_UNAVAILABLE


@pytest.mark.asyncio
async def test_cover_open_service(hass: HomeAssistant, init_integration):
    """Test opening the cover (raising desk)."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    mock_device = MagicMock()
    mock_device.move_up = AsyncMock()
    coordinator._device = mock_device
    
    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_OPEN_COVER,
        {ATTR_ENTITY_ID: "cover.desky_desk"},
        blocking=True,
    )
    
    mock_device.move_up.assert_called_once()


@pytest.mark.asyncio
async def test_cover_close_service(hass: HomeAssistant, init_integration):
    """Test closing the cover (lowering desk)."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    mock_device = MagicMock()
    mock_device.move_down = AsyncMock()
    coordinator._device = mock_device
    
    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_CLOSE_COVER,
        {ATTR_ENTITY_ID: "cover.desky_desk"},
        blocking=True,
    )
    
    mock_device.move_down.assert_called_once()


@pytest.mark.asyncio
async def test_cover_stop_service(hass: HomeAssistant, init_integration):
    """Test stopping the cover."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    mock_device = MagicMock()
    mock_device.stop = AsyncMock()
    coordinator._device = mock_device
    
    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_STOP_COVER,
        {ATTR_ENTITY_ID: "cover.desky_desk"},
        blocking=True,
    )
    
    mock_device.stop.assert_called_once()


@pytest.mark.asyncio
async def test_cover_set_position_service(hass: HomeAssistant, init_integration):
    """Test setting cover position uses move_to_height."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    mock_device = MagicMock()
    mock_device.move_to_height = AsyncMock()
    coordinator._device = mock_device
    coordinator.async_request_refresh = AsyncMock()
    
    # Test moving to 75% position
    # 75% = MIN_HEIGHT + 0.75 * (MAX_HEIGHT - MIN_HEIGHT) = 60 + 0.75 * 70 = 112.5
    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_SET_COVER_POSITION,
        {
            ATTR_ENTITY_ID: "cover.desky_desk",
            ATTR_POSITION: 75,
        },
        blocking=True,
    )
    
    mock_device.move_to_height.assert_called_once_with(112.5)
    coordinator.async_request_refresh.assert_called_once()
    
    # Reset mocks
    mock_device.move_to_height.reset_mock()
    coordinator.async_request_refresh.reset_mock()
    
    # Test moving to 0% position (minimum height)
    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_SET_COVER_POSITION,
        {
            ATTR_ENTITY_ID: "cover.desky_desk",
            ATTR_POSITION: 0,
        },
        blocking=True,
    )
    
    mock_device.move_to_height.assert_called_once_with(MIN_HEIGHT)
    
    # Reset mocks
    mock_device.move_to_height.reset_mock()
    
    # Test moving to 100% position (maximum height)
    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_SET_COVER_POSITION,
        {
            ATTR_ENTITY_ID: "cover.desky_desk",
            ATTR_POSITION: 100,
        },
        blocking=True,
    )
    
    mock_device.move_to_height.assert_called_once_with(MAX_HEIGHT)


@pytest.mark.asyncio
async def test_cover_movement_state(hass: HomeAssistant, init_integration):
    """Test cover movement state."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    
    # Test moving up state
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": True,
        "movement_direction": "up",
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("cover.desky_desk")
    assert state.state == "opening"
    
    # Test moving down state
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": True,
        "movement_direction": "down",
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("cover.desky_desk")
    assert state.state == "closing"
    
    # Test stopped state
    coordinator.async_set_updated_data({
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "movement_direction": None,
        "is_connected": True,
    })
    await hass.async_block_till_done()
    
    state = hass.states.get("cover.desky_desk")
    assert state.state == "open"  # Position is 28% which is > 0