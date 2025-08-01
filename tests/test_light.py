"""Test Desky Desk light platform."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    DOMAIN as LIGHT_DOMAIN,
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

from custom_components.desky_desk.const import DOMAIN, LIGHT_COLORS


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


async def test_light_entity_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test light entity is set up correctly."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    await setup_coordinator_data(hass, mock_config_entry)
    
    entity_registry = er.async_get(hass)
    
    # Check entity is registered
    entity = entity_registry.async_get("light.desky_desk_led_strip")
    assert entity is not None
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_led_strip"
    
    # Check state
    state = hass.states.get("light.desky_desk_led_strip")
    assert state is not None
    assert state.state == STATE_ON
    # Brightness might be 127 or 128 due to rounding (50% of 255)
    assert state.attributes.get(ATTR_BRIGHTNESS) in [127, 128]
    assert state.attributes.get("color_name") == "White"  # Check extra_state_attributes in light.py


async def test_light_turn_on_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test turning light on and off."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    
    mock_device = coordinator._device
    
    # Turn off first (light starts on)
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "light.desky_desk_led_strip"},
        blocking=True,
    )
    
    mock_device.set_lighting.assert_called_once_with(False)
    
    # Update coordinator data to reflect light is off
    coordinator.data["lighting_enabled"] = False
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    # Turn on
    mock_device.set_lighting.reset_mock()
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "light.desky_desk_led_strip"},
        blocking=True,
    )
    
    mock_device.set_lighting.assert_called_once_with(True)


async def test_light_brightness(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test setting light brightness."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    mock_device = coordinator._device
    
    # Mock the device methods
    mock_device.set_brightness = AsyncMock(return_value=True)
    mock_device.get_brightness = AsyncMock(return_value=True)
    
    # Set brightness to 75%
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.desky_desk_led_strip",
            ATTR_BRIGHTNESS: 191,  # 75% of 255
        },
        blocking=True,
    )
    
    # Check that set_brightness was called
    assert mock_device.set_brightness.called
    # Get the actual call arguments
    args, kwargs = mock_device.set_brightness.call_args
    # 191/255 * 100 = 74.9, which rounds to 74
    assert args[0] == 74


@pytest.mark.skip(reason="Custom service not implemented yet")
async def test_light_color_selection(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test setting light colors using custom service."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    mock_device = coordinator._device
    
    # Mock the device methods
    mock_device.set_light_color = AsyncMock(return_value=True)
    mock_device.get_light_color = AsyncMock(return_value=True)
    
    # Test setting red color using custom service
    await hass.services.async_call(
        DOMAIN,
        "set_light_color",
        {
            ATTR_ENTITY_ID: "light.desky_desk_led_strip",
            "color": "red",
        },
        blocking=True,
    )
    
    mock_device.set_light_color.assert_called_once_with(2)  # Red is color ID 2
    
    # Test setting green color
    mock_device.set_light_color.reset_mock()
    
    await hass.services.async_call(
        DOMAIN,
        "set_light_color",
        {
            ATTR_ENTITY_ID: "light.desky_desk_led_strip",
            "color": "green",
        },
        blocking=True,
    )
    
    mock_device.set_light_color.assert_called_once_with(3)  # Green is color ID 3


async def test_light_party_mode_effect(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test setting party mode effect."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    mock_device = coordinator._device
    
    # Mock the device methods
    mock_device.set_light_color = AsyncMock(return_value=True)
    mock_device.get_light_color = AsyncMock(return_value=True)
    
    # Set party mode effect
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: "light.desky_desk_led_strip",
            ATTR_EFFECT: "Party mode",
        },
        blocking=True,
    )
    
    mock_device.set_light_color.assert_called_once_with(6)  # Party mode is color ID 6


async def test_light_color_effects(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test setting different color effects."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    mock_device = coordinator._device
    
    # Mock the device methods
    mock_device.set_light_color = AsyncMock(return_value=True)
    mock_device.get_light_color = AsyncMock(return_value=True)
    
    # Test color effects
    color_tests = [
        ("White", 1),
        ("Red", 2),
        ("Green", 3),
        ("Blue", 4),
        ("Yellow", 5),
        ("Party mode", 6),
    ]
    
    for effect_name, expected_color_id in color_tests:
        mock_device.set_light_color.reset_mock()
        
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {
                ATTR_ENTITY_ID: "light.desky_desk_led_strip",
                ATTR_EFFECT: effect_name,
            },
            blocking=True,
        )
        
        mock_device.set_light_color.assert_called_once_with(expected_color_id)
        
        # Test that the effect is reported correctly
        coordinator.data["light_color"] = expected_color_id
        coordinator.async_set_updated_data(coordinator.data)
        await hass.async_block_till_done()
        
        state = hass.states.get("light.desky_desk_led_strip")
        assert state.attributes.get(ATTR_EFFECT) == effect_name


async def test_light_turn_off_via_color(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test turning light off by setting color to Off."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    mock_device = coordinator._device
    
    # Mock the device methods
    mock_device.set_light_color = AsyncMock(return_value=True)
    
    # Verify light is on initially
    state = hass.states.get("light.desky_desk_led_strip")
    assert state.state == STATE_ON
    
    # Simulate receiving notification that color changed to Off
    coordinator.data["light_color"] = 7  # Off
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    # Check light is now off
    state = hass.states.get("light.desky_desk_led_strip")
    assert state.state == STATE_OFF


async def test_light_unavailable_when_disconnected(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test light becomes unavailable when disconnected."""
    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]
    
    # Simulate disconnection
    coordinator.data["is_connected"] = False
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    state = hass.states.get("light.desky_desk_led_strip")
    assert state.state == STATE_UNAVAILABLE


@pytest.mark.skip(reason="Custom service not implemented yet")
async def test_light_custom_service(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test custom set_light_color service."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    mock_device = coordinator._device
    
    # Mock the device method
    mock_device.set_light_color = AsyncMock(return_value=True)
    mock_device.get_light_color = AsyncMock(return_value=True)
    
    # Call custom service
    await hass.services.async_call(
        DOMAIN,
        "set_light_color",
        {
            ATTR_ENTITY_ID: "light.desky_desk_led_strip",
            "color": "Blue",
        },
        blocking=True,
    )
    
    mock_device.set_light_color.assert_called_once_with(4)  # Blue is color ID 4


async def test_light_color_mapping(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test all color mappings work correctly."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    
    color_names = {
        1: "White",
        2: "Red",
        3: "Green",
        4: "Blue",
        5: "Yellow",
        6: "Party mode",
        7: "Off",
    }
    
    for color_id, expected_name in color_names.items():
        # Update coordinator data
        coordinator.data["light_color"] = color_id
        coordinator.async_set_updated_data(coordinator.data)
        await hass.async_block_till_done()
        
        # Check state
        state = hass.states.get("light.desky_desk_led_strip")
        if color_id == 7:  # Off
            assert state.state == STATE_OFF
        else:
            assert state.state == STATE_ON
            assert state.attributes.get("color_name") == expected_name