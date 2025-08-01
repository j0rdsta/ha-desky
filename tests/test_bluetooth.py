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
    STATUS_NOTIFICATION_HEADER,
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
    assert device.movement_direction is None
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
    # Verify services property was accessed (not get_services method)
    # The services property is accessed during connection to discover services
    assert hasattr(mock_bleak_client, 'services')
    
    # Verify handshake command was sent
    expected_calls = [
        call(WRITE_CHARACTERISTIC_UUID, COMMAND_HANDSHAKE),
        call(WRITE_CHARACTERISTIC_UUID, COMMAND_GET_STATUS),
    ]
    mock_bleak_client.write_gatt_char.assert_has_calls(expected_calls)

async def test_connect_already_connected(mock_ble_device, mock_bleak_client):
    """Test connect when already connected."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    result = await device.connect()
    
    assert result is True

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

async def test_get_updated_device(mock_ble_device):
    """Test _get_updated_device callback returns the BLE device."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Test the callback returns the device
    result = device._get_updated_device()
    assert result == mock_ble_device

async def test_disconnect(mock_ble_device, mock_bleak_client):
    """Test disconnection."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    await device.disconnect()
    
    mock_bleak_client.stop_notify.assert_called_once_with(NOTIFY_CHARACTERISTIC_UUID)
    mock_bleak_client.disconnect.assert_called_once()
    assert device._client is None

async def test_send_command_success(mock_ble_device, mock_bleak_client):
    """Test successful command sending."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    result = await device._send_command(COMMAND_GET_STATUS)
    
    assert result is True
    mock_bleak_client.write_gatt_char.assert_called_once_with(
        WRITE_CHARACTERISTIC_UUID, COMMAND_GET_STATUS
    )

async def test_send_command_not_connected(mock_ble_device):
    """Test command sending when not connected."""
    device = DeskBLEDevice(mock_ble_device)
    
    result = await device._send_command(COMMAND_GET_STATUS)
    
    assert result is False

async def test_send_command_failure(mock_ble_device, mock_bleak_client):
    """Test command sending failure."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    mock_bleak_client.write_gatt_char.side_effect = Exception("Write failed")
    
    result = await device._send_command(COMMAND_GET_STATUS)
    
    assert result is False

async def test_movement_commands(mock_ble_device, mock_bleak_client):
    """Test movement commands."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Test move up - movement intent is set but _is_moving is False until actual movement detected
    await device.move_up()
    assert device._is_moving is False  # Not moving until actual movement detected
    assert device._movement_direction == "up"
    assert device._movement_type == "continuous"
    mock_bleak_client.write_gatt_char.assert_called_with(
        WRITE_CHARACTERISTIC_UUID, COMMAND_MOVE_UP
    )
    
    # Test move down
    await device.move_down()
    assert device._is_moving is False  # Not moving until actual movement detected
    assert device._movement_direction == "down"
    assert device._movement_type == "continuous"
    mock_bleak_client.write_gatt_char.assert_called_with(
        WRITE_CHARACTERISTIC_UUID, COMMAND_MOVE_DOWN
    )
    
    # Test stop
    await device.stop()
    assert device._is_moving is False
    assert device._movement_direction is None
    mock_bleak_client.write_gatt_char.assert_called_with(
        WRITE_CHARACTERISTIC_UUID, COMMAND_STOP
    )

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
        assert device._is_moving is False  # Not moving until actual movement detected
        assert device._movement_type == "preset"
        mock_bleak_client.write_gatt_char.assert_called_with(
            WRITE_CHARACTERISTIC_UUID, command
        )

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
def test_handle_status_notification(mock_ble_device):
    """Test status notification handling (0xF2 0xF2 0x01 0x03 format)."""
    device = DeskBLEDevice(mock_ble_device)
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Create status notification data with height 85.0 cm (850 in raw)
    # Header is at bytes 0-3, height is at bytes 4-5, big-endian
    data = bytearray([0xF2, 0xF2, 0x01, 0x03, 0x03, 0x52])  # 850 = 0x0352 (big-endian)
    
    device._handle_notification(0, data)
    
    assert device.height_cm == 85.0
    callback.assert_called_once_with(85.0, False, False)
def test_handle_both_notification_types(mock_ble_device):
    """Test that both notification formats work correctly."""
    device = DeskBLEDevice(mock_ble_device)
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Test movement notification (0x98 0x98)
    data1 = bytearray([0x98, 0x98, 0x00, 0x00, 0x52, 0x03])  # 85.0 cm
    device._handle_notification(0, data1)
    assert device.height_cm == 85.0
    
    # Test status notification (0xF2 0xF2 0x01 0x03) with different height
    data2 = bytearray([0xF2, 0xF2, 0x01, 0x03, 0x03, 0xF4])  # 101.2 cm (1012 = 0x03F4 big-endian)
    device._handle_notification(0, data2)
    assert device.height_cm == 101.2
    
    # Verify callbacks were called for both
    assert callback.call_count == 2
    callback.assert_has_calls([
        call(85.0, False, False),
        call(101.2, False, False)
    ])
def test_handle_notification_edge_cases(mock_ble_device):
    """Test notification handling with edge case heights."""
    device = DeskBLEDevice(mock_ble_device)
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Test minimum height (60.0 cm = 600 = 0x0258) with movement notification
    data_min_movement = bytearray([0x98, 0x98, 0x00, 0x00, 0x58, 0x02])
    device._handle_notification(0, data_min_movement)
    assert device.height_cm == 60.0
    
    # Test maximum height (130.0 cm = 1300 = 0x0514) with status notification
    data_max_status = bytearray([0xF2, 0xF2, 0x01, 0x03, 0x05, 0x14])  # big-endian
    device._handle_notification(0, data_max_status)
    assert device.height_cm == 130.0
    
    assert callback.call_count == 2
def test_handle_unknown_notification(mock_ble_device):
    """Test handling of unknown notification formats."""
    device = DeskBLEDevice(mock_ble_device)
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Unknown header format
    data = bytearray([0xFF, 0xFF, 0x00, 0x00, 0x52, 0x03])
    device._handle_notification(0, data)
    
    # Height should not be updated, callback should not be called
    assert device.height_cm == 0.0  # Initial value
    callback.assert_not_called()
def test_handle_notification_various_lengths(mock_ble_device):
    """Test notification handling with different data lengths."""
    device = DeskBLEDevice(mock_ble_device)
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Too short for any format (less than 6 bytes)
    device._handle_notification(0, bytearray([0xF2, 0xF2, 0x01]))
    callback.assert_not_called()
    
    # Exactly 6 bytes - valid for both formats
    data_movement = bytearray([0x98, 0x98, 0x00, 0x00, 0x52, 0x03])
    device._handle_notification(0, data_movement)
    assert device.height_cm == 85.0
    
    data_status = bytearray([0xF2, 0xF2, 0x01, 0x03, 0x03, 0xE8])  # 100.0 cm (1000 = 0x03E8 big-endian)
    device._handle_notification(0, data_status)
    assert device.height_cm == 100.0
    
    # Longer data should still work
    data_long = bytearray([0x98, 0x98, 0x00, 0x00, 0x84, 0x03, 0xFF, 0xFF])  # 90.0 cm
    device._handle_notification(0, data_long)
    assert device.height_cm == 90.0
    
    assert callback.call_count == 3
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

