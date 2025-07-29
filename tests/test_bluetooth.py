"""Test the Desky Desk Bluetooth communication."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch
import pytest

from custom_components.desky_desk.bluetooth import DeskBLEDevice
from custom_components.desky_desk.const import (
    COMMAND_GET_STATUS,
    COMMAND_MEMORY_1,
    COMMAND_MEMORY_2,
    COMMAND_MEMORY_3,
    COMMAND_MEMORY_4,
    COMMAND_MOVE_DOWN,
    COMMAND_MOVE_UP,
    COMMAND_STOP,
    HEIGHT_NOTIFICATION_HEADER,
    NOTIFY_CHARACTERISTIC_UUID,
    WRITE_CHARACTERISTIC_UUID,
)


def test_desk_device_init(mock_ble_device):
    """Test DeskBLEDevice initialization."""
    device = DeskBLEDevice(mock_ble_device)
    
    assert device.address == "AA:BB:CC:DD:EE:FF"
    assert device.name == "Desky"
    assert device.height_cm == 0.0
    assert device.collision_detected is False
    assert device.is_moving is False
    assert device.is_connected is False


def test_desk_device_properties(mock_ble_device):
    """Test DeskBLEDevice properties."""
    device = DeskBLEDevice(mock_ble_device)
    device._height_cm = 85.0
    device._collision_detected = True
    device._is_moving = True
    
    assert device.height_cm == 85.0
    assert device.collision_detected is True
    assert device.is_moving is True


def test_register_callbacks(mock_ble_device):
    """Test callback registration."""
    device = DeskBLEDevice(mock_ble_device)
    
    notification_callback = MagicMock()
    disconnect_callback = MagicMock()
    
    device.register_notification_callback(notification_callback)
    device.register_disconnect_callback(disconnect_callback)
    
    assert notification_callback in device._notification_callbacks
    assert disconnect_callback in device._disconnect_callbacks


@pytest.mark.asyncio
async def test_connect_success(mock_ble_device, mock_establish_connection, mock_bleak_client):
    """Test successful connection."""
    device = DeskBLEDevice(mock_ble_device)
    
    result = await device.connect()
    
    assert result is True
    assert device._client == mock_bleak_client
    assert device.is_connected is True
    
    mock_establish_connection.assert_called_once()
    mock_bleak_client.start_notify.assert_called_once_with(
        NOTIFY_CHARACTERISTIC_UUID, device._handle_notification
    )


@pytest.mark.asyncio
async def test_connect_already_connected(mock_ble_device, mock_bleak_client):
    """Test connect when already connected."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    result = await device.connect()
    
    assert result is True


@pytest.mark.asyncio
async def test_connect_failure(mock_ble_device):
    """Test connection failure."""
    device = DeskBLEDevice(mock_ble_device)
    
    with patch(
        "custom_components.desky_desk.bluetooth.establish_connection",
        side_effect=Exception("Connection failed"),
    ):
        result = await device.connect()
        
        assert result is False
        assert device._client is None
        assert device.is_connected is False


@pytest.mark.asyncio
async def test_disconnect(mock_ble_device, mock_bleak_client):
    """Test disconnection."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    await device.disconnect()
    
    mock_bleak_client.stop_notify.assert_called_once_with(NOTIFY_CHARACTERISTIC_UUID)
    mock_bleak_client.disconnect.assert_called_once()
    assert device._client is None


@pytest.mark.asyncio
async def test_send_command_success(mock_ble_device, mock_bleak_client):
    """Test successful command sending."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    result = await device._send_command(COMMAND_GET_STATUS)
    
    assert result is True
    mock_bleak_client.write_gatt_char.assert_called_once_with(
        WRITE_CHARACTERISTIC_UUID, COMMAND_GET_STATUS
    )


@pytest.mark.asyncio
async def test_send_command_not_connected(mock_ble_device):
    """Test command sending when not connected."""
    device = DeskBLEDevice(mock_ble_device)
    
    result = await device._send_command(COMMAND_GET_STATUS)
    
    assert result is False


@pytest.mark.asyncio
async def test_send_command_failure(mock_ble_device, mock_bleak_client):
    """Test command sending failure."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    mock_bleak_client.write_gatt_char.side_effect = Exception("Write failed")
    
    result = await device._send_command(COMMAND_GET_STATUS)
    
    assert result is False


@pytest.mark.asyncio
async def test_movement_commands(mock_ble_device, mock_bleak_client):
    """Test movement commands."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Test move up
    await device.move_up()
    assert device._is_moving is True
    mock_bleak_client.write_gatt_char.assert_called_with(
        WRITE_CHARACTERISTIC_UUID, COMMAND_MOVE_UP
    )
    
    # Test move down
    await device.move_down()
    assert device._is_moving is True
    mock_bleak_client.write_gatt_char.assert_called_with(
        WRITE_CHARACTERISTIC_UUID, COMMAND_MOVE_DOWN
    )
    
    # Test stop
    await device.stop()
    assert device._is_moving is False
    mock_bleak_client.write_gatt_char.assert_called_with(
        WRITE_CHARACTERISTIC_UUID, COMMAND_STOP
    )


@pytest.mark.asyncio
async def test_preset_commands(mock_ble_device, mock_bleak_client):
    """Test preset commands."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Test all presets
    presets_commands = [
        (1, COMMAND_MEMORY_1),
        (2, COMMAND_MEMORY_2),
        (3, COMMAND_MEMORY_3),
        (4, COMMAND_MEMORY_4),
    ]
    
    for preset, command in presets_commands:
        await device.move_to_preset(preset)
        assert device._is_moving is True
        mock_bleak_client.write_gatt_char.assert_called_with(
            WRITE_CHARACTERISTIC_UUID, command
        )


@pytest.mark.asyncio
async def test_invalid_preset(mock_ble_device, mock_bleak_client):
    """Test invalid preset number."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    result = await device.move_to_preset(5)
    
    assert result is False
    mock_bleak_client.write_gatt_char.assert_not_called()


def test_handle_notification(mock_ble_device):
    """Test notification handling."""
    device = DeskBLEDevice(mock_ble_device)
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Create notification data with height 85.0 cm (850 in raw)
    # Height is at bytes 4-5, little-endian
    data = bytearray([0x98, 0x98, 0x00, 0x00, 0x52, 0x03])  # 850 = 0x0352
    
    device._handle_notification(0, data)
    
    assert device.height_cm == 85.0
    callback.assert_called_once_with(85.0, False, False)


def test_handle_notification_invalid_data(mock_ble_device):
    """Test notification handling with invalid data."""
    device = DeskBLEDevice(mock_ble_device)
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Too short data
    device._handle_notification(0, bytearray([0x98, 0x98]))
    callback.assert_not_called()
    
    # Wrong header
    device._handle_notification(0, bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))
    callback.assert_not_called()


def test_handle_disconnect(mock_ble_device, mock_bleak_client):
    """Test disconnect handling."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._is_moving = True
    
    callback = MagicMock()
    device.register_disconnect_callback(callback)
    
    device._handle_disconnect(mock_bleak_client)
    
    assert device._client is None
    assert device._is_moving is False
    callback.assert_called_once()