"""Test the Desky Desk update coordinator."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.desky_desk.coordinator import DeskUpdateCoordinator
from custom_components.desky_desk.const import RECONNECT_INTERVAL_SECONDS, UPDATE_INTERVAL_SECONDS

async def test_coordinator_init(hass: HomeAssistant, mock_config_entry, enable_custom_integrations):
    """Test coordinator initialization."""
    coordinator = DeskUpdateCoordinator(hass, mock_config_entry)
    
    assert coordinator.entry == mock_config_entry
    assert coordinator._device is None
    assert coordinator.update_interval.total_seconds() == UPDATE_INTERVAL_SECONDS
    assert coordinator._shutdown is False

async def test_coordinator_first_refresh_success(
    hass: HomeAssistant,
    mock_config_entry,
    mock_bluetooth_device_from_address,
    mock_establish_connection,
    enable_custom_integrations,
):
    """Test successful first refresh."""
    coordinator = DeskUpdateCoordinator(hass, mock_config_entry)
    
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
        
        # Patch asyncio.create_task to prevent the reconnect task from running
        with patch("asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task
            
            await coordinator.async_config_entry_first_refresh()
        
            assert coordinator._device == mock_device_instance
            # Initial data should show disconnected state (set by async_config_entry_first_refresh)
            assert coordinator.data == {
                "height_cm": 0,
                "collision_detected": False,
                "is_moving": False,
                "movement_direction": None,
                "is_connected": False,
            }

async def test_coordinator_first_refresh_no_device(
    hass: HomeAssistant,
    mock_config_entry,
    enable_custom_integrations,
):
    """Test first refresh when device is not found."""
    coordinator = DeskUpdateCoordinator(hass, mock_config_entry)
    
    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        with pytest.raises(ConfigEntryNotReady):
            await coordinator.async_config_entry_first_refresh()

async def test_coordinator_first_refresh_connection_failed(
    hass: HomeAssistant,
    mock_config_entry,
    mock_bluetooth_device_from_address,
    enable_custom_integrations,
):
    """Test first refresh when connection fails - starts reconnect task."""
    coordinator = DeskUpdateCoordinator(hass, mock_config_entry)
    
    with patch(
        "custom_components.desky_desk.coordinator.DeskBLEDevice"
    ) as mock_desk_device:
        mock_device_instance = mock_desk_device.return_value
        mock_device_instance.connect = AsyncMock(return_value=False)
        mock_device_instance.register_notification_callback = MagicMock()
        mock_device_instance.register_disconnect_callback = MagicMock()
        
        # Patch asyncio.create_task to prevent the reconnect task from running
        with patch("asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task
            
            # Should not raise - starts reconnect in background
            await coordinator.async_config_entry_first_refresh()
            
            # Verify device was created and callbacks registered
            assert coordinator._device == mock_device_instance
            mock_device_instance.register_notification_callback.assert_called_once()
            mock_device_instance.register_disconnect_callback.assert_called_once()
            
            # Verify reconnect task was created
            mock_create_task.assert_called_once()
            
            # Initial data should show disconnected state
            assert coordinator.data == {
                "height_cm": 0,
                "collision_detected": False,
                "is_moving": False,
                "movement_direction": None,
                "is_connected": False,
            }

async def test_coordinator_update_data_connected(
    hass: HomeAssistant,
    mock_config_entry,
    enable_custom_integrations,
):
    """Test data update when connected."""
    coordinator = DeskUpdateCoordinator(hass, mock_config_entry)
    
    mock_device = MagicMock()
    mock_device.is_connected = True
    mock_device.height_cm = 90.0
    mock_device.collision_detected = True
    mock_device.is_moving = True
    mock_device.movement_direction = "up"
    mock_device.get_status = AsyncMock()
    coordinator._device = mock_device
    
    data = await coordinator._async_update_data()
    
    assert data == {
        "height_cm": 90.0,
        "collision_detected": True,
        "is_moving": True,
        "movement_direction": "up",
        "is_connected": True,
    }
    mock_device.get_status.assert_called_once()

async def test_coordinator_update_data_not_connected(
    hass: HomeAssistant,
    mock_config_entry,
    enable_custom_integrations,
):
    """Test data update when not connected."""
    coordinator = DeskUpdateCoordinator(hass, mock_config_entry)
    
    mock_device = MagicMock()
    mock_device.is_connected = False
    coordinator._device = mock_device
    
    # Patch create_task to prevent reconnect task from running
    with patch("asyncio.create_task") as mock_create_task:
        mock_task = MagicMock()
        mock_create_task.return_value = mock_task
        
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        
        # Verify reconnect task was created
        mock_create_task.assert_called_once()

async def test_coordinator_notification_callback(
    hass: HomeAssistant,
    mock_config_entry,
    enable_custom_integrations,
):
    """Test notification callback updates data."""
    coordinator = DeskUpdateCoordinator(hass, mock_config_entry)
    
    # Set up a mock device to provide movement_direction
    mock_device = MagicMock()
    mock_device.movement_direction = "down"
    coordinator._device = mock_device
    
    with patch.object(coordinator, "async_set_updated_data") as mock_set_data:
        coordinator._handle_notification(85.5, True, False)
        
        mock_set_data.assert_called_once_with({
            "height_cm": 85.5,
            "collision_detected": True,
            "is_moving": False,
            "movement_direction": "down",
            "is_connected": True,
        })

async def test_coordinator_disconnect_callback(
    hass: HomeAssistant,
    mock_config_entry,
    enable_custom_integrations,
):
    """Test disconnect callback updates data."""
    coordinator = DeskUpdateCoordinator(hass, mock_config_entry)
    
    mock_device = MagicMock()
    mock_device.height_cm = 75.0
    coordinator._device = mock_device
    
    with patch.object(coordinator, "async_set_updated_data") as mock_set_data:
        coordinator._handle_disconnect()
        
        mock_set_data.assert_called_once_with({
            "height_cm": 75.0,
            "collision_detected": False,
            "is_moving": False,
            "movement_direction": None,
            "is_connected": False,
        })

async def test_coordinator_reconnect(
    hass: HomeAssistant,
    mock_config_entry,
    mock_bluetooth_device_from_address,
    enable_custom_integrations,
):
    """Test reconnection logic."""
    coordinator = DeskUpdateCoordinator(hass, mock_config_entry)
    
    mock_device = MagicMock()
    mock_device.is_connected = False
    mock_device.connect = AsyncMock(side_effect=[False, True])
    mock_device._ble_device = MagicMock()
    coordinator._device = mock_device
    
    # Patch the reconnect method to simulate one failed and one successful connection attempt
    connect_count = 0
    
    async def mock_connect():
        nonlocal connect_count
        connect_count += 1
        if connect_count == 1:
            return False
        else:
            # Set shutdown to exit the loop after success
            coordinator._shutdown = True
            return True
    
    mock_device.connect = mock_connect
    
    with patch.object(coordinator, "async_set_updated_data") as mock_set_data:
        with patch.object(coordinator, "_async_update_data", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = {"test": "data"}
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await coordinator._reconnect()
                
                assert connect_count == 2
                mock_set_data.assert_called_once_with({"test": "data"})
                mock_sleep.assert_called_once_with(RECONNECT_INTERVAL_SECONDS)

async def test_coordinator_shutdown(
    hass: HomeAssistant,
    mock_config_entry,
    enable_custom_integrations,
):
    """Test coordinator shutdown."""
    coordinator = DeskUpdateCoordinator(hass, mock_config_entry)
    
    mock_device = MagicMock()
    mock_device.disconnect = AsyncMock()
    coordinator._device = mock_device
    
    reconnect_task = asyncio.create_task(asyncio.sleep(10))
    coordinator._reconnect_task = reconnect_task
    
    await coordinator.async_shutdown()
    
    assert coordinator._shutdown is True
    assert reconnect_task.cancelled()
    mock_device.disconnect.assert_called_once()