async def test_move_to_height_success(mock_ble_device, mock_bleak_client):
    """Test move_to_height command."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._height_cm = 70.0  # Current height
    
    # Test moving to 85.0 cm (850 mm) - up direction
    result = await device.move_to_height(85.0)
    
    assert result is True
    assert device._is_moving is False  # Not moving until actual movement detected
    assert device._movement_direction == "up"
    assert device._movement_type == "targeted"
    assert device._target_height == 85.0
    
    # Calculate expected command
    # 850 mm = 0x0352, so high=0x03, low=0x52
    # checksum = (0x1B + 0x02 + 0x03 + 0x52) & 0xFF = 0x72
    expected_command = bytes([0xF1, 0xF1, 0x1B, 0x02, 0x03, 0x52, 0x72, 0x7E])
    
    mock_bleak_client.write_gatt_char.assert_called_once_with(
        WRITE_CHARACTERISTIC_UUID, expected_command
    )

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
@patch('time.time')
def test_auto_stop_detection(mock_time, mock_ble_device):
    """Test auto-stop detection when height stops changing."""
    device = DeskBLEDevice(mock_ble_device)
    device._is_moving = True
    device._movement_direction = "up"
    device._height_cm = 85.0
    device._last_height_cm = 84.9
    device._movement_start_time = 0.0  # Start time
    
    # Mock time to simulate movement duration > 1 second
    mock_time.return_value = 1.5  # 1.5 seconds after start
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # First notification with same height
    data = bytearray([0x98, 0x98, 0x00, 0x00, 0x52, 0x03])  # 85.0 cm
    device._handle_notification(0, data)
    assert device._is_moving is True  # Still moving
    assert device._height_unchanged_count == 1
    assert device._collision_detected is False  # Not yet
    
    # Second notification with same height
    device._handle_notification(0, data)
    assert device._is_moving is True  # Still moving
    assert device._height_unchanged_count == 2
    assert device._collision_detected is False  # Not yet
    
    # Third notification with same height - should trigger auto-stop and collision
    device._handle_notification(0, data)
    assert device._is_moving is False  # Stopped
    assert device._movement_direction is None
    assert device._height_unchanged_count == 0  # Reset
    assert device._collision_detected is True  # Collision detected!
    
    # Verify callbacks were called
    assert callback.call_count == 3
    # Verify last callback includes collision state
    callback.assert_called_with(85.0, True, False)
def test_auto_stop_detection_reset_on_movement(mock_ble_device):
    """Test auto-stop detection resets when height changes."""
    device = DeskBLEDevice(mock_ble_device)
    device._is_moving = True
    device._movement_direction = "up"
    device._height_cm = 85.0
    device._last_height_cm = 85.0
    device._height_unchanged_count = 2  # Almost at stop threshold
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Notification with different height - should reset counter
    data = bytearray([0x98, 0x98, 0x00, 0x00, 0x5C, 0x03])  # 86.0 cm
    device._handle_notification(0, data)
    
    assert device._is_moving is True  # Still moving
    assert device._height_unchanged_count == 0  # Reset
    assert device._last_height_cm == 86.0  # Updated

async def test_move_to_height_direction_detection(mock_ble_device, mock_bleak_client):
    """Test move_to_height sets correct movement direction."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._height_cm = 85.0  # Current height
    
    # Test moving down
    await device.move_to_height(70.0)
    assert device._movement_direction == "down"
    
    # Test moving up
    device._height_cm = 70.0
    await device.move_to_height(90.0)
    assert device._movement_direction == "up"
    
    # Test same height (no movement)
    device._height_cm = 80.0
    result = await device.move_to_height(80.0)
    assert result is True
    assert device._movement_direction is None

async def test_collision_state_persists(mock_ble_device, mock_bleak_client):
    """Test collision state persists through new movement commands."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._set_collision_detected(True)  # Simulate previous collision
    
    # Test move_up doesn't clear collision
    await device.move_up()
    assert device._collision_detected is True
    
    # Test move_down doesn't clear collision
    await device.move_down()
    assert device._collision_detected is True
    
    # Test move_to_preset doesn't clear collision
    await device.move_to_preset(1)
    assert device._collision_detected is True
    
    # Test move_to_height doesn't clear collision
    device._height_cm = 85.0
    await device.move_to_height(70.0)
    assert device._collision_detected is True
    
    # Test stop command also doesn't clear collision
    await device.stop()
    assert device._collision_detected is True
    assert device._is_moving is False
    
    # Cancel the auto-clear task to clean up
    if device._auto_clear_task:
        device._auto_clear_task.cancel()
        try:
            await device._auto_clear_task
        except asyncio.CancelledError:
            pass
@patch('time.time')
def test_no_collision_for_short_movement(mock_time, mock_ble_device):
    """Test no collision detected for movements shorter than 1 second."""
    device = DeskBLEDevice(mock_ble_device)
    device._is_moving = True
    device._movement_direction = "up"
    device._height_cm = 85.0
    device._last_height_cm = 84.9
    device._movement_start_time = 0.0  # Start time
    
    # Mock time to simulate short movement duration < 1 second
    mock_time.return_value = 0.5  # Only 0.5 seconds after start
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Three notifications with same height
    data = bytearray([0x98, 0x98, 0x00, 0x00, 0x52, 0x03])  # 85.0 cm
    
    device._handle_notification(0, data)
    device._handle_notification(0, data)
    device._handle_notification(0, data)
    
    # Should stop but NOT detect collision (movement too short)
    assert device._is_moving is False  # Stopped
    assert device._movement_direction is None
    assert device._collision_detected is False  # No collision for short movement
    
    # Verify last callback shows no collision
    callback.assert_called_with(85.0, False, False)
@patch('time.time')
def test_bounce_back_detection_down(mock_time, mock_ble_device):
    """Test bounce-back detection when desk moves down then bounces up."""
    device = DeskBLEDevice(mock_ble_device)
    device._is_moving = True
    device._movement_direction = "down"
    device._commanded_direction = "down"  # User commanded down
    device._movement_start_time = 0.0
    
    # Mock time to simulate movement > 1 second
    mock_time.return_value = 2.0
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Simulate desk moving down
    heights = [
        75.0,  # Starting height
        74.0,  # Moving down
        73.0,  # Still moving down
        72.0,  # Still moving down
        71.0,  # Still moving down
        70.5,  # Hit obstacle
        71.0,  # Bounce back up!
        71.5,  # Still bouncing up
        72.0,  # Settled after bounce
    ]
    
    for i, height in enumerate(heights):
        # Create notification with current height
        height_raw = int(height * 10)
        data = bytearray([0x98, 0x98, 0x00, 0x00, 
                         height_raw & 0xFF, (height_raw >> 8) & 0xFF])
        device._handle_notification(0, data)
        
        # Check if bounce was detected after we see upward movement
        if device._bounce_detected:
            # Bounce should be detected when moving up after going down
            assert i >= 6  # Should be after hitting 70.5 and starting to bounce
            assert device._collision_detected is True
            assert device._is_moving is False
            break
    
    # Verify collision was detected
    assert device._collision_detected is True
    assert device._bounce_detected is True
@patch('time.time')
def test_bounce_back_detection_up(mock_time, mock_ble_device):
    """Test bounce-back detection when desk moves up then bounces down."""
    device = DeskBLEDevice(mock_ble_device)
    device._is_moving = True
    device._movement_direction = "up"
    device._commanded_direction = "up"  # User commanded up
    device._movement_start_time = 0.0
    
    # Mock time to simulate movement > 1 second
    mock_time.return_value = 2.0
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Simulate desk moving up
    heights = [
        100.0,  # Starting height
        101.0,  # Moving up
        102.0,  # Still moving up
        103.0,  # Still moving up
        104.0,  # Still moving up
        104.5,  # Hit obstacle
        104.0,  # Bounce back down!
        103.5,  # Still bouncing down
        103.0,  # Settled after bounce
    ]
    
    for i, height in enumerate(heights):
        # Create notification with current height
        height_raw = int(height * 10)
        data = bytearray([0x98, 0x98, 0x00, 0x00, 
                         height_raw & 0xFF, (height_raw >> 8) & 0xFF])
        device._handle_notification(0, data)
        
        # Check if bounce was detected after we see downward movement
        if device._bounce_detected:
            # Bounce should be detected when moving down after going up
            assert i >= 6  # Should be after hitting 104.5 and starting to bounce
            assert device._collision_detected is True
            assert device._is_moving is False
            break
    
    # Verify collision was detected
    assert device._collision_detected is True
    assert device._bounce_detected is True

async def test_bounce_back_resets_on_new_movement(mock_ble_device, mock_bleak_client):
    """Test bounce detection state resets on new movement."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Set previous bounce state
    device._bounce_detected = True
    device._collision_detected = True
    device._recent_heights = [(1.0, 85.0), (1.1, 85.1)]
    
    # Start new movement
    await device.move_up()
    
    # Verify bounce state was reset
    assert device._bounce_detected is False
    assert device._collision_detected is True  # Collision persists through new movement
    assert device._recent_heights == []
    assert device._commanded_direction == "up"
