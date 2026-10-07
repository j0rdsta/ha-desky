"""Test the Desky Desk cover platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

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
from homeassistant.helpers.entity_component import DATA_INSTANCES

from custom_components.desky_desk.const import DOMAIN, MAX_HEIGHT, MIN_HEIGHT


async def test_cover_setup(hass: HomeAssistant, init_integration):
    """Test cover entity setup."""
    # First, trigger an update to set entities as available
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    coordinator.async_set_updated_data(
        {
            "height_cm": 80.0,
            "collision_detected": False,
            "is_moving": False,
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    state = hass.states.get("cover.desky_desk")

    assert state is not None
    assert state.state == "open"  # Default position
    assert state.attributes.get("current_position") == 28  # (80-60)/(130-60)*100


async def test_cover_position_calculations(hass: HomeAssistant, init_integration):
    """Test cover position calculations."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]

    # Test minimum height (closed)
    coordinator.async_set_updated_data(
        {
            "height_cm": MIN_HEIGHT,
            "collision_detected": False,
            "is_moving": False,
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    state = hass.states.get("cover.desky_desk")
    assert state.state == "closed"
    assert state.attributes.get("current_position") == 0

    # Test maximum height (open)
    coordinator.async_set_updated_data(
        {
            "height_cm": MAX_HEIGHT,
            "collision_detected": False,
            "is_moving": False,
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    state = hass.states.get("cover.desky_desk")
    assert state.state == "open"
    assert state.attributes.get("current_position") == 100

    # Test mid position
    coordinator.async_set_updated_data(
        {
            "height_cm": 95.0,  # Midpoint between 60 and 130
            "collision_detected": False,
            "is_moving": False,
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    state = hass.states.get("cover.desky_desk")
    assert state.state == "open"
    assert state.attributes.get("current_position") == 50


async def test_cover_availability(hass: HomeAssistant, init_integration):
    """Test cover availability based on connection."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]

    # Test disconnected
    coordinator.async_set_updated_data(
        {
            "height_cm": 80.0,
            "collision_detected": False,
            "is_moving": False,
            "is_connected": False,
        }
    )
    await hass.async_block_till_done()

    state = hass.states.get("cover.desky_desk")
    assert state.state == STATE_UNAVAILABLE


async def test_cover_open_service(hass: HomeAssistant, init_integration):
    """Test opening the cover (raising desk)."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]

    # First make sure the entity is available
    coordinator.async_set_updated_data(
        {
            "height_cm": 80.0,
            "collision_detected": False,
            "is_moving": False,
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    # Now replace the device with a fresh mock for testing
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


async def test_cover_close_service(hass: HomeAssistant, init_integration):
    """Test closing the cover (lowering desk)."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]

    # First make sure the entity is available
    coordinator.async_set_updated_data(
        {
            "height_cm": 80.0,
            "collision_detected": False,
            "is_moving": False,
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    # Now replace the device with a fresh mock for testing
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


async def test_cover_stop_service(hass: HomeAssistant, init_integration):
    """Test stopping the cover."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]

    # First make sure the entity is available
    coordinator.async_set_updated_data(
        {
            "height_cm": 80.0,
            "collision_detected": False,
            "is_moving": False,
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    # Now replace the device with a fresh mock for testing
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


async def test_cover_set_position_service(hass: HomeAssistant, init_integration):
    """Test setting cover position uses move_to_height."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]

    # First make sure the entity is available
    coordinator.async_set_updated_data(
        {
            "height_cm": 80.0,
            "collision_detected": False,
            "is_moving": False,
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    # Now replace the device with a fresh mock for testing
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


async def test_cover_movement_state(hass: HomeAssistant, init_integration):
    """Test cover movement state."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]

    # Test moving up state
    coordinator.async_set_updated_data(
        {
            "height_cm": 80.0,
            "collision_detected": False,
            "is_moving": True,
            "movement_direction": "up",
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    state = hass.states.get("cover.desky_desk")
    assert state.state == "opening"

    # Test moving down state
    coordinator.async_set_updated_data(
        {
            "height_cm": 80.0,
            "collision_detected": False,
            "is_moving": True,
            "movement_direction": "down",
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    state = hass.states.get("cover.desky_desk")
    assert state.state == "closing"

    # Test stopped state
    coordinator.async_set_updated_data(
        {
            "height_cm": 80.0,
            "collision_detected": False,
            "is_moving": False,
            "movement_direction": None,
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    state = hass.states.get("cover.desky_desk")
    assert state.state == "open"  # Position is 28% which is > 0


def _get_cover_entity(hass: HomeAssistant):
    """Return the desk entity object registered with the cover component."""
    return hass.data[DATA_INSTANCES][COVER_DOMAIN].get_entity("cover.desky_desk")


async def test_cover_properties_without_data(hass: HomeAssistant, init_integration):
    """Test the cover reports no position or movement when it has no data."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    cover = _get_cover_entity(hass)

    coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()

    assert hass.states.get("cover.desky_desk").state == STATE_UNAVAILABLE
    assert cover.available is False
    assert cover.current_cover_position is None
    assert cover.is_closed is None
    assert cover.is_opening is False
    assert cover.is_closing is False


async def test_cover_commands_skipped_without_device(
    hass: HomeAssistant, init_integration
):
    """Test cover services do nothing when the desk device is gone."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    coordinator.async_set_updated_data(
        {
            "height_cm": 80.0,
            "collision_detected": False,
            "is_moving": False,
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    old_device = MagicMock()
    old_device.move_up = AsyncMock()
    old_device.move_down = AsyncMock()
    old_device.stop = AsyncMock()
    old_device.move_to_height = AsyncMock()
    coordinator._device = old_device
    # The desk drops off and the coordinator loses its device
    coordinator._device = None
    coordinator.async_request_refresh = AsyncMock()

    for service, data in (
        (SERVICE_OPEN_COVER, {}),
        (SERVICE_CLOSE_COVER, {}),
        (SERVICE_STOP_COVER, {}),
        (SERVICE_SET_COVER_POSITION, {ATTR_POSITION: 50}),
    ):
        await hass.services.async_call(
            COVER_DOMAIN,
            service,
            {ATTR_ENTITY_ID: "cover.desky_desk", **data},
            blocking=True,
        )

    old_device.move_up.assert_not_called()
    old_device.move_down.assert_not_called()
    old_device.stop.assert_not_called()
    old_device.move_to_height.assert_not_called()
    coordinator.async_request_refresh.assert_not_called()
    state = hass.states.get("cover.desky_desk")
    assert state.state == "open"
    assert state.attributes.get("current_position") == 28
