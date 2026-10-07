"""Test the Desky Desk binary sensor platform."""

from __future__ import annotations

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import DATA_INSTANCES

from custom_components.desky_desk.const import DOMAIN
from custom_components.desky_desk.entity import DeskEntity


async def test_binary_sensor_setup(hass: HomeAssistant, init_integration):
    """Test binary sensor entity setup."""
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

    state = hass.states.get("binary_sensor.desky_desk_collision_detected")

    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes.get("device_class") == "problem"


async def test_binary_sensor_collision_detection(hass: HomeAssistant, init_integration):
    """Test collision detection states."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]

    # Test no collision
    coordinator.async_set_updated_data(
        {
            "height_cm": 80.0,
            "collision_detected": False,
            "is_moving": False,
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.desky_desk_collision_detected")
    assert state.state == STATE_OFF

    # Test collision detected
    coordinator.async_set_updated_data(
        {
            "height_cm": 80.0,
            "collision_detected": True,
            "is_moving": False,
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.desky_desk_collision_detected")
    assert state.state == STATE_ON


async def test_binary_sensor_availability(hass: HomeAssistant, init_integration):
    """Test binary sensor availability based on connection."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]

    # Test connected
    coordinator.async_set_updated_data(
        {
            "height_cm": 80.0,
            "collision_detected": False,
            "is_moving": False,
            "is_connected": True,
        }
    )
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.desky_desk_collision_detected")
    assert state.state == STATE_OFF

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


async def test_binary_sensor_is_on_without_data(hass: HomeAssistant, init_integration):
    """Test the collision sensor reports no state when it has no data."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    sensor = hass.data[DATA_INSTANCES][BINARY_SENSOR_DOMAIN].get_entity(
        "binary_sensor.desky_desk_collision_detected"
    )

    coordinator.async_set_updated_data(
        {"collision_detected": True, "is_connected": True}
    )
    await hass.async_block_till_done()
    assert sensor.is_on is True

    coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()
    assert sensor.is_on is None
    assert sensor.available is False


async def test_base_entity_attributes(hass: HomeAssistant, init_integration):
    """Test the shared desk entity reports its connection state."""
    coordinator = hass.data[DOMAIN][init_integration.entry_id]
    entity = DeskEntity(coordinator, init_integration)

    coordinator.async_set_updated_data({"is_connected": True})
    await hass.async_block_till_done()
    assert entity.available is True
    assert entity.extra_state_attributes == {"connected": True}
    assert entity._device is coordinator.device

    coordinator.async_set_updated_data({"is_connected": False})
    await hass.async_block_till_done()
    assert entity.available is False
    assert entity.extra_state_attributes == {"connected": False}

    coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()
    assert entity.available is False
    assert entity.extra_state_attributes == {"connected": False}