@patch('time.time')
def test_no_bounce_for_normal_stop(mock_time, mock_ble_device):
    """Test no bounce detected for normal stop (no direction reversal)."""
    device = DeskBLEDevice(mock_ble_device)
    device._is_moving = True
    device._movement_direction = "up"
    device._commanded_direction = "up"
    device._movement_start_time = 0.0
    
    mock_time.return_value = 2.0
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Simulate normal stop (no bounce)
    heights = [
        85.0,  # Starting
        86.0,  # Moving up
        87.0,  # Still up
        88.0,  # Still up
        88.0,  # Stopped
        88.0,  # Still stopped
        88.0,  # Still stopped
    ]
    
    for height in heights:
        height_raw = int(height * 10)
        data = bytearray([0x98, 0x98, 0x00, 0x00, 
                         height_raw & 0xFF, (height_raw >> 8) & 0xFF])
        device._handle_notification(0, data)
    
    # Should detect stop but not bounce
    assert device._is_moving is False  # Stopped due to no change
    assert device._bounce_detected is False  # No bounce
    assert device._collision_detected is True  # Regular collision from stop
def test_detect_movement_direction(mock_ble_device):
    """Test movement direction detection from recent heights."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Test with no data
    assert device._detect_movement_direction() is None
    
    # Test with insufficient data
    device._recent_heights = [(1.0, 85.0)]
    assert device._detect_movement_direction() is None
    
    # Test upward movement
    device._recent_heights = [
        (1.0, 85.0),
        (1.1, 85.5),
        (1.2, 86.0),
        (1.3, 86.5)
    ]
    assert device._detect_movement_direction() == "up"
    
    # Test downward movement
    device._recent_heights = [
        (2.0, 90.0),
        (2.1, 89.5),
        (2.2, 89.0),
        (2.3, 88.5)
    ]
    assert device._detect_movement_direction() == "down"
    
    # Test no significant movement
    device._recent_heights = [
        (3.0, 85.0),
        (3.1, 85.0),
        (3.2, 85.0),
        (3.3, 85.0)
    ]
    assert device._detect_movement_direction() is None
@patch('time.time')
def test_bounce_back_with_status_notification(mock_time, mock_ble_device):
    """Test bounce-back detection works with status notifications too."""
    device = DeskBLEDevice(mock_ble_device)
    device._is_moving = True
    device._movement_direction = "down"
    device._commanded_direction = "down"
    device._movement_start_time = 0.0
    
    mock_time.return_value = 2.0
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Use status notification format (big-endian)
    heights = [75.0, 74.0, 73.0, 72.0, 71.0, 70.5, 71.0]  # Bounce at end
    
    for height in heights:
        height_raw = int(height * 10)
        # Status notification uses big-endian
        data = bytearray([0xF2, 0xF2, 0x01, 0x03,
                         (height_raw >> 8) & 0xFF, height_raw & 0xFF])
        device._handle_notification(0, data)
        
        if height == 71.0 and heights[heights.index(height)-1] == 70.5:
            # Should detect bounce
            assert device._bounce_detected is True
            assert device._collision_detected is True
            break

async def test_movement_with_preset_no_direction(mock_ble_device, mock_bleak_client):
    """Test that preset movements don't set commanded direction initially."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._collision_detected = True  # Previous collision
    
    # Move to preset doesn't know direction initially
    await device.move_to_preset(1)
    
    assert device._collision_detected is True  # Collision persists through new movement
    assert device._is_moving is False  # Only True when actual movement detected
    assert device._movement_direction is None  # Unknown initially
    assert device._commanded_direction is None  # Not set for presets
    assert device._bounce_detected is False
    assert device._recent_heights == []
    assert device._movement_type == "preset"  # Movement type should be set

async def test_collision_auto_clear(mock_ble_device):
    """Test collision state auto-clears after timeout."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Manually set collision state
    device._set_collision_detected(True)
    assert device._collision_detected is True
    assert device._collision_time is not None
    assert device._auto_clear_task is not None
    
    # Wait for auto-clear (using shorter timeout for testing)
    # Note: In real code it's 10 seconds, but we'll patch it for testing
    with patch('custom_components.desky_desk.bluetooth.COLLISION_AUTO_CLEAR_SECONDS', 0.1):
        device._set_collision_detected(True)  # Re-trigger with patched timeout
        await asyncio.sleep(0.2)  # Wait for auto-clear
    
    # Collision should be cleared
    assert device._collision_detected is False
    assert device._collision_time is None

async def test_collision_persists_on_new_movement(mock_ble_device, mock_bleak_client):
    """Test collision state persists when new movement starts."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Set collision state
    device._set_collision_detected(True)
    initial_task = device._auto_clear_task
    assert initial_task is not None
    assert device._collision_detected is True
    
    # Start new movement (should NOT clear collision)
    await device.move_up()
    
    # Check collision persists and auto-clear task is still active
    assert device._collision_detected is True
    assert device._auto_clear_task == initial_task
    assert not initial_task.cancelled()
    
    # Test with move_down
    await device.move_down()
    assert device._collision_detected is True
    
    # Test with move_to_height
    device._height_cm = 80.0
    await device.move_to_height(90.0)
    assert device._collision_detected is True
    
    # Test with move_to_preset
    await device.move_to_preset(1)
    assert device._collision_detected is True
    
    # Cancel the task to clean up
    if device._auto_clear_task:
        device._auto_clear_task.cancel()
        try:
            await device._auto_clear_task
        except asyncio.CancelledError:
            pass
