"""Test Desky Desk integration setup and unloading."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.desky_desk import async_setup_entry, async_unload_entry
from custom_components.desky_desk.const import DOMAIN

async def test_setup_entry_success(
    hass: HomeAssistant,
    mock_config_entry,
    mock_bluetooth_device_from_address,
    mock_establish_connection,
    mock_bleak_client,
    enable_custom_integrations,
):
    """Test successful setup of config entry."""
    mock_config_entry.add_to_hass(hass)
    
    with patch(
        "custom_components.desky_desk.coordinator.DeskBLEDevice"
    ) as mock_desk_device:
        mock_device_instance = mock_desk_device.return_value
        mock_device_instance.connect = AsyncMock(return_value=True)
        mock_device_instance.is_connected = True
        mock_device_instance.height_cm = 80.0
        mock_device_instance.collision_detected = False
        mock_device_instance.is_moving = False
        mock_device_instance.get_status = AsyncMock()
        mock_device_instance.register_notification_callback = MagicMock()
        mock_device_instance.register_disconnect_callback = MagicMock()
        
        with patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"
        ) as mock_forward:
            result = await async_setup_entry(hass, mock_config_entry)
            
        assert result is True
        await hass.async_block_till_done()
        
        # Verify the coordinator was set up
        assert DOMAIN in hass.data
        assert mock_config_entry.entry_id in hass.data[DOMAIN]
        
        # Verify platforms were forwarded
        mock_forward.assert_called_once()
        platforms = mock_forward.call_args[0][1]
        assert len(platforms) == 8

async def test_setup_entry_no_device(
    hass: HomeAssistant,
    mock_config_entry,
    enable_custom_integrations,
):
    """Test setup failure when device is not found."""
    mock_config_entry.add_to_hass(hass)
    
    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, mock_config_entry)


async def test_unload_entry(
    hass: HomeAssistant,
    mock_config_entry,
    enable_custom_integrations,
):
    """Test unloading the config entry."""
    # First setup the entry
    mock_config_entry.add_to_hass(hass)
    
    # Create a mock coordinator
    mock_coordinator = MagicMock()
    mock_coordinator.async_shutdown = AsyncMock()
    
    # Add data to hass
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][mock_config_entry.entry_id] = mock_coordinator
    
    # Set the entry state to loaded
    mock_config_entry._state = ConfigEntryState.LOADED
    
    # Now test unloading
    assert await async_unload_entry(hass, mock_config_entry)
    mock_coordinator.async_shutdown.assert_called_once()
    
    assert mock_config_entry.entry_id not in hass.data[DOMAIN]

async def test_setup_platforms(
    hass: HomeAssistant,
    mock_config_entry,
    mock_bluetooth_device_from_address,
    mock_establish_connection,
    enable_custom_integrations,
):
    """Test that all platforms are set up."""
    mock_config_entry.add_to_hass(hass)
    
    with patch(
        "custom_components.desky_desk.coordinator.DeskBLEDevice"
    ) as mock_desk_device:
        mock_device_instance = mock_desk_device.return_value
        mock_device_instance.connect = AsyncMock(return_value=True)
        mock_device_instance.is_connected = True
        mock_device_instance.height_cm = 80.0
        mock_device_instance.collision_detected = False
        mock_device_instance.is_moving = False
        mock_device_instance.get_status = AsyncMock()
        mock_device_instance.register_notification_callback = MagicMock()
        mock_device_instance.register_disconnect_callback = MagicMock()
        
        with patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"
        ) as mock_forward:
            await async_setup_entry(hass, mock_config_entry)
            await hass.async_block_till_done()
            
            mock_forward.assert_called_once()
            platforms = mock_forward.call_args[0][1]
            assert len(platforms) == 8
            assert "cover" in [p.value for p in platforms]
            assert "number" in [p.value for p in platforms]
            assert "button" in [p.value for p in platforms]
            assert "binary_sensor" in [p.value for p in platforms]
            assert "light" in [p.value for p in platforms]
            assert "switch" in [p.value for p in platforms]
            assert "select" in [p.value for p in platforms]
            assert "sensor" in [p.value for p in platforms]