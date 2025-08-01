"""Test Desky Desk sensor platform."""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import (
    PERCENTAGE,
    STATE_UNAVAILABLE,
    UnitOfLength,
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


async def test_sensor_entities_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test sensor entities are set up correctly."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    await setup_coordinator_data(hass, mock_config_entry)
    
    entity_registry = er.async_get(hass)
    
    # Check height display sensor
    entity = entity_registry.async_get("sensor.desky_desk_height_display")
    assert entity
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_height_display"
    
    # Check LED color sensor
    entity = entity_registry.async_get("sensor.desky_desk_led_color")
    assert entity
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_led_color"
    
    # Check vibration intensity sensor
    entity = entity_registry.async_get("sensor.desky_desk_vibration_intensity_display")
    assert entity
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_vibration_intensity_display"
    
    # Check states
    height_state = hass.states.get("sensor.desky_desk_height_display")
    assert height_state
    assert height_state.state == "80.0"
    assert height_state.attributes.get("unit_of_measurement") == UnitOfLength.CENTIMETERS
    
    led_color_state = hass.states.get("sensor.desky_desk_led_color")
    assert led_color_state
    assert led_color_state.state == "White"
    
    vibration_state = hass.states.get("sensor.desky_desk_vibration_intensity_display")
    assert vibration_state
    assert vibration_state.state == "75"
    assert vibration_state.attributes.get("unit_of_measurement") == PERCENTAGE


async def test_height_display_with_units(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test height display sensor shows correct units."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    
    # Check cm display
    state = hass.states.get("sensor.desky_desk_height_display")
    assert state.state == "80.0"
    assert state.attributes.get("unit_of_measurement") == UnitOfLength.CENTIMETERS
    
    # Change to inches
    coordinator.data["unit_preference"] = "inch"
    coordinator.data["height_cm"] = 100.0  # 100cm = 39.37 inches
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    state = hass.states.get("sensor.desky_desk_height_display")
    assert state.state == "39.4"  # Rounded to 1 decimal
    assert state.attributes.get("unit_of_measurement") == UnitOfLength.INCHES


async def test_led_color_display(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test LED color sensor shows correct color names."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    
    # Test all color mappings
    for color_id, color_name in LIGHT_COLORS.items():
        coordinator.data["light_color"] = color_id
        coordinator.async_set_updated_data(coordinator.data)
        await hass.async_block_till_done()
        
        state = hass.states.get("sensor.desky_desk_led_color")
        assert state.state == color_name


async def test_led_color_unknown(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test LED color sensor shows Unknown for invalid color."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    
    # Set invalid color
    coordinator.data["light_color"] = 99
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    state = hass.states.get("sensor.desky_desk_led_color")
    assert state.state == "Unknown"


async def test_vibration_intensity_display(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test vibration intensity sensor."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    
    # Test different intensity values
    for intensity in [0, 25, 50, 75, 100]:
        coordinator.data["vibration_intensity"] = intensity
        coordinator.async_set_updated_data(coordinator.data)
        await hass.async_block_till_done()
        
        state = hass.states.get("sensor.desky_desk_vibration_intensity_display")
        assert state.state == str(intensity)
        assert state.attributes.get("unit_of_measurement") == PERCENTAGE


async def test_sensors_unavailable_when_disconnected(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test sensors become unavailable when disconnected."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    
    # Simulate disconnection
    coordinator.data["is_connected"] = False
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    assert hass.states.get("sensor.desky_desk_height_display").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.desky_desk_led_color").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.desky_desk_vibration_intensity_display").state == STATE_UNAVAILABLE


async def test_height_sensor_precision(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test height sensor maintains proper precision."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    
    # Test various height values
    test_heights = [
        (65.0, "65.0"),
        (80.5, "80.5"),
        (100.25, "100.2"),  # Banker's rounding: .25 rounds to even digit
        (120.99, "121.0"),  # Should round to 1 decimal
    ]
    
    for height, expected in test_heights:
        coordinator.data["height_cm"] = height
        coordinator.async_set_updated_data(coordinator.data)
        await hass.async_block_till_done()
        
        state = hass.states.get("sensor.desky_desk_height_display")
        assert state.state == expected