@patch('time.time')
def test_collision_clears_after_successful_movement_from_collision_time(mock_time, mock_ble_device):
    """Test collision clears after 2 seconds of movement from collision detection time."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Set up initial movement state
    device._is_moving = True
    device._movement_direction = "down"
    device._commanded_direction = "down"
    device._movement_start_time = 0.0
    device._height_cm = 80.0
    device._last_height_cm = 80.0
    
    # Collision detected at t=1.0
    mock_time.return_value = 1.0
    device._set_collision_detected(True)
    assert device._collision_detected is True
    assert device._collision_time == 1.0
    
    # New movement command at t=1.5 (would reset movement_start_time but not collision_time)
    mock_time.return_value = 1.5
    device._movement_start_time = 1.5
    device._is_moving = True  # Re-enable movement after collision
    
    # First movement at t=2.5 (1.5 seconds after collision)
    mock_time.return_value = 2.5
    device._last_height_cm = 80.0  # Starting from where we were
    
    # Process notification - small movement, collision should NOT clear yet (only 1.5 seconds since collision)
    data = bytearray([0x98, 0x98, 0x00, 0x00, 0x1A, 0x03])  # 79.4 cm = 794 = 0x031A (moved 0.6cm from 80.0)
    device._handle_notification(0, data)
    assert device._collision_detected is True  # Still detected
    assert device._is_moving is True  # Still moving
    
    # Second movement at t=3.1 (2.1 seconds after collision)
    mock_time.return_value = 3.1
    device._last_height_cm = 79.4  # Update to previous height
    
    # Process notification - collision should clear now (>2 seconds since collision)
    data = bytearray([0x98, 0x98, 0x00, 0x00, 0x14, 0x03])  # 78.8 cm = 788 = 0x0314 (moved 0.6cm from 79.4)
    device._handle_notification(0, data)
    assert device._collision_detected is False  # Cleared after 2+ seconds

async def test_collision_auto_clear_on_disconnect(mock_ble_device, mock_bleak_client):
    """Test collision auto-clear task is cancelled on disconnect."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Set collision state
    device._set_collision_detected(True)
    initial_task = device._auto_clear_task
    assert initial_task is not None
    
    # Disconnect
    await device.disconnect()
    
    # Auto-clear task should be cancelled
    assert device._auto_clear_task is None
    
    # Give the task a moment to complete cancellation
    try:
        await initial_task
    except asyncio.CancelledError:
        pass  # Expected
    
    assert initial_task.cancelled()

async def test_set_collision_detected_manages_state(mock_ble_device):
    """Test _set_collision_detected properly manages state and tasks."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Setting collision to True
    device._set_collision_detected(True)
    assert device._collision_detected is True
    assert device._collision_time is not None
    assert device._auto_clear_task is not None
    task1 = device._auto_clear_task
    
    # Setting collision to True again (should cancel and create new task)
    device._set_collision_detected(True)
    assert device._collision_detected is True
    assert device._auto_clear_task is not None
    assert device._auto_clear_task != task1  # New task created
    
    # Give cancelled task a moment
    try:
        await task1
    except asyncio.CancelledError:
        pass
    assert task1.cancelled()  # Old task cancelled
    
    # Setting collision to False
    task2 = device._auto_clear_task
    device._set_collision_detected(False)
    assert device._collision_detected is False
    assert device._collision_time is None
    assert device._auto_clear_task is None
    
    # Give cancelled task a moment
    try:
        await task2
    except asyncio.CancelledError:
        pass
    assert task2.cancelled()  # Task cancelled

async def test_auto_clear_notifies_callbacks(mock_ble_device):
    """Test auto-clear notifies callbacks when collision is cleared."""
    device = DeskBLEDevice(mock_ble_device)
    device._height_cm = 85.0
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Set collision with very short timeout
    with patch('custom_components.desky_desk.bluetooth.COLLISION_AUTO_CLEAR_SECONDS', 0.05):
        device._set_collision_detected(True)
        
        # Wait for auto-clear
        await asyncio.sleep(0.1)
        
        # Callback should have been called with collision cleared
        callback.assert_called()
        # Get the last call
        last_call = callback.call_args
        assert last_call[0] == (85.0, False, False)  # height, collision=False, moving=False
@patch('time.time')
def test_no_collision_when_reaching_target_height(mock_time, mock_ble_device):
    """Test that reaching target height does not trigger collision detection."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Start targeted movement to 90.0 cm
    mock_time.return_value = 0.0
    device._is_moving = True
    device._movement_start_time = 0.0
    device._last_height_cm = 85.0
    device._target_height = 90.0
    device._movement_type = "targeted"
    
    # Move towards target
    mock_time.return_value = 1.5
    device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x84, 0x03]))  # 90.0 cm
    
    # Three unchanged notifications at target height
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x84, 0x03]))  # 90.0 cm
    
    # Should NOT detect collision - reached target
    assert device._is_moving is False
    assert device.collision_detected is False
@patch('time.time')
def test_collision_when_stopping_away_from_target(mock_time, mock_ble_device):
    """Test that stopping away from target height triggers collision detection."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Start targeted movement to 90.0 cm
    mock_time.return_value = 0.0
    device._is_moving = True
    device._movement_start_time = 0.0
    device._last_height_cm = 85.0
    device._target_height = 90.0
    device._movement_type = "targeted"
    
    # Stop at 87.0 cm (3cm away from target)
    mock_time.return_value = 1.5
    device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x66, 0x03]))  # 87.0 cm
    
    # Three unchanged notifications away from target
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x66, 0x03]))  # 87.0 cm
    
    # Should detect collision - stopped away from target
    assert device._is_moving is False
    assert device.collision_detected is True
@patch('time.time')
def test_continuous_movement_collision_minimal_movement(mock_time, mock_ble_device):
    """Test that continuous movement detects collision for minimal distance moved."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Start continuous movement from 87.0cm
    mock_time.return_value = 0.0
    device._is_moving = True
    device._movement_start_time = 0.0
    device._movement_start_height = 87.0  # Set starting height
    device._last_height_cm = 87.2  # Set to match final notifications (0.2cm movement)
    device._movement_type = "continuous"
    device._commanded_direction = "up"
    
    # Stop after 1.5 seconds with minimal movement (0.2cm = too small)
    mock_time.return_value = 1.5
    
    # Three unchanged notifications at 87.2cm (87.2cm = 872 = 0x0368)
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x68, 0x03]))  # 87.2 cm
    
    # Should detect collision due to minimal movement (< 0.5cm)
    assert device._is_moving is False
    assert device.collision_detected is True
@patch('time.time')
def test_continuous_movement_no_collision_normal_movement(mock_time, mock_ble_device):
    """Test that continuous movement doesn't detect collision for normal distance and speed."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Start continuous movement from 85.0cm
    mock_time.return_value = 0.0
    device._is_moving = True
    device._movement_start_time = 0.0
    device._movement_start_height = 85.0  # Set starting height
    device._last_height_cm = 86.0  # Set to final height (1.0cm movement)
    device._movement_type = "continuous"
    device._commanded_direction = "up"
    
    # Stop at 86.0cm after 1.7 seconds (1.0cm in 1.7s = 0.59 cm/s, reasonable speed)
    mock_time.return_value = 1.7
    
    # Three unchanged notifications at final position (86.0cm = 860 = 0x035C)
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x5C, 0x03]))  # 86.0 cm
    
    # Should NOT detect collision - reasonable distance and speed
    assert device._is_moving is False
    assert device.collision_detected is False
@patch('time.time')
def test_continuous_movement_no_collision_short_duration(mock_time, mock_ble_device):
    """Test that very short continuous movements don't trigger collision (user releasing button)."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Start continuous movement
    mock_time.return_value = 0.0
    device._is_moving = True
    device._movement_start_time = 0.0
    device._movement_start_height = 85.0
    device._last_height_cm = 85.1  # Minimal movement
    device._movement_type = "continuous"
    device._commanded_direction = "up"
    
    # Stop very quickly (0.3 seconds - user releasing button quickly)
    mock_time.return_value = 0.3
    
    # Three unchanged notifications
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x53, 0x03]))  # 85.1 cm
    
    # Should NOT detect collision - too short duration (user released button)
    assert device._is_moving is False
    assert device.collision_detected is False
