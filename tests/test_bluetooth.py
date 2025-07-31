"""Test the Desky Desk Bluetooth communication."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch
import pytest

from custom_components.desky_desk.bluetooth import DeskBLEDevice
from custom_components.desky_desk.const import (
    COMMAND_GET_STATUS,
    COMMAND_HANDSHAKE,
    COMMAND_MEMORY_1,
    COMMAND_MEMORY_2,
    COMMAND_MEMORY_3,
    COMMAND_MEMORY_4,
    COMMAND_MOVE_DOWN,
    COMMAND_MOVE_UP,
    COMMAND_STOP,
    HEIGHT_NOTIFICATION_HEADER,
    MAX_HEIGHT,
    MIN_HEIGHT,
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
    
    # Verify establish_connection was called with correct parameters
    mock_establish_connection.assert_called_once()
    call_args = mock_establish_connection.call_args
    assert call_args.kwargs['timeout'] == 20.0  # Direct connection timeout
    assert call_args.kwargs['max_attempts'] == 3  # Direct connection attempts
    assert call_args.kwargs['use_services_cache'] is True
    assert 'ble_device_callback' in call_args.kwargs
    
    mock_bleak_client.start_notify.assert_called_once_with(
        NOTIFY_CHARACTERISTIC_UUID, device._handle_notification
    )
    mock_bleak_client.get_services.assert_called_once()
    
    # Verify handshake command was sent
    expected_calls = [
        call(WRITE_CHARACTERISTIC_UUID, COMMAND_HANDSHAKE),
        call(WRITE_CHARACTERISTIC_UUID, COMMAND_GET_STATUS),
    ]
    mock_bleak_client.write_gatt_char.assert_has_calls(expected_calls)


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


@pytest.mark.asyncio
async def test_connect_timeout(mock_ble_device):
    """Test connection timeout."""
    device = DeskBLEDevice(mock_ble_device)
    
    with patch(
        "custom_components.desky_desk.bluetooth.establish_connection",
        side_effect=asyncio.TimeoutError(),
    ):
        result = await device.connect()
        
        assert result is False
        assert device._client is None


@pytest.mark.asyncio 
async def test_proxy_detection(mock_ble_device):
    """Test ESPHome proxy detection."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Test no details
    mock_ble_device.details = None
    assert device._is_esphome_proxy(mock_ble_device) is False
    
    # Test via_device indicator
    mock_ble_device.details = {"via_device": "ESP32"}
    assert device._is_esphome_proxy(mock_ble_device) is True
    
    # Test source field
    mock_ble_device.details = {"source": "esphome"}
    assert device._is_esphome_proxy(mock_ble_device) is True
    
    # Test scanner field
    mock_ble_device.details = {"scanner": "esp32_proxy"}
    assert device._is_esphome_proxy(mock_ble_device) is True
    
    # Test path field
    mock_ble_device.details = {"path": "/esphome/proxy1"}
    assert device._is_esphome_proxy(mock_ble_device) is True
    
    # Test no proxy indicators
    mock_ble_device.details = {"source": "hci0"}
    assert device._is_esphome_proxy(mock_ble_device) is False


@pytest.mark.asyncio
async def test_connect_with_proxy(mock_ble_device, mock_establish_connection, mock_bleak_client):
    """Test connection with ESPHome proxy detection."""
    # Set proxy indicators
    mock_ble_device.details = {"via_device": "ESP32"}
    
    device = DeskBLEDevice(mock_ble_device)
    
    result = await device.connect()
    
    assert result is True
    
    # Verify proxy-specific parameters were used
    call_args = mock_establish_connection.call_args
    assert call_args.kwargs['timeout'] == 30.0  # Proxy timeout
    assert call_args.kwargs['max_attempts'] == 5  # Proxy attempts


@pytest.mark.asyncio
async def test_get_updated_device(mock_ble_device):
    """Test _get_updated_device callback returns the BLE device."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Test the callback returns the device
    result = device._get_updated_device()
    assert result == mock_ble_device


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


@pytest.mark.asyncio
async def test_move_to_height_success(mock_ble_device, mock_bleak_client):
    """Test move_to_height command."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Test moving to 85.0 cm (850 mm)
    result = await device.move_to_height(85.0)
    
    assert result is True
    assert device._is_moving is True
    
    # Calculate expected command
    # 850 mm = 0x0352, so high=0x03, low=0x52
    # checksum = (0x1B + 0x02 + 0x03 + 0x52) & 0xFF = 0x72
    expected_command = bytes([0xF1, 0xF1, 0x1B, 0x02, 0x03, 0x52, 0x72, 0x7E])
    
    mock_bleak_client.write_gatt_char.assert_called_once_with(
        WRITE_CHARACTERISTIC_UUID, expected_command
    )


@pytest.mark.asyncio
async def test_move_to_height_out_of_range(mock_ble_device, mock_bleak_client):
    """Test move_to_height with out of range values."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Test below minimum
    result = await device.move_to_height(MIN_HEIGHT - 10)
    assert result is False
    assert not device._is_moving
    
    # Test above maximum
    result = await device.move_to_height(MAX_HEIGHT + 10)
    assert result is False
    assert not device._is_moving
    
    # Verify no commands were sent
    mock_bleak_client.write_gatt_char.assert_not_called()


@pytest.mark.asyncio
async def test_move_to_height_edge_cases(mock_ble_device, mock_bleak_client):
    """Test move_to_height with edge case values."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Test minimum height (60.0 cm = 600 mm = 0x0258)
    await device.move_to_height(MIN_HEIGHT)
    # checksum = (0x1B + 0x02 + 0x02 + 0x58) & 0xFF = 0x77
    expected_min = bytes([0xF1, 0xF1, 0x1B, 0x02, 0x02, 0x58, 0x77, 0x7E])
    
    # Test maximum height (130.0 cm = 1300 mm = 0x0514)
    await device.move_to_height(MAX_HEIGHT)
    # checksum = (0x1B + 0x02 + 0x05 + 0x14) & 0xFF = 0x36
    expected_max = bytes([0xF1, 0xF1, 0x1B, 0x02, 0x05, 0x14, 0x36, 0x7E])
    
    expected_calls = [
        call(WRITE_CHARACTERISTIC_UUID, expected_min),
        call(WRITE_CHARACTERISTIC_UUID, expected_max),
    ]
    mock_bleak_client.write_gatt_char.assert_has_calls(expected_calls)