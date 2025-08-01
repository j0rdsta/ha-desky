"""Test Desky Desk select platform."""
from __future__ import annotations

from unittest.mock import AsyncMock
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_OPTION,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.desky_desk.const import (
    DOMAIN,
    SENSITIVITY_LEVELS,
    TOUCH_MODES,
)


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


async def test_select_entities_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test select entities are set up correctly."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    await setup_coordinator_data(hass, mock_config_entry)
    
    entity_registry = er.async_get(hass)
    
    # Check sensitivity select
    entity = entity_registry.async_get("select.desky_desk_collision_sensitivity")
    assert entity
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_sensitivity"
    
    # Check touch mode select
    entity = entity_registry.async_get("select.desky_desk_touch_mode")
    assert entity
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_touch_mode"
    
    # Check units select
    entity = entity_registry.async_get("select.desky_desk_display_unit")
    assert entity
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_unit"
    
    # Check states
    sensitivity_state = hass.states.get("select.desky_desk_collision_sensitivity")
    assert sensitivity_state
    assert sensitivity_state.state == "Medium"
    assert sensitivity_state.attributes.get("options") == ["High", "Medium", "Low"]
    
    touch_mode_state = hass.states.get("select.desky_desk_touch_mode")
    assert touch_mode_state
    assert touch_mode_state.state == "One press"
    assert touch_mode_state.attributes.get("options") == ["One press", "Press and hold"]
    
    units_state = hass.states.get("select.desky_desk_display_unit")
    assert units_state
    assert units_state.state == "cm"
    assert units_state.attributes.get("options") == ["cm", "in"]


async def test_sensitivity_select_change(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test changing collision sensitivity."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    mock_device = coordinator._device
    
    # Mock the device method
    mock_device.set_sensitivity = AsyncMock(return_value=True)
    mock_device.get_sensitivity = AsyncMock(return_value=True)
    
    # Change to High sensitivity
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: "select.desky_desk_collision_sensitivity",
            ATTR_OPTION: "High",
        },
        blocking=True,
    )
    
    mock_device.set_sensitivity.assert_called_once_with(1)  # High = 1
    
    # Change to Low sensitivity
    mock_device.set_sensitivity.reset_mock()
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: "select.desky_desk_collision_sensitivity",
            ATTR_OPTION: "Low",
        },
        blocking=True,
    )
    
    mock_device.set_sensitivity.assert_called_once_with(3)  # Low = 3


async def test_touch_mode_select_change(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test changing touch mode."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    mock_device = coordinator._device
    
    # Mock the device method
    mock_device.set_touch_mode = AsyncMock(return_value=True)
    
    # Change to Press and hold
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: "select.desky_desk_touch_mode",
            ATTR_OPTION: "Press and hold",
        },
        blocking=True,
    )
    
    mock_device.set_touch_mode.assert_called_once_with(1)  # Press and hold = 1
    
    # Change back to One press
    mock_device.set_touch_mode.reset_mock()
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: "select.desky_desk_touch_mode",
            ATTR_OPTION: "One press",
        },
        blocking=True,
    )
    
    mock_device.set_touch_mode.assert_called_once_with(0)  # One press = 0


async def test_units_select_change(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test changing height units."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    mock_device = coordinator._device
    
    # Mock the device method
    mock_device.set_unit = AsyncMock(return_value=True)
    
    # Change to inches
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: "select.desky_desk_display_unit",
            ATTR_OPTION: "in",
        },
        blocking=True,
    )
    
    mock_device.set_unit.assert_called_once_with("in")
    
    # Change back to cm
    mock_device.set_unit.reset_mock()
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: "select.desky_desk_display_unit",
            ATTR_OPTION: "cm",
        },
        blocking=True,
    )
    
    mock_device.set_unit.assert_called_once_with("cm")


async def test_select_state_updates(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test select states update when coordinator data changes."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    
    # Initial states
    assert hass.states.get("select.desky_desk_collision_sensitivity").state == "Medium"
    assert hass.states.get("select.desky_desk_touch_mode").state == "One press"
    assert hass.states.get("select.desky_desk_display_unit").state == "cm"
    
    # Update sensitivity to High
    coordinator.data["sensitivity_level"] = 1
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    assert hass.states.get("select.desky_desk_collision_sensitivity").state == "High"
    
    # Update touch mode to Press and hold
    coordinator.data["touch_mode"] = 1
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    assert hass.states.get("select.desky_desk_touch_mode").state == "Press and hold"
    
    # Update units to in
    coordinator.data["unit_preference"] = "in"
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    assert hass.states.get("select.desky_desk_display_unit").state == "in"


async def test_selects_unavailable_when_disconnected(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test selects become unavailable when disconnected."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    
    # Simulate disconnection
    coordinator.data["is_connected"] = False
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    
    assert hass.states.get("select.desky_desk_collision_sensitivity").state == STATE_UNAVAILABLE
    assert hass.states.get("select.desky_desk_touch_mode").state == STATE_UNAVAILABLE
    assert hass.states.get("select.desky_desk_display_unit").state == STATE_UNAVAILABLE


@pytest.mark.skip(reason="Custom service not implemented yet")
async def test_custom_sensitivity_service(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    init_integration,
):
    """Test custom set_sensitivity service."""
    await hass.async_block_till_done()
    
    # Set up coordinator data
    coordinator = await setup_coordinator_data(hass, mock_config_entry)
    mock_device = coordinator._device
    
    # Mock the device method
    mock_device.set_sensitivity = AsyncMock(return_value=True)
    mock_device.get_sensitivity = AsyncMock(return_value=True)
    
    # Call custom service
    await hass.services.async_call(
        DOMAIN,
        "set_sensitivity",
        {
            ATTR_ENTITY_ID: "cover.desky_desk",
            "level": "Low",
        },
        blocking=True,
    )
    
    mock_device.set_sensitivity.assert_called_once_with(3)  # Low = 3