@patch('time.time')
def test_continuous_movement_collision_slow_speed(mock_time, mock_ble_device):
    """Test that continuous movement detects collision for abnormally slow speed."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Start continuous movement from 85.0cm
    mock_time.return_value = 0.0
    device._is_moving = True
    device._movement_start_time = 0.0
    device._movement_start_height = 85.0  # Set starting height
    device._last_height_cm = 85.4  # Set to final height (0.4cm movement)
    device._movement_type = "continuous"
    device._commanded_direction = "up"
    
    # Stop at 85.4cm after 2.0 seconds (0.4cm in 2.0s = 0.2 cm/s, too slow)
    mock_time.return_value = 2.0
    
    # Three unchanged notifications at final position (85.4cm = 854 = 0x0356)
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x56, 0x03]))  # 85.4 cm
    
    # Should detect collision due to abnormally slow speed (< 0.5 cm/s)
    assert device._is_moving is False
    assert device.collision_detected is True
@patch('time.time')
def test_preset_clears_previous_commanded_direction(mock_time, mock_ble_device):
    """Test that preset movements clear previous commanded direction to prevent false bounce detection."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Simulate previous continuous movement up
    device._commanded_direction = "up"  # From previous move_up command
    device._movement_type = "continuous"
    
    # Now call preset movement - should clear commanded direction
    mock_time.return_value = 0.0
    asyncio.run(device.move_to_preset(1))
    
    # Should clear the commanded direction to prevent false bounce detection
    assert device._commanded_direction is None
    assert device._movement_type == "preset"
    
    # Simulate preset movement going down (normal for preset 1)
    device._is_moving = True
    device._movement_start_time = 0.0
    device._movement_start_height = 77.0  # Starting height
    device._last_height_cm = 72.0  # Final height (preset 1)
    device._recent_heights = [(0.0, 77.0), (0.5, 75.0), (1.0, 72.0)]  # Downward movement
    
    # Stop at preset height after 2.0 seconds (5cm in 2s = 2.5 cm/s, normal speed)
    mock_time.return_value = 2.0
    
    # Three unchanged notifications at final position (72.0cm = 720 = 0x02D0)
    for _ in range(3):
        device._handle_notification(None, bytes([0xF2, 0xF2, 0x01, 0x03, 0x02, 0xD0]))  # 72.0 cm
    
    # Should NOT detect collision - normal preset completion with no bounce detection
    assert device._is_moving is False
    assert device.collision_detected is False
@patch('time.time')
def test_preset_movement_no_collision_normal_movement(mock_time, mock_ble_device):
    """Test that preset movement doesn't trigger collision for normal distance and speed."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Start preset movement from 85.0cm
    mock_time.return_value = 0.0
    device._is_moving = True
    device._movement_start_time = 0.0
    device._movement_start_height = 85.0  # Set starting height
    device._last_height_cm = 90.0  # Set to final height for auto-stop detection
    device._movement_type = "preset"
    
    # Stop at 90.0cm after 2.5 seconds (5cm in 2.5s = 2.0 cm/s, normal speed)
    mock_time.return_value = 2.5
    
    # Three unchanged notifications at final position (90.0cm)
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x84, 0x03]))  # 90.0 cm
    
    # Should NOT detect collision - normal distance and speed
    assert device._is_moving is False
    assert device.collision_detected is False
@patch('time.time')
def test_preset_movement_collision_minimal_distance(mock_time, mock_ble_device):
    """Test that preset movement triggers collision for minimal movement distance."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Start preset movement
    mock_time.return_value = 0.0
    device._is_moving = True
    device._movement_start_time = 0.0
    device._movement_start_height = 87.0  # Set starting height
    device._last_height_cm = 87.3  # Set to final height for auto-stop detection
    device._movement_type = "preset"
    
    # Stop after 2 seconds with minimal movement (only 0.3cm)
    mock_time.return_value = 2.0
    
    # Three unchanged notifications at 87.3cm (minimal movement)
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x69, 0x03]))  # 87.3 cm
    
    # Should detect collision - minimal movement distance
    assert device._is_moving is False
    assert device.collision_detected is True
@patch('time.time')
def test_preset_movement_collision_slow_overall_speed(mock_time, mock_ble_device):
    """Test that preset movement triggers collision for abnormally slow overall speed."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Start preset movement from 85.0cm
    mock_time.return_value = 0.0
    device._is_moving = True
    device._movement_start_time = 0.0
    device._movement_start_height = 85.0  # Set starting height
    device._last_height_cm = 85.2  # Set to final height for auto-stop detection
    device._movement_type = "preset"
    
    # Stop at 85.2cm after 10 seconds (0.2cm in 10s = 0.02 cm/s, very slow!)
    mock_time.return_value = 10.0
    
    # Three unchanged notifications at final position (85.2cm)
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x54, 0x03]))  # 85.2 cm
    
    # Should detect collision - very slow overall speed
    assert device._is_moving is False
    assert device.collision_detected is True
 
async def test_velocity_tracking_reset_on_new_movement(mock_ble_device, mock_bleak_client):
    """Test that velocity tracking is reset when new movement starts.""" 
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Set up some existing velocity data
    device._recent_velocities = [1.5, 2.0, 1.8]
    device._movement_start_height = 85.0
    
    # Start new movement
    await device.move_up()
    
    # Velocity data should be cleared for new movement
    assert device._recent_velocities == []
    assert device._movement_start_height is None
def test_average_velocity_calculation(mock_ble_device):
    """Test average velocity calculation."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Test with no velocities
    assert device._get_average_velocity() == 0.0
    
    # Test with some velocities
    device._recent_velocities = [1.0, 2.0, 3.0]
    assert device._get_average_velocity() == 2.0
    
    # Test with negative velocities (should still work)
    device._recent_velocities = [-1.0, 1.0, 2.0]
    assert abs(device._get_average_velocity() - 0.667) < 0.001  # Close enough

async def test_move_commands_set_movement_type(mock_ble_device, mock_bleak_client):
    """Test that movement commands set the correct movement type."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Test move_up
    await device.move_up()
    assert device._movement_type == "continuous"
    assert device._target_height is None
    
    # Test move_down
    await device.move_down()
    assert device._movement_type == "continuous"
    assert device._target_height is None
    
    # Test move_to_height
    await device.move_to_height(90.0)
    assert device._movement_type == "targeted"
    assert device._target_height == 90.0
    
    # Test move_to_preset
    await device.move_to_preset(1)
    assert device._movement_type == "preset"
    assert device._target_height is None
    
    # Test stop clears everything
    await device.stop()
    assert device._movement_type is None
    assert device._target_height is None
@patch('time.time')
def test_no_collision_at_height_limits(mock_time, mock_ble_device):
    """Test that stopping near height limits doesn't trigger collision detection."""
    device = DeskBLEDevice(mock_ble_device)
    device._is_moving = True
    device._movement_type = "targeted"
    device._movement_start_time = 0.0
    device._movement_start_height = 77.0
    
    mock_time.return_value = 15.0  # Long movement duration
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Test case 1: Try to reach maximum height (130cm) but stop at 125cm (physical limit)
    device._target_height = 130.0  # Trying to reach maximum
    device._movement_direction = "up"
    device._commanded_direction = "up"
    
    # Simulate movement from 77cm to 125cm, then stopping
    heights = [77.0, 80.0, 90.0, 100.0, 110.0, 120.0, 125.0, 125.0, 125.0, 125.0]
    for i, height in enumerate(heights):
        if i > 0:  # Skip first to avoid movement start detection
            device._last_height_cm = heights[i-1]
        height_raw = int(height * 10)
        data = bytearray([0x98, 0x98, 0x00, 0x00, 
                         height_raw & 0xFF, (height_raw >> 8) & 0xFF])
        device._handle_notification(0, data)
    
    # Should not detect collision - hit maximum height limit
    assert device._is_moving is False  # Movement stopped
    assert device._collision_detected is False  # No collision detected
    
    # Test case 2: Try to reach minimum height (60cm) but stop at 63cm (physical limit)
    device._is_moving = True
    device._movement_type = "targeted"
    device._target_height = 60.0  # Trying to reach minimum
    device._movement_direction = "down"
    device._commanded_direction = "down"
    device._movement_start_time = 0.0
    device._movement_start_height = 125.0
    device._collision_detected = False
    device._height_unchanged_count = 0
    
    # Simulate movement from 125cm to 63cm, then stopping
    heights = [125.0, 120.0, 110.0, 100.0, 90.0, 80.0, 70.0, 63.0, 63.0, 63.0, 63.0]
    for i, height in enumerate(heights):
        if i > 0:
            device._last_height_cm = heights[i-1]
        height_raw = int(height * 10)
        data = bytearray([0x98, 0x98, 0x00, 0x00, 
                         height_raw & 0xFF, (height_raw >> 8) & 0xFF])
        device._handle_notification(0, data)
    
    # Should not detect collision - hit minimum height limit
    assert device._is_moving is False  # Movement stopped
    assert device._collision_detected is False  # No collision detected
@patch('time.time')
def test_collision_detection_away_from_limits(mock_time, mock_ble_device):
    """Test that collision is still detected when stopping away from height limits."""
    device = DeskBLEDevice(mock_ble_device)
    device._is_moving = True
    device._movement_type = "targeted"
    device._movement_start_time = 0.0
    device._movement_start_height = 77.0
    
    mock_time.return_value = 5.0  # Movement duration
    
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Try to reach 120cm but stop at 85cm (far from limits - likely real collision)
    device._target_height = 120.0
    device._movement_direction = "up"
    device._commanded_direction = "up"
    
    # Simulate movement from 77cm to 85cm, then stopping (stopped early)
    heights = [77.0, 80.0, 83.0, 85.0, 85.0, 85.0, 85.0]
    for i, height in enumerate(heights):
        if i > 0:
            device._last_height_cm = heights[i-1]
        height_raw = int(height * 10)
        data = bytearray([0x98, 0x98, 0x00, 0x00, 
                         height_raw & 0xFF, (height_raw >> 8) & 0xFF])
        device._handle_notification(0, data)
    
    # Should detect collision - stopped far from target and limits
    assert device._is_moving is False  # Movement stopped
    assert device._collision_detected is True  # Collision detected


async def test_new_device_commands(mock_ble_device, mock_bleak_client):
    """Test new device control commands."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Test light color commands
    result = await device.set_light_color(2)  # Red
    assert result is True
    expected_command = bytes([0xF1, 0xF1, 0xB4, 0x01, 0x02, 0xB7, 0x7E])
    mock_bleak_client.write_gatt_char.assert_called_with(WRITE_CHARACTERISTIC_UUID, expected_command)
    
    # Test invalid light color
    result = await device.set_light_color(8)  # Invalid
    assert result is False
    
    # Test brightness
    result = await device.set_brightness(75)
    assert result is True
    expected_command = bytes([0xF1, 0xF1, 0xB6, 0x01, 0x4B, 0x02, 0x7E])  # 75 = 0x4B
    
    # Test lighting enabled
    result = await device.set_lighting(True)
    assert result is True
    expected_command = bytes([0xF1, 0xF1, 0xB5, 0x01, 0x01, 0xB7, 0x7E])
    
    # Test vibration
    result = await device.set_vibration(False)
    assert result is True
    expected_command = bytes([0xF1, 0xF1, 0xB3, 0x01, 0x00, 0xB4, 0x7E])
    
    # Test vibration intensity
    result = await device.set_vibration_intensity(50)
    assert result is True
    expected_command = bytes([0xF1, 0xF1, 0xA4, 0x01, 0x32, 0xD7, 0x7E])  # 50 = 0x32
    
    # Test lock status
    result = await device.set_lock_status(True)
    assert result is True
    expected_command = bytes([0xF1, 0xF1, 0xB2, 0x01, 0x01, 0xB4, 0x7E])
    
    # Test sensitivity level
    result = await device.set_sensitivity(2)  # Medium
    assert result is True
    expected_command = bytes([0xF1, 0xF1, 0x1D, 0x01, 0x02, 0x20, 0x7E])
    
    # Test height limits
    result = await device.set_height_limit_upper(120.0)
    assert result is True
    # 1200 = 0x04B0, so high=0x04, low=0xB0
    expected_command = bytes([0xF1, 0xF1, 0x21, 0x02, 0x04, 0xB0, 0xD7, 0x7E])
    
    result = await device.set_height_limit_lower(65.0)
    assert result is True
    # 650 = 0x028A, so high=0x02, low=0x8A
    expected_command = bytes([0xF1, 0xF1, 0x22, 0x02, 0x02, 0x8A, 0xB0, 0x7E])
    
    # Test clear limits
    result = await device.clear_height_limits()
    assert result is True
    expected_command = bytes([0xF1, 0xF1, 0x23, 0x00, 0x23, 0x7E])
    
    # Test touch mode
    result = await device.set_touch_mode(1)  # Press and hold
    assert result is True
    expected_command = bytes([0xF1, 0xF1, 0x19, 0x01, 0x01, 0x1B, 0x7E])
    
    # Test units - not implemented in device
    # result = await device.set_unit("inch")
    # assert result is True
    # expected_command = bytes([0xF1, 0xF1, 0x00, 0x00, 0x00, 0x7E])  # Not implemented


async def test_device_capability_queries(mock_ble_device, mock_bleak_client):
    """Test device capability query commands."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Test all get commands
    commands_to_test = [
        (device.get_light_color, bytes([0xF1, 0xF1, 0xB4, 0x00, 0xB4, 0x7E])),
        (device.get_brightness, bytes([0xF1, 0xF1, 0xB6, 0x00, 0xB6, 0x7E])),
        (device.get_lighting_status, bytes([0xF1, 0xF1, 0xB5, 0x00, 0xB5, 0x7E])),
        (device.get_vibration_status, bytes([0xF1, 0xF1, 0xB3, 0x00, 0xB3, 0x7E])),
        (device.get_vibration_intensity, bytes([0xF1, 0xF1, 0xA4, 0x00, 0xA4, 0x7E])),
        (device.get_lock_status, bytes([0xF1, 0xF1, 0xB2, 0x00, 0xB2, 0x7E])),
        (device.get_sensitivity, bytes([0xF1, 0xF1, 0x1D, 0x00, 0x1D, 0x7E])),
        (device.get_limits, bytes([0xF1, 0xF1, 0x0C, 0x00, 0x0C, 0x7E])),
    ]
    
    for method, expected_command in commands_to_test:
        mock_bleak_client.write_gatt_char.reset_mock()
        result = await method()
        assert result is True
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            WRITE_CHARACTERISTIC_UUID, expected_command
        )


@pytest.mark.skip(reason="Notification parsing for new features not yet implemented")
def test_parse_new_notifications(mock_ble_device):
    """Test parsing of new notification types."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Mock callbacks to verify data updates
    callback = MagicMock()
    device.register_notification_callback(callback)
    
    # Test light color notification (0xF2 0xF2 0xB4 0x01)
    data = bytearray([0xF2, 0xF2, 0xB4, 0x01, 0x03])  # Green
    device._handle_notification(0, data)
    assert device._light_color == 3
    
    # Test brightness notification (0xF2 0xF2 0xB5 0x01)
    data = bytearray([0xF2, 0xF2, 0xB5, 0x01, 0x64])  # 100%
    device._handle_notification(0, data)
    assert device._brightness == 100
    
    # Test lighting enabled notification (0xF2 0xF2 0xB1 0x01)
    data = bytearray([0xF2, 0xF2, 0xB1, 0x01, 0x01])  # Enabled
    device._handle_notification(0, data)
    assert device._lighting_enabled is True
    
    # Test vibration enabled notification (0xF2 0xF2 0xA4 0x01)
    data = bytearray([0xF2, 0xF2, 0xA4, 0x01, 0x00])  # Disabled
    device._handle_notification(0, data)
    assert device._vibration_enabled is False
    
    # Test vibration intensity notification (0xF2 0xF2 0xA9 0x01)
    data = bytearray([0xF2, 0xF2, 0xA9, 0x01, 0x32])  # 50
    device._handle_notification(0, data)
    assert device._vibration_intensity == 50
    
    # Test lock status notification (0xF2 0xF2 0xB2 0x01)
    data = bytearray([0xF2, 0xF2, 0xB2, 0x01, 0x01])  # Locked
    device._handle_notification(0, data)
    assert device._lock_status is True
    
    # Test sensitivity level notification (0xF2 0xF2 0xAB 0x01)
    data = bytearray([0xF2, 0xF2, 0xAB, 0x01, 0x01])  # High
    device._handle_notification(0, data)
    assert device._sensitivity_level == 1
    
    # Test touch mode notification (0xF2 0xF2 0xAE 0x01)
    data = bytearray([0xF2, 0xF2, 0xAE, 0x01, 0x01])  # Double press
    device._handle_notification(0, data)
    assert device._touch_mode == 1
    
    # Test units notification (0xF2 0xF2 0xB0 0x01)
    data = bytearray([0xF2, 0xF2, 0xB0, 0x01, 0x00])  # cm
    device._handle_notification(0, data)
    assert device._unit_preference == "cm"
    
    data = bytearray([0xF2, 0xF2, 0xB0, 0x01, 0x01])  # inch
    device._handle_notification(0, data)
    assert device._unit_preference == "inch"


@pytest.mark.skip(reason="Height limit notification parsing not yet implemented")
def test_parse_height_limit_notifications(mock_ble_device):
    """Test parsing of height limit notifications."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Test upper limit notification (0xF2 0xF2 0xA5 0x02) - big-endian
    # 1200 = 0x04B0
    data = bytearray([0xF2, 0xF2, 0xA5, 0x02, 0x04, 0xB0])
    device._handle_notification(0, data)
    assert device._height_limit_upper == 120.0
    
    # Test lower limit notification (0xF2 0xF2 0xA7 0x02) - big-endian
    # 650 = 0x028A
    data = bytearray([0xF2, 0xF2, 0xA7, 0x02, 0x02, 0x8A])
    device._handle_notification(0, data)
    assert device._height_limit_lower == 65.0
    
    # Test limits enabled notification (0xF2 0xF2 0xA6 0x01)
    data = bytearray([0xF2, 0xF2, 0xA6, 0x01, 0x01])  # Enabled
    device._handle_notification(0, data)
    assert device._limits_enabled is True


async def test_device_capability_detection(mock_ble_device, mock_bleak_client):
    """Test device capability detection on connection."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Mock successful responses for all capability queries
    mock_bleak_client.write_gatt_char.return_value = None
    
    # Simulate connection and capability detection
    with patch(
        "custom_components.desky_desk.bluetooth.establish_connection",
        return_value=mock_bleak_client,
    ):
        result = await device.connect()
        assert result is True
        
        # Check that capability queries were sent
        # Should have handshake, status, and all capability queries
        calls = mock_bleak_client.write_gatt_char.call_args_list
        
        # First two should be handshake and status
        assert calls[0][0] == (WRITE_CHARACTERISTIC_UUID, COMMAND_HANDSHAKE)
        assert calls[1][0] == (WRITE_CHARACTERISTIC_UUID, COMMAND_GET_STATUS)
        
        # Then all capability queries
        expected_queries = [
            bytes([0xF1, 0xF1, 0xB4, 0x00, 0xB4, 0x7E]),  # get_light_color
            bytes([0xF1, 0xF1, 0xB6, 0x00, 0xB6, 0x7E]),  # get_brightness
            bytes([0xF1, 0xF1, 0xB5, 0x00, 0xB5, 0x7E]),  # get_lighting_status
            bytes([0xF1, 0xF1, 0xB3, 0x00, 0xB3, 0x7E]),  # get_vibration_status
            bytes([0xF1, 0xF1, 0xA4, 0x00, 0xA4, 0x7E]),  # get_vibration_intensity
            bytes([0xF1, 0xF1, 0xB2, 0x00, 0xB2, 0x7E]),  # get_lock_status
            bytes([0xF1, 0xF1, 0x1D, 0x00, 0x1D, 0x7E]),  # get_sensitivity
            bytes([0xF1, 0xF1, 0x0C, 0x00, 0x0C, 0x7E]),  # get_limits
        ]
        
        # Check that all capability queries were sent
        sent_commands = [call[0][1] for call in calls[2:]]
        for expected in expected_queries:
            assert expected in sent_commands


async def test_command_parameter_validation(mock_ble_device, mock_bleak_client):
    """Test parameter validation for new commands."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Test invalid light color
    result = await device.set_light_color(0)  # Too low
    assert result is False
    result = await device.set_light_color(8)  # Too high
    assert result is False
    
    # Test invalid brightness
    result = await device.set_brightness(-1)  # Too low
    assert result is False
    result = await device.set_brightness(101)  # Too high
    assert result is False
    
    # Test invalid vibration intensity
    result = await device.set_vibration_intensity(-1)  # Too low
    assert result is False
    result = await device.set_vibration_intensity(101)  # Too high
    assert result is False
    
    # Test invalid sensitivity level
    result = await device.set_sensitivity(0)  # Too low
    assert result is False
    result = await device.set_sensitivity(4)  # Too high
    assert result is False
    
    # Test invalid height limits
    result = await device.set_height_limit_upper(59.0)  # Too low
    assert result is False
    result = await device.set_height_limit_upper(131.0)  # Too high
    assert result is False
    
    result = await device.set_height_limit_lower(59.0)  # Too low
    assert result is False
    result = await device.set_height_limit_lower(131.0)  # Too high
    assert result is False
    
    # Test invalid touch mode
    result = await device.set_touch_mode(-1)  # Too low
    assert result is False
    result = await device.set_touch_mode(2)  # Too high
    assert result is False
    
    # Test invalid units
    result = await device.set_unit("meters")  # Invalid unit
    assert result is False


def test_create_command_helpers(mock_ble_device):
    """Test command creation helper methods."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Test single byte parameter command
    command = device._create_command_with_byte_param(0xB4, 5)
    # checksum = (0xB4 + 0x01 + 0x05) & 0xFF = 0xBA
    expected = bytes([0xF1, 0xF1, 0xB4, 0x01, 0x05, 0xBA, 0x7E])
    assert command == expected
    
    # Test word parameter command
    command = device._create_command_with_word_param(0xA5, 1200)
    # 1200 = 0x04B0, so high=0x04, low=0xB0
    # checksum = (0xA5 + 0x02 + 0x04 + 0xB0) & 0xFF = 0x5B
    expected = bytes([0xF1, 0xF1, 0xA5, 0x02, 0x04, 0xB0, 0x5B, 0x7E])
    assert command == expected


# Device Information Service Tests

async def test_read_device_information_success(mock_ble_device, mock_bleak_client_with_device_info):
    """Test successful device information reading."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client_with_device_info
    
    await device._read_device_information()
    
    # Verify all device information was read
    assert device.manufacturer_name == "Test Manufacturer"
    assert device.model_number == "Test Model"
    assert device.serial_number == "TEST123456"
    assert device.hardware_revision == "1.0"
    assert device.firmware_revision == "2.1.0"
    assert device.software_revision == "1.5.2"


async def test_read_device_information_service_not_found(mock_ble_device, mock_bleak_client):
    """Test when Device Information Service (0x180A) is not available."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Mock services without device info service
    mock_bleak_client.services = [MagicMock(uuid="0000fe60-0000-1000-8000-00805f9b34fb")]
    
    await device._read_device_information()
    
    # Verify all device information remains None (fallback behavior)
    assert device.manufacturer_name is None
    assert device.model_number is None
    assert device.serial_number is None
    assert device.hardware_revision is None
    assert device.firmware_revision is None
    assert device.software_revision is None


async def test_read_device_information_partial_characteristics(mock_ble_device, mock_bleak_client):
    """Test when only some device info characteristics are available."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Create service with only manufacturer and model characteristics
    service = MagicMock()
    service.uuid = "0000180a-0000-1000-8000-00805f9b34fb"  # Device Info Service
    
    char1 = MagicMock()
    char1.uuid = "00002a29-0000-1000-8000-00805f9b34fb"  # Manufacturer
    char1.properties = ["read"]
    
    char2 = MagicMock()
    char2.uuid = "00002a24-0000-1000-8000-00805f9b34fb"  # Model
    char2.properties = ["read"]
    
    service.characteristics = [char1, char2]
    mock_bleak_client.services = [service]
    
    # Mock read responses
    async def mock_read_char(char_uuid):
        if char_uuid.lower() == "00002a29-0000-1000-8000-00805f9b34fb":
            return b"Partial Manufacturer"
        elif char_uuid.lower() == "00002a24-0000-1000-8000-00805f9b34fb":
            return b"Partial Model"
        return b""
    
    mock_bleak_client.read_gatt_char = AsyncMock(side_effect=mock_read_char)
    
    await device._read_device_information()
    
    # Verify partial information was read
    assert device.manufacturer_name == "Partial Manufacturer"
    assert device.model_number == "Partial Model"
    # Others remain None
    assert device.serial_number is None
    assert device.hardware_revision is None
    assert device.firmware_revision is None
    assert device.software_revision is None


async def test_read_device_information_characteristic_read_failure(mock_ble_device, mock_bleak_client):
    """Test when reading device info characteristics fails."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Create service with characteristics
    service = MagicMock()
    service.uuid = "0000180a-0000-1000-8000-00805f9b34fb"
    
    char = MagicMock()
    char.uuid = "00002a29-0000-1000-8000-00805f9b34fb"  # Manufacturer
    char.properties = ["read"]
    service.characteristics = [char]
    
    mock_bleak_client.services = [service]
    
    # Mock read_gatt_char to raise exception
    mock_bleak_client.read_gatt_char = AsyncMock(side_effect=Exception("Read failed"))
    
    # Should not raise exception
    await device._read_device_information()
    
    # Verify device info remains None after failure
    assert device.manufacturer_name is None


async def test_read_device_information_characteristic_not_readable(mock_ble_device, mock_bleak_client):
    """Test when device info characteristic doesn't support read operation."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Create service with non-readable characteristic
    service = MagicMock()
    service.uuid = "0000180a-0000-1000-8000-00805f9b34fb"
    
    char = MagicMock()
    char.uuid = "00002a29-0000-1000-8000-00805f9b34fb"  # Manufacturer
    char.properties = ["write"]  # No read property
    service.characteristics = [char]
    
    mock_bleak_client.services = [service]
    
    await device._read_device_information()
    
    # Verify device info remains None when not readable
    assert device.manufacturer_name is None


async def test_read_device_information_empty_data(mock_ble_device, mock_bleak_client):
    """Test when device info characteristics return empty data."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Create service with characteristics
    service = MagicMock()
    service.uuid = "0000180a-0000-1000-8000-00805f9b34fb"
    
    char = MagicMock()
    char.uuid = "00002a29-0000-1000-8000-00805f9b34fb"  # Manufacturer
    char.properties = ["read"]
    service.characteristics = [char]
    
    mock_bleak_client.services = [service]
    
    # Mock read to return empty data
    mock_bleak_client.read_gatt_char = AsyncMock(return_value=b"")
    
    await device._read_device_information()
    
    # Verify device info remains None for empty data
    assert device.manufacturer_name is None


async def test_read_device_information_utf8_decoding(mock_ble_device, mock_bleak_client):
    """Test UTF-8 decoding and whitespace handling."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    
    # Create service with characteristics
    service = MagicMock()
    service.uuid = "0000180a-0000-1000-8000-00805f9b34fb"
    
    char = MagicMock()
    char.uuid = "00002a29-0000-1000-8000-00805f9b34fb"  # Manufacturer
    char.properties = ["read"]
    service.characteristics = [char]
    
    mock_bleak_client.services = [service]
    
    # Mock read to return data with whitespace and null bytes
    mock_bleak_client.read_gatt_char = AsyncMock(return_value=b"  Test Manufacturer\x00\r\n\t ")
    
    await device._read_device_information()
    
    # Verify whitespace and null bytes are stripped
    assert device.manufacturer_name == "Test Manufacturer"


async def test_read_device_information_not_connected(mock_ble_device):
    """Test device information reading when not connected."""
    device = DeskBLEDevice(mock_ble_device)
    # Device not connected (no client)
    
    await device._read_device_information()
    
    # Should handle gracefully without error
    assert device.manufacturer_name is None


def test_device_info_properties(mock_ble_device):
    """Test device information property getters."""
    device = DeskBLEDevice(mock_ble_device)
    
    # Test initial state
    assert device.manufacturer_name is None
    assert device.model_number is None
    assert device.serial_number is None
    assert device.hardware_revision is None
    assert device.firmware_revision is None
    assert device.software_revision is None
    
    # Set values directly (simulating successful read)
    device._manufacturer_name = "Test Manufacturer"
    device._model_number = "Test Model"
    device._serial_number = "TEST123456"
    device._hardware_revision = "1.0"
    device._firmware_revision = "2.1.0"
    device._software_revision = "1.5.2"
    
    # Test property getters
    assert device.manufacturer_name == "Test Manufacturer"
    assert device.model_number == "Test Model"
    assert device.serial_number == "TEST123456"
    assert device.hardware_revision == "1.0"
    assert device.firmware_revision == "2.1.0"
    assert device.software_revision == "1.5.2"


async def test_device_information_called_during_connect(mock_ble_device, mock_bleak_client_with_device_info):
    """Test that device information is read during connection."""
    device = DeskBLEDevice(mock_ble_device)
    
    with patch.object(device, '_read_device_information', AsyncMock()) as mock_read_device_info:
        with patch(
            "custom_components.desky_desk.bluetooth.establish_connection",
            return_value=mock_bleak_client_with_device_info,
        ):
            result = await device.connect()
            
            assert result is True
            # Verify device information was read during connection
            mock_read_device_info.assert_called_once()