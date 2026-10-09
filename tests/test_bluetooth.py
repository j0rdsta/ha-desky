"""Test the Desky Desk Bluetooth communication."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache
import pytest

from custom_components.desky_desk.bluetooth import (
    COMMAND_EXPIRY_SECONDS,
    RECENT_NOTIFICATION_HEADERS,
    DeskBLEDevice,
    DeskCommandError,
    DeskNotConnectedError,
    _Movement,
)
from custom_components.desky_desk.const import (
    BRIGHTNESS_RESPONSE_HEADER,
    COMMAND_GET_LIGHTING,
    COMMAND_GET_LIMITS,
    COMMAND_GET_STATUS,
    COMMAND_GET_VIBRATION,
    COMMAND_HANDSHAKE,
    COMMAND_MEMORY_1,
    COMMAND_MEMORY_2,
    COMMAND_MEMORY_3,
    COMMAND_MEMORY_4,
    COMMAND_MOVE_DOWN,
    COMMAND_MOVE_UP,
    COMMAND_STOP,
    LIGHT_COLOR_RESPONSE_HEADER,
    LIGHTING_RESPONSE_HEADER,
    LIMIT_LOWER_RESPONSE_HEADER,
    LIMIT_STATUS_RESPONSE_HEADER,
    LIMIT_UPPER_RESPONSE_HEADER,
    LOCK_STATUS_RESPONSE_HEADER,
    MAX_HEIGHT,
    MIN_HEIGHT,
    NOTIFY_CHARACTERISTIC_UUID,
    SENSITIVITY_RESPONSE_HEADER,
    VIBRATION_RESPONSE_HEADER,
    WRITE_CHARACTERISTIC_UUID,
    HeightLimit,
)

from . import desk_response


def _status_frame(height_cm: float) -> bytearray:
    """Build a real status frame (f2 f2 01 03 HH LL 07 CS 7e) for a height in cm."""
    raw = round(height_cm * 10)
    body = [0x01, 0x03, raw >> 8, raw & 0xFF, 0x07]
    return bytearray([0xF2, 0xF2, *body, sum(body) & 0xFF, 0x7E])


def _replay(device, mock_time, readings) -> None:
    """Feed (time, height_cm) readings to the device as status frames."""
    for when, height in readings:
        mock_time.return_value = when
        device._handle_notification(None, _status_frame(height))


def _collision_starts(callback: MagicMock) -> int:
    """Count how often the collision flag went from off to on in the callbacks."""
    flags = [call_args.args[1] for call_args in callback.call_args_list]
    return sum(
        1
        for before, after in zip([False, *flags], flags, strict=False)
        if after and not before
    )


def _started_movement(
    device: DeskBLEDevice,
    kind: str,
    direction: str | None = None,
    *,
    start_height: float,
    height: float,
    moved_until: float,
    target_height: float | None = None,
) -> None:
    """Put the device mid-movement: started at time 0 and last changed at moved_until."""
    device._height_cm = height
    device._movement = _Movement(
        kind=kind,
        direction=direction,
        target_height=target_height,
        command_time=0.0,
        command_height=start_height,
        started=True,
        start_time=0.0,
        last_change_time=moved_until,
        last_height=height,
        furthest_height=height,
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


@patch("time.time")
async def test_desk_device_properties(mock_time, mock_ble_device, mock_bleak_client):
    """Test DeskBLEDevice properties."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._collision_detected = True

    _replay(device, mock_time, [(0.0, 84.0)])
    await device.move_up()
    _replay(device, mock_time, [(0.5, 85.0)])

    assert device.height_cm == 85.0
    assert device.collision_detected is True
    assert device.is_moving is True
    assert device.movement_direction == "up"


def test_register_callbacks(mock_ble_device):
    """Test callback registration."""
    device = DeskBLEDevice(mock_ble_device)

    notification_callback = MagicMock()
    disconnect_callback = MagicMock()

    device.register_notification_callback(notification_callback)
    device.register_disconnect_callback(disconnect_callback)

    assert notification_callback in device._notification_callbacks
    assert disconnect_callback in device._disconnect_callbacks


async def test_connect_success(
    mock_ble_device, mock_establish_connection, mock_bleak_client
):
    """Test successful connection."""
    device = DeskBLEDevice(mock_ble_device)

    result = await device.connect()

    assert result is True
    assert device._client == mock_bleak_client
    assert device.is_connected is True

    # bleak-retry-connector handles adapters and proxies alike, with no
    # timeouts of our own
    mock_establish_connection.assert_called_once_with(
        BleakClientWithServiceCache,
        mock_ble_device,
        "Desky",
        disconnected_callback=device._handle_disconnect,
        max_attempts=3,
        ble_device_callback=device._get_ble_device,
    )

    mock_bleak_client.start_notify.assert_called_once_with(
        NOTIFY_CHARACTERISTIC_UUID, device._handle_notification
    )
    # The client mock is specced to Bleak, which has no get_services() any more
    assert not hasattr(mock_bleak_client, "get_services")

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
        side_effect=TimeoutError(),
    ):
        result = await device.connect()

        assert result is False
        assert device._client is None


async def test_connection_retries_use_the_latest_ble_device(mock_ble_device):
    """Test retries within a connection attempt use the most recently seen device."""
    device = DeskBLEDevice(mock_ble_device)
    assert device._get_ble_device() is mock_ble_device

    # The desk is now heard through another proxy
    newer = MagicMock(address=mock_ble_device.address)
    device.set_ble_device(newer)

    assert device._get_ble_device() is newer


async def test_connection_lifecycle_logs_only_at_debug(
    mock_ble_device, mock_establish_connection, mock_bleak_client, caplog
):
    """Test connecting, dropping and failing to reconnect log nothing above debug.

    The coordinator logs an outage and the recovery once each, so the device
    must not add a line for every attempt.
    """
    caplog.set_level("DEBUG", logger="custom_components.desky_desk.bluetooth")
    device = DeskBLEDevice(mock_ble_device)

    # A desk without the Device Information Service, connected and dropped
    assert await device.connect()
    device._handle_disconnect(mock_bleak_client)
    mock_establish_connection.side_effect = TimeoutError()
    assert not await device.connect()

    assert [
        record.getMessage() for record in caplog.records if record.levelname != "DEBUG"
    ] == []
    assert "Failed to connect to desk at AA:BB:CC:DD:EE:FF" in caplog.text


def _bleak_client() -> MagicMock:
    """Return another connected Bleak client mock, for a second connection."""
    client = MagicMock(spec=BleakClient)
    client.is_connected = True
    client.disconnect = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()
    client.services = []
    return client


async def test_connect_waits_on_no_fixed_delays(
    mock_ble_device, mock_establish_connection, mock_bleak_client
):
    """Test connecting sends its queries back to back, without sleeping."""
    device = DeskBLEDevice(mock_ble_device)

    with patch(
        "custom_components.desky_desk.bluetooth.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        assert await device.connect() is True

    mock_sleep.assert_not_awaited()
    # Handshake, status and the six capability queries
    assert mock_bleak_client.write_gatt_char.await_count == 8


async def test_capability_query_failure_is_not_an_unsupported_feature(
    mock_ble_device, mock_establish_connection, mock_bleak_client, caplog
):
    """Test a desk that stops answering during the queries fails the connect.

    A failed write means the connection is gone, not that the desk lacks the
    feature, so nothing is logged as unsupported.
    """
    caplog.set_level("DEBUG", logger="custom_components.desky_desk.bluetooth")
    device = DeskBLEDevice(mock_ble_device)

    async def _write(_uuid: str, command: bytes) -> None:
        if command == COMMAND_GET_VIBRATION:
            mock_bleak_client.is_connected = False
            raise BleakError("not connected")

    mock_bleak_client.write_gatt_char.side_effect = _write

    assert await device.connect() is False

    mock_bleak_client.disconnect.assert_awaited_once()
    assert device._client is None
    assert "not supported" not in caplog.text
    assert "Failed to connect to desk at AA:BB:CC:DD:EE:FF" in caplog.text


async def test_connect_releases_the_link_when_notifications_fail(
    mock_ble_device, mock_establish_connection, mock_bleak_client
):
    """Test a link whose notifications cannot be started is closed again."""
    device = DeskBLEDevice(mock_ble_device)
    mock_bleak_client.start_notify.side_effect = BleakError("notify failed")

    assert await device.connect() is False

    mock_bleak_client.disconnect.assert_awaited_once()
    assert device._client is None
    assert device.is_connected is False


@pytest.mark.parametrize(
    "failing_command",
    [COMMAND_HANDSHAKE, COMMAND_GET_STATUS, COMMAND_GET_LIGHTING, COMMAND_GET_LIMITS],
    ids=["handshake", "status", "first capability query", "last capability query"],
)
async def test_connect_releases_the_link_when_a_setup_write_fails(
    mock_ble_device, mock_establish_connection, mock_bleak_client, failing_command
):
    """Test a write that fails while setting up closes the new link."""
    device = DeskBLEDevice(mock_ble_device)

    async def _write(_uuid: str, command: bytes) -> None:
        if command == failing_command:
            raise BleakError("write failed")

    mock_bleak_client.write_gatt_char.side_effect = _write

    assert await device.connect() is False

    mock_bleak_client.disconnect.assert_awaited_once()
    assert device._client is None
    assert device.is_connected is False


async def test_failed_setup_reports_one_disconnect(
    mock_ble_device, mock_establish_connection, mock_bleak_client
):
    """Test a failed setup reports the desk disconnected once and resets its state.

    Closing the link fires its own disconnect callback, which must not report
    the drop a second time.
    """
    device = DeskBLEDevice(mock_ble_device)
    callback = MagicMock()
    device.register_disconnect_callback(callback)

    async def _write(_uuid: str, command: bytes) -> None:
        if command == COMMAND_GET_STATUS:
            # The desk reports inches, then the link fails
            device._handle_notification(None, bytearray.fromhex("f2f20e0101107e"))
            raise BleakError("write failed")

    async def _disconnect() -> None:
        mock_establish_connection.call_args.kwargs["disconnected_callback"](
            mock_bleak_client
        )

    mock_bleak_client.write_gatt_char.side_effect = _write
    mock_bleak_client.disconnect.side_effect = _disconnect

    assert await device.connect() is False

    callback.assert_called_once_with()
    assert device.unit_preference is None
    mock_bleak_client.disconnect.assert_awaited_once()


async def test_drop_during_setup_is_reported_once(
    mock_ble_device, mock_establish_connection, mock_bleak_client
):
    """Test a desk that drops while setting up is reported once and released."""
    device = DeskBLEDevice(mock_ble_device)
    callback = MagicMock()
    device.register_disconnect_callback(callback)

    async def _write(_uuid: str, command: bytes) -> None:
        if command == COMMAND_GET_STATUS:
            mock_bleak_client.is_connected = False
            mock_establish_connection.call_args.kwargs["disconnected_callback"](
                mock_bleak_client
            )
            raise BleakError("disconnected")

    mock_bleak_client.write_gatt_char.side_effect = _write

    assert await device.connect() is False

    callback.assert_called_once_with()
    mock_bleak_client.disconnect.assert_awaited_once()
    assert device._client is None


async def test_drop_after_the_last_query_fails_the_connect(
    mock_ble_device, mock_establish_connection, mock_bleak_client
):
    """Test a desk that drops after the last write, during the reads, fails the connect."""
    device = DeskBLEDevice(mock_ble_device)
    callback = MagicMock()
    device.register_disconnect_callback(callback)

    async def _write(_uuid: str, command: bytes) -> None:
        if command == COMMAND_GET_LIMITS:
            # The write goes out, then the link drops
            mock_bleak_client.is_connected = False
            mock_establish_connection.call_args.kwargs["disconnected_callback"](
                mock_bleak_client
            )

    mock_bleak_client.write_gatt_char.side_effect = _write

    assert await device.connect() is False

    callback.assert_called_once_with()
    mock_bleak_client.disconnect.assert_awaited_once()
    assert device._client is None


async def test_release_survives_a_failing_disconnect(
    mock_ble_device, mock_establish_connection, mock_bleak_client, caplog
):
    """Test a link that errors while closing still fails the connect quietly."""
    caplog.set_level("DEBUG", logger="custom_components.desky_desk.bluetooth")
    device = DeskBLEDevice(mock_ble_device)
    mock_bleak_client.start_notify.side_effect = BleakError("notify failed")
    mock_bleak_client.disconnect.side_effect = BleakError("already gone")

    assert await device.connect() is False

    assert device._client is None
    assert "Error closing the connection to desk at AA:BB:CC:DD:EE:FF" in caplog.text
    assert [r.getMessage() for r in caplog.records if r.levelname != "DEBUG"] == []


async def test_disconnect_from_an_earlier_link_is_ignored(
    mock_ble_device, mock_bleak_client
):
    """Test the old link of a failed attempt cannot drop a newer connection."""
    device = DeskBLEDevice(mock_ble_device)
    callback = MagicMock()
    device.register_disconnect_callback(callback)
    old_client = _bleak_client()
    old_client.start_notify.side_effect = BleakError("notify failed")

    with patch(
        "custom_components.desky_desk.bluetooth.establish_connection",
        side_effect=[old_client, mock_bleak_client],
    ) as mock_establish:
        assert await device.connect() is False
        assert await device.connect() is True
    callback.reset_mock()

    # The old link's drop arrives late, while the new connection works
    mock_establish.call_args.kwargs["disconnected_callback"](old_client)

    assert device._client is mock_bleak_client
    assert device.is_connected is True
    callback.assert_not_called()


@pytest.mark.parametrize(
    "callback_on_close", [True, False], ids=["callback on close", "no callback"]
)
async def test_release_closes_then_reports_the_drop_once(
    mock_ble_device, mock_establish_connection, mock_bleak_client, callback_on_close
):
    """Test a failed setup closes the link before reporting it, and reports once.

    BlueZ fires the link's own disconnect callback while closing it; a proxy
    may not fire it until later, or at all.
    """
    device = DeskBLEDevice(mock_ble_device)
    callback = MagicMock()
    device.register_disconnect_callback(callback)
    mock_bleak_client.start_notify.side_effect = BleakError("notify failed")
    reports_before_close: list[int] = []

    async def _disconnect() -> None:
        reports_before_close.append(callback.call_count)
        if callback_on_close:
            mock_establish_connection.call_args.kwargs["disconnected_callback"](
                mock_bleak_client
            )

    mock_bleak_client.disconnect.side_effect = _disconnect

    assert await device.connect() is False

    assert reports_before_close == [0]
    callback.assert_called_once_with()
    mock_bleak_client.disconnect.assert_awaited_once()
    assert device._client is None


async def test_cancelled_release_is_closed_on_disconnect(
    mock_ble_device, mock_establish_connection, mock_bleak_client
):
    """Test a connect cancelled while closing its failed link, as on unload.

    The link stays referenced, so the disconnect() that unload runs closes it.
    """
    device = DeskBLEDevice(mock_ble_device)
    mock_bleak_client.start_notify.side_effect = BleakError("notify failed")
    closing = asyncio.Event()

    async def _disconnect() -> None:
        if mock_bleak_client.disconnect.await_count == 1:
            closing.set()
            await asyncio.Event().wait()  # the proxy never answers

    mock_bleak_client.disconnect.side_effect = _disconnect

    task = asyncio.create_task(device.connect())
    await closing.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await device.disconnect()

    assert mock_bleak_client.disconnect.await_count == 2
    assert device._client is None


async def test_cancelled_connect_is_released_on_disconnect(
    mock_ble_device, mock_establish_connection, mock_bleak_client
):
    """Test a connect cancelled mid-setup, as on unload, leaves its link reachable."""
    device = DeskBLEDevice(mock_ble_device)
    writing = asyncio.Event()

    async def _write(_uuid: str, command: bytes) -> None:
        writing.set()
        await asyncio.Event().wait()  # the desk never answers

    mock_bleak_client.write_gatt_char.side_effect = _write

    task = asyncio.create_task(device.connect())
    await writing.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await device.disconnect()

    mock_bleak_client.disconnect.assert_awaited_once()
    assert device._client is None


async def test_disconnect_resets_link_state_without_a_callback(
    mock_ble_device, mock_bleak_client, mock_establish_connection
) -> None:
    """A proxy may report the drop only after disconnect() returns; state is reset anyway."""
    device = DeskBLEDevice(mock_ble_device)
    await device.connect()
    device._unit_preference = "in"
    device._touch_mode = 1
    device._handle_notification(None, bytearray.fromhex("f2f21d0102207e"))
    # The mocked client.disconnect() does not call the disconnect callback

    await device.disconnect()

    assert device._client is None
    assert device._unit_preference is None
    assert device._effective_unit is None
    assert device._touch_mode is None
    assert device.sensitivity_level is None
    assert device.collision_detected is False


async def test_disconnect(mock_ble_device, mock_bleak_client):
    """Test disconnection."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    await device.disconnect()

    # Closing the link ends the subscription; no extra write to a quiet desk
    mock_bleak_client.stop_notify.assert_not_called()
    mock_bleak_client.disconnect.assert_awaited_once()
    assert device._client is None


async def test_send_command_success(mock_ble_device, mock_bleak_client):
    """Test successful command sending."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    await device._send_command(COMMAND_GET_STATUS)

    mock_bleak_client.write_gatt_char.assert_called_once_with(
        WRITE_CHARACTERISTIC_UUID, COMMAND_GET_STATUS
    )


async def test_send_command_not_connected(mock_ble_device):
    """Test a command to a disconnected desk raises instead of reporting success."""
    device = DeskBLEDevice(mock_ble_device)

    with pytest.raises(DeskNotConnectedError):
        await device._send_command(COMMAND_GET_STATUS)


async def test_send_command_failure(mock_ble_device, mock_bleak_client):
    """Test a failed write raises with the cause attached."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    cause = Exception("Write failed")
    mock_bleak_client.write_gatt_char.side_effect = cause

    with pytest.raises(DeskCommandError, match="Write failed") as err:
        await device._send_command(COMMAND_GET_STATUS)

    assert err.value.__cause__ is cause


async def test_movement_commands(mock_ble_device, mock_bleak_client):
    """Test movement commands."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    # Test move up - the movement only starts once the desk responds
    await device.move_up()
    assert device.is_moving is False
    assert device.movement_direction == "up"
    assert device._movement.kind == "continuous"
    mock_bleak_client.write_gatt_char.assert_called_with(
        WRITE_CHARACTERISTIC_UUID, COMMAND_MOVE_UP
    )

    # Test move down
    await device.move_down()
    assert device.is_moving is False
    assert device.movement_direction == "down"
    assert device._movement.kind == "continuous"
    mock_bleak_client.write_gatt_char.assert_called_with(
        WRITE_CHARACTERISTIC_UUID, COMMAND_MOVE_DOWN
    )

    # Test stop
    await device.stop()
    assert device.is_moving is False
    assert device.movement_direction is None
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
        assert device.is_moving is False  # Not moving until the desk responds
        assert device._movement.kind == "preset"
        mock_bleak_client.write_gatt_char.assert_called_with(
            WRITE_CHARACTERISTIC_UUID, command
        )


async def test_invalid_preset(mock_ble_device, mock_bleak_client):
    """Test invalid preset number."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    with pytest.raises(ValueError, match="Invalid preset number: 5"):
        await device.move_to_preset(5)

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


def test_recent_notification_headers(mock_ble_device):
    """Test the device keeps the headers of recent frames, not their values."""
    device = DeskBLEDevice(mock_ble_device)
    assert device.recent_notification_headers == []

    device._handle_notification(None, _status_frame(85.0))
    device._handle_notification(None, bytearray([0xF2, 0xF2]))
    device._handle_notification(None, bytearray([0xFF, 0xFF, 0x00, 0x00, 0x52, 0x03]))

    # Unknown and truncated frames are kept too: they are what a bug report needs
    assert device.recent_notification_headers == [
        {"header": "f2 f2 01 03", "count": 1},
        {"header": "f2 f2", "count": 1},
        {"header": "ff ff 00 00", "count": 1},
    ]


def test_recent_notification_headers_collapse_repeats(mock_ble_device):
    """Test a run of identical headers is kept once, with how often it came."""
    device = DeskBLEDevice(mock_ble_device)

    # An idle desk streams status frames; a settings reply interrupts the run
    for _ in range(81):
        device._handle_notification(None, _status_frame(85.0))
    device._handle_notification(None, bytearray([0xF2, 0xF2, 0x0E, 0x01, 0x00]))
    for _ in range(3):
        device._handle_notification(None, _status_frame(85.0))

    assert device.recent_notification_headers == [
        {"header": "f2 f2 01 03", "count": 81},
        {"header": "f2 f2 0e 01", "count": 1},
        {"header": "f2 f2 01 03", "count": 3},
    ]


def test_recent_notification_headers_are_capped(mock_ble_device):
    """Test only the most recent runs of notification headers are kept."""
    device = DeskBLEDevice(mock_ble_device)

    for value in range(RECENT_NOTIFICATION_HEADERS + 5):
        for _ in range(2):
            device._handle_notification(
                None, bytearray([0xF2, 0xF2, value, 0x01, 0x00])
            )

    headers = device.recent_notification_headers
    assert len(headers) == RECENT_NOTIFICATION_HEADERS == 20
    assert headers[0] == {"header": "f2 f2 05 01", "count": 2}
    assert headers[-1] == {"header": "f2 f2 18 01", "count": 2}


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
    data2 = bytearray(
        [0xF2, 0xF2, 0x01, 0x03, 0x03, 0xF4]
    )  # 101.2 cm (1012 = 0x03F4 big-endian)
    device._handle_notification(0, data2)
    assert device.height_cm == 101.2

    # Verify callbacks were called for both
    assert callback.call_count == 2
    callback.assert_has_calls([call(85.0, False, False), call(101.2, False, False)])


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


def test_vibration_intensity_reply_is_unrecognised(mock_ble_device):
    """Test a vibration intensity reply, which the desk is never asked for, is ignored."""
    device = DeskBLEDevice(mock_ble_device)
    callback = MagicMock()
    device.register_notification_callback(callback)

    device._handle_notification(
        0, bytearray([0xF2, 0xF2, 0xA4, 0x01, 0x32, 0xD7, 0x7E])
    )

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

    data_status = bytearray(
        [0xF2, 0xF2, 0x01, 0x03, 0x03, 0xE8]
    )  # 100.0 cm (1000 = 0x03E8 big-endian)
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
    _started_movement(
        device, "continuous", "up", start_height=80.0, height=82.0, moved_until=1.0
    )
    device._collision_detected = True

    callback = MagicMock()
    device.register_disconnect_callback(callback)

    device._handle_disconnect(mock_bleak_client)

    assert device._client is None
    assert device.is_moving is False
    assert device.movement_direction is None
    assert device.collision_detected is False
    callback.assert_called_once()


async def test_move_to_height_success(mock_ble_device, mock_bleak_client):
    """Test move_to_height command."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._height_cm = 70.0  # Current height

    # Test moving to 85.0 cm (850 mm) - up direction
    await device.move_to_height(85.0)

    assert device.is_moving is False  # Not moving until the desk responds
    assert device.movement_direction == "up"
    assert device._movement.kind == "targeted"
    assert device._movement.target_height == 85.0

    # Calculate expected command
    # 850 mm = 0x0352, so high=0x03, low=0x52
    # checksum = (0x1B + 0x02 + 0x03 + 0x52) & 0xFF = 0x72
    expected_command = bytes([0xF1, 0xF1, 0x1B, 0x02, 0x03, 0x52, 0x72, 0x7E])

    # The handshake wakes the desk first
    assert mock_bleak_client.write_gatt_char.call_args_list == [
        call(WRITE_CHARACTERISTIC_UUID, COMMAND_HANDSHAKE),
        call(WRITE_CHARACTERISTIC_UUID, expected_command),
    ]


async def test_move_to_height_rounds_to_mm(mock_ble_device, mock_bleak_client):
    """Test the target is rounded to the nearest mm, not truncated."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._height_cm = 70.0

    await device.move_to_height(85.27)

    # 853 mm = 0x0355; checksum = (0x1B + 0x02 + 0x03 + 0x55) & 0xFF = 0x75
    expected_command = bytes([0xF1, 0xF1, 0x1B, 0x02, 0x03, 0x55, 0x75, 0x7E])
    assert mock_bleak_client.write_gatt_char.call_args_list[-1] == call(
        WRITE_CHARACTERISTIC_UUID, expected_command
    )


async def test_move_to_height_out_of_range(mock_ble_device, mock_bleak_client):
    """Test move_to_height with out of range values."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    # Test below minimum
    with pytest.raises(ValueError, match="out of range"):
        await device.move_to_height(MIN_HEIGHT - 10)
    assert not device.is_moving

    # Test above maximum
    with pytest.raises(ValueError, match="out of range"):
        await device.move_to_height(MAX_HEIGHT + 10)
    assert not device.is_moving

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
        call(WRITE_CHARACTERISTIC_UUID, COMMAND_HANDSHAKE),
        call(WRITE_CHARACTERISTIC_UUID, expected_min),
        call(WRITE_CHARACTERISTIC_UUID, COMMAND_HANDSHAKE),
        call(WRITE_CHARACTERISTIC_UUID, expected_max),
    ]
    mock_bleak_client.write_gatt_char.assert_has_calls(expected_calls)


@patch("time.time")
def test_auto_stop_detection(mock_time, mock_ble_device):
    """Test auto-stop detection when height stops changing."""
    device = DeskBLEDevice(mock_ble_device)
    _started_movement(
        device, "continuous", "up", start_height=84.9, height=85.0, moved_until=1.5
    )
    mock_time.return_value = 1.5

    callback = MagicMock()
    device.register_notification_callback(callback)

    # First notification with same height
    data = bytearray([0x98, 0x98, 0x00, 0x00, 0x52, 0x03])  # 85.0 cm
    device._handle_notification(0, data)
    assert device.is_moving is True  # Still moving
    assert device._movement.unchanged_readings == 1
    assert device._collision_detected is False  # Not yet

    # Second notification with same height
    device._handle_notification(0, data)
    assert device.is_moving is True  # Still moving
    assert device._movement.unchanged_readings == 2
    assert device._collision_detected is False  # Not yet

    # Third notification: auto-stop, and 0.1 cm in 1.5 s is a collision
    device._handle_notification(0, data)
    assert device.is_moving is False  # Stopped
    assert device.movement_direction is None
    assert device._movement is None  # The movement is forgotten
    assert device._collision_detected is True  # Collision detected!

    # Verify callbacks were called
    assert callback.call_count == 3
    # Verify last callback includes collision state
    callback.assert_called_with(85.0, True, False)


def test_auto_stop_detection_reset_on_movement(mock_ble_device):
    """Test auto-stop detection resets when height changes."""
    device = DeskBLEDevice(mock_ble_device)
    _started_movement(
        device, "continuous", "up", start_height=80.0, height=85.0, moved_until=1.0
    )
    device._movement.unchanged_readings = 2  # Almost at stop threshold

    # Notification with different height - should reset counter
    data = bytearray([0x98, 0x98, 0x00, 0x00, 0x5C, 0x03])  # 86.0 cm
    device._handle_notification(0, data)

    assert device.is_moving is True  # Still moving
    assert device._movement.unchanged_readings == 0  # Reset
    assert device._movement.last_height == 86.0  # Updated


async def test_move_to_height_direction_detection(mock_ble_device, mock_bleak_client):
    """Test move_to_height sets correct movement direction."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._height_cm = 85.0  # Current height

    # Test moving down
    await device.move_to_height(70.0)
    assert device.movement_direction == "down"

    # Test moving up
    device._height_cm = 70.0
    await device.move_to_height(90.0)
    assert device.movement_direction == "up"

    # Test same height (no movement)
    device._height_cm = 80.0
    await device.move_to_height(80.0)
    assert device.movement_direction is None
    # Nothing is sent for a move to where the desk already is
    assert mock_bleak_client.write_gatt_char.call_count == 4


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
    assert device.is_moving is False

    # Cancel the auto-clear task to clean up
    if device._auto_clear_task:
        device._auto_clear_task.cancel()
        try:
            await device._auto_clear_task
        except asyncio.CancelledError:
            pass


@patch("time.time")
def test_no_collision_for_short_movement(mock_time, mock_ble_device):
    """Test no collision detected for movements shorter than 1 second."""
    device = DeskBLEDevice(mock_ble_device)
    _started_movement(
        device, "continuous", "up", start_height=84.9, height=85.0, moved_until=0.5
    )
    mock_time.return_value = 0.5  # Only 0.5 seconds after start

    callback = MagicMock()
    device.register_notification_callback(callback)

    # Three notifications with same height
    data = bytearray([0x98, 0x98, 0x00, 0x00, 0x52, 0x03])  # 85.0 cm

    device._handle_notification(0, data)
    device._handle_notification(0, data)
    device._handle_notification(0, data)

    # Should stop but NOT detect collision (movement too short)
    assert device.is_moving is False  # Stopped
    assert device.movement_direction is None
    assert device._collision_detected is False  # No collision for short movement

    # Verify last callback shows no collision
    callback.assert_called_with(85.0, False, False)


@patch("time.time")
async def test_bounce_back_detection_down(
    mock_time, mock_ble_device, mock_bleak_client
):
    """Test bounce-back detection when desk moves down then bounces up."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    callback = MagicMock()
    device.register_notification_callback(callback)

    _replay(device, mock_time, [(0.0, 75.0)])
    await device.move_down()

    heights = [75.0, 74.0, 73.0, 72.0, 71.0, 70.5, 71.0, 71.5, 72.0]

    for i, height in enumerate(heights):
        _replay(device, mock_time, [(0.2 * (i + 1), height)])

        # The collision is reported once the reversal exceeds the jitter band
        if device.collision_detected:
            assert i >= 6  # after hitting 70.5 and starting to bounce
            assert device.is_moving is False
            break

    # Verify collision was detected and the movement ended
    try:
        assert device.collision_detected is True
        assert device._movement is None
    finally:
        await device.disconnect()


@patch("time.time")
async def test_bounce_back_detection_up(mock_time, mock_ble_device, mock_bleak_client):
    """Test bounce-back detection when desk moves up then bounces down."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    callback = MagicMock()
    device.register_notification_callback(callback)

    _replay(device, mock_time, [(0.0, 100.0)])
    await device.move_up()

    heights = [100.0, 101.0, 102.0, 103.0, 104.0, 104.5, 104.0, 103.5, 103.0]

    for i, height in enumerate(heights):
        _replay(device, mock_time, [(0.2 * (i + 1), height)])

        # The collision is reported once the reversal exceeds the jitter band
        if device.collision_detected:
            assert i >= 6  # after hitting 104.5 and starting to bounce
            assert device.is_moving is False
            break

    # Verify collision was detected and the movement ended
    try:
        assert device.collision_detected is True
        assert device._movement is None
    finally:
        await device.disconnect()


@patch("time.time")
async def test_bounce_back_resets_on_new_movement(
    mock_time, mock_ble_device, mock_bleak_client
):
    """After a bounce the next command is a fresh movement; the collision persists."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    _replay(device, mock_time, [(0.0, 80.0)])
    await device.move_down()
    _replay(device, mock_time, [(0.2, 79.0), (0.4, 78.0), (0.6, 79.0)])
    assert device.collision_detected is True
    assert device._movement is None

    # Start new movement
    await device.move_up()

    try:
        assert device._movement.started is False
        assert device._movement.velocities == []
        assert device.collision_detected is True  # Collision persists
        assert device.movement_direction == "up"
    finally:
        await device.disconnect()


@patch("time.time")
async def test_no_bounce_for_normal_stop(mock_time, mock_ble_device, mock_bleak_client):
    """Test no bounce detected for normal stop (no direction reversal)."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    callback = MagicMock()
    device.register_notification_callback(callback)

    _replay(device, mock_time, [(0.0, 85.0)])
    await device.move_up()
    # Moving up for 1.5 s, then stopped
    _replay(
        device,
        mock_time,
        [(0.5, 86.0), (1.0, 87.0), (1.5, 88.0), (1.7, 88.0), (1.9, 88.0), (2.1, 88.0)],
    )

    # Should detect the stop, with no bounce and no collision
    assert device.is_moving is False
    assert device._movement is None
    assert device.collision_detected is False


@patch("time.time")
async def test_bounce_back_with_status_notification(
    mock_time, mock_ble_device, mock_bleak_client
):
    """Test bounce-back detection works with status notifications too."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    _replay(device, mock_time, [(0.0, 75.0)])
    await device.move_down()
    heights = [74.0, 73.0, 72.0, 71.0, 70.5, 71.0, 71.5]  # Bounce at end
    _replay(device, mock_time, [(0.2 * (i + 1), h) for i, h in enumerate(heights)])

    try:
        assert device.collision_detected is True
        assert device.is_moving is False
    finally:
        await device.disconnect()


async def test_movement_with_preset_no_direction(mock_ble_device, mock_bleak_client):
    """Test that preset movements don't set commanded direction initially."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._collision_detected = True  # Previous collision

    # Move to preset doesn't know direction initially
    await device.move_to_preset(1)

    assert device._collision_detected is True  # Collision persists through new movement
    assert device.is_moving is False  # Only True when actual movement detected
    assert device.movement_direction is None  # Unknown initially
    assert device._movement.direction is None  # Not set for presets
    assert device._movement.kind == "preset"  # Movement type should be set


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
    with patch(
        "custom_components.desky_desk.bluetooth.COLLISION_AUTO_CLEAR_SECONDS", 0.1
    ):
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


@patch("time.time")
async def test_collision_clears_after_successful_movement_from_collision_time(
    mock_time, mock_ble_device, mock_bleak_client
):
    """Test collision clears after 2 seconds of movement from collision detection time."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    _replay(device, mock_time, [(0.0, 80.0)])

    # Collision detected at t=1.0
    mock_time.return_value = 1.0
    device._set_collision_detected(True)
    assert device._collision_detected is True
    assert device._collision_time == 1.0

    # New movement command at t=1.5
    mock_time.return_value = 1.5
    await device.move_down()

    # First movement at t=2.5 (1.5 seconds after collision): still detected
    _replay(device, mock_time, [(2.5, 79.4)])
    assert device._collision_detected is True
    assert device.is_moving is True

    # Second movement at t=3.1 (2.1 seconds after collision): cleared
    _replay(device, mock_time, [(3.1, 78.8)])
    assert device._collision_detected is False


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
    with patch(
        "custom_components.desky_desk.bluetooth.COLLISION_AUTO_CLEAR_SECONDS", 0.05
    ):
        device._set_collision_detected(True)

        # Wait for auto-clear
        await asyncio.sleep(0.1)

        # Callback should have been called with collision cleared
        callback.assert_called()
        # Get the last call
        last_call = callback.call_args
        assert last_call[0] == (
            85.0,
            False,
            False,
        )  # height, collision=False, moving=False


@patch("time.time")
async def test_no_collision_when_reaching_target_height(
    mock_time, mock_ble_device, mock_bleak_client
):
    """Test that reaching target height does not trigger collision detection."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    # Targeted movement from 85.0 to 90.0 cm
    _replay(device, mock_time, [(0.0, 85.0)])
    await device.move_to_height(90.0)
    _replay(
        device,
        mock_time,
        [
            (0.5, 86.0),
            (1.0, 87.0),
            (1.5, 88.0),
            (2.0, 89.0),
            (2.5, 90.0),
            (2.7, 90.0),
            (2.9, 90.0),
            (3.1, 90.0),
        ],
    )

    # Should NOT detect collision - reached target
    assert device.is_moving is False
    assert device.collision_detected is False


@patch("time.time")
async def test_collision_when_stopping_away_from_target(
    mock_time, mock_ble_device, mock_bleak_client
):
    """Test that stopping away from target height triggers collision detection."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    # Targeted movement from 85.0 to 90.0 cm that stops at 87.0 cm
    _replay(device, mock_time, [(0.0, 85.0)])
    await device.move_to_height(90.0)
    _replay(
        device,
        mock_time,
        [(0.5, 86.0), (1.0, 86.5), (1.6, 87.0), (1.8, 87.0), (2.0, 87.0), (2.2, 87.0)],
    )

    # Should detect collision - stopped away from target
    try:
        assert device.is_moving is False
        assert device.collision_detected is True
    finally:
        await device.disconnect()


@patch("time.time")
def test_continuous_movement_collision_minimal_movement(mock_time, mock_ble_device):
    """Test that continuous movement detects collision for minimal distance moved."""
    device = DeskBLEDevice(mock_ble_device)
    _started_movement(
        device,
        "continuous",
        "up",
        start_height=87.0,
        height=87.2,
        moved_until=1.5,
    )
    mock_time.return_value = 1.5

    # Three unchanged notifications at the final height
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x68, 0x03]))

    # Should detect collision due to minimal movement (< 0.5cm)
    assert device.is_moving is False
    assert device.collision_detected is True


@patch("time.time")
def test_continuous_movement_no_collision_normal_movement(mock_time, mock_ble_device):
    """Test that continuous movement doesn't detect collision for normal distance and speed."""
    device = DeskBLEDevice(mock_ble_device)
    _started_movement(
        device,
        "continuous",
        "up",
        start_height=85.0,
        height=86.0,
        moved_until=1.7,
    )
    mock_time.return_value = 1.7

    # Three unchanged notifications at the final height
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x5C, 0x03]))

    # Should NOT detect collision - 1.0 cm in 1.7 s is a reasonable distance and speed
    assert device.is_moving is False
    assert device.collision_detected is False


@patch("time.time")
def test_continuous_movement_no_collision_short_duration(mock_time, mock_ble_device):
    """Test that very short continuous movements don't trigger collision (user releasing button)."""
    device = DeskBLEDevice(mock_ble_device)
    _started_movement(
        device,
        "continuous",
        "up",
        start_height=85.0,
        height=85.1,
        moved_until=0.3,
    )
    mock_time.return_value = 0.3

    # Three unchanged notifications at the final height
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x53, 0x03]))

    # Should NOT detect collision - too short duration (user released button)
    assert device.is_moving is False
    assert device.collision_detected is False


@patch("time.time")
def test_continuous_movement_collision_slow_speed(mock_time, mock_ble_device):
    """Test that continuous movement detects collision for abnormally slow speed."""
    device = DeskBLEDevice(mock_ble_device)
    _started_movement(
        device,
        "continuous",
        "up",
        start_height=85.0,
        height=85.4,
        moved_until=2.0,
    )
    mock_time.return_value = 2.0

    # Three unchanged notifications at the final height
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x56, 0x03]))

    # Should detect collision - 0.4 cm in 2.0 s is abnormally slow
    assert device.is_moving is False
    assert device.collision_detected is True


@patch("time.time")
async def test_preset_clears_previous_commanded_direction(
    mock_time, mock_ble_device, mock_bleak_client
):
    """Test that preset movements clear previous commanded direction to prevent false bounce detection."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    # A previous continuous movement up, then a preset
    _replay(device, mock_time, [(0.0, 77.0)])
    await device.move_up()
    await device.move_to_preset(1)

    # The preset has no commanded direction, so a descent is not a bounce
    assert device._movement.direction is None
    assert device._movement.kind == "preset"

    # The preset moves down from 77.0 to 72.0 cm over 2 seconds and stops
    _replay(
        device,
        mock_time,
        [
            (0.5, 76.0),
            (1.0, 75.0),
            (1.5, 74.0),
            (2.0, 73.0),
            (2.5, 72.0),
            (2.7, 72.0),
            (2.9, 72.0),
            (3.1, 72.0),
        ],
    )

    # Should NOT detect collision - normal preset completion with no bounce detection
    assert device.is_moving is False
    assert device.collision_detected is False


@patch("time.time")
def test_preset_movement_no_collision_normal_movement(mock_time, mock_ble_device):
    """Test that preset movement doesn't trigger collision for normal distance and speed."""
    device = DeskBLEDevice(mock_ble_device)
    _started_movement(
        device,
        "preset",
        start_height=85.0,
        height=90.0,
        moved_until=2.5,
    )
    mock_time.return_value = 2.5

    # Three unchanged notifications at the final height
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x84, 0x03]))

    # Should NOT detect collision - 5 cm in 2.5 s is a normal distance and speed
    assert device.is_moving is False
    assert device.collision_detected is False


@patch("time.time")
def test_preset_movement_collision_minimal_distance(mock_time, mock_ble_device):
    """Test that preset movement triggers collision for minimal movement distance."""
    device = DeskBLEDevice(mock_ble_device)
    _started_movement(
        device,
        "preset",
        start_height=87.0,
        height=87.3,
        moved_until=2.0,
    )
    mock_time.return_value = 2.0

    # Three unchanged notifications at the final height
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x69, 0x03]))

    # Should detect collision - minimal movement distance
    assert device.is_moving is False
    assert device.collision_detected is True


@patch("time.time")
def test_preset_movement_collision_slow_overall_speed(mock_time, mock_ble_device):
    """Test that preset movement triggers collision for abnormally slow overall speed."""
    device = DeskBLEDevice(mock_ble_device)
    _started_movement(
        device,
        "preset",
        start_height=85.0,
        height=85.2,
        moved_until=10.0,
    )
    mock_time.return_value = 10.0

    # Three unchanged notifications at the final height
    for _ in range(3):
        device._handle_notification(None, bytes([0x98, 0x98, 0x00, 0x00, 0x54, 0x03]))

    # Should detect collision - 0.2 cm in 10 s is very slow
    assert device.is_moving is False
    assert device.collision_detected is True


@patch("time.time")
async def test_velocity_tracking_reset_on_new_movement(
    mock_time, mock_ble_device, mock_bleak_client
):
    """Test that velocity tracking is reset when new movement starts."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    # A movement that has measured some velocities
    _replay(device, mock_time, [(0.0, 80.0)])
    await device.move_up()
    _replay(device, mock_time, [(0.5, 81.0), (1.0, 82.0), (1.5, 83.0)])
    assert device._movement.velocities

    # Start new movement
    await device.move_up()

    # Velocity data and progress belong to the old movement
    assert device._movement.velocities == []
    assert device._movement.started is False
    assert device._movement.command_height == 83.0


def test_average_velocity_calculation():
    """Test average velocity calculation."""
    movement = _Movement(
        kind="continuous",
        direction="up",
        target_height=None,
        command_time=0.0,
        command_height=80.0,
    )

    # Test with no velocities
    assert movement.average_velocity() == 0.0

    # Test with some velocities
    movement.velocities = [1.0, 2.0, 3.0]
    assert movement.average_velocity() == 2.0

    # Test with negative velocities (should still work)
    movement.velocities = [-1.0, 1.0, 2.0]
    assert abs(movement.average_velocity() - 0.667) < 0.001  # Close enough


async def test_move_commands_set_movement_type(mock_ble_device, mock_bleak_client):
    """Test that movement commands set the correct movement type."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    # Test move_up
    await device.move_up()
    assert device._movement.kind == "continuous"
    assert device._movement.target_height is None

    # Test move_down
    await device.move_down()
    assert device._movement.kind == "continuous"
    assert device._movement.target_height is None

    # Test move_to_height
    await device.move_to_height(90.0)
    assert device._movement.kind == "targeted"
    assert device._movement.target_height == 90.0

    # Test move_to_preset
    await device.move_to_preset(1)
    assert device._movement.kind == "preset"
    assert device._movement.target_height is None

    # Test stop forgets the movement
    await device.stop()
    assert device._movement is None


@patch("time.time")
async def test_no_collision_at_height_limits(
    mock_time, mock_ble_device, mock_bleak_client
):
    """Test that stopping near height limits doesn't trigger collision detection."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    # Test case 1: Try to reach maximum height (130cm) but stop at 125cm (physical limit)
    _replay(device, mock_time, [(0.0, 77.0)])
    await device.move_to_height(130.0)
    heights = [80.0, 90.0, 100.0, 110.0, 120.0, 125.0, 125.0, 125.0, 125.0]
    _replay(device, mock_time, [(i + 1.0, h) for i, h in enumerate(heights)])

    # Should not detect collision - hit maximum height limit
    assert device.is_moving is False  # Movement stopped
    assert device._collision_detected is False  # No collision detected

    # Test case 2: Try to reach minimum height (60cm) but stop at 63cm (physical limit)
    mock_time.return_value = 20.0
    await device.move_to_height(60.0)
    heights = [120.0, 110.0, 100.0, 90.0, 80.0, 70.0, 63.0, 63.0, 63.0, 63.0]
    _replay(device, mock_time, [(i + 21.0, h) for i, h in enumerate(heights)])

    # Should not detect collision - hit minimum height limit
    assert device.is_moving is False  # Movement stopped
    assert device._collision_detected is False  # No collision detected


@patch("time.time")
async def test_collision_detection_away_from_limits(
    mock_time, mock_ble_device, mock_bleak_client
):
    """Test that collision is still detected when stopping away from height limits."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    # Try to reach 120cm but stop at 85cm (far from limits - likely real collision)
    _replay(device, mock_time, [(0.0, 77.0)])
    await device.move_to_height(120.0)
    heights = [80.0, 83.0, 85.0, 85.0, 85.0, 85.0]
    _replay(device, mock_time, [(i + 1.0, h) for i, h in enumerate(heights)])

    # Should detect collision - stopped far from target and limits
    try:
        assert device.is_moving is False  # Movement stopped
        assert device._collision_detected is True  # Collision detected
    finally:
        await device.disconnect()


async def test_new_device_commands(mock_ble_device, mock_bleak_client):
    """Test new device control commands."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    # Test light color commands
    await device.set_light_color(2)  # Red
    expected_command = bytes([0xF1, 0xF1, 0xB4, 0x01, 0x02, 0xB7, 0x7E])
    mock_bleak_client.write_gatt_char.assert_called_with(
        WRITE_CHARACTERISTIC_UUID, expected_command
    )

    # Test invalid light color
    with pytest.raises(ValueError):
        await device.set_light_color(8)

    # Test brightness
    await device.set_brightness(75)
    expected_command = bytes([0xF1, 0xF1, 0xB6, 0x01, 0x4B, 0x02, 0x7E])  # 75 = 0x4B

    # Test lighting enabled
    await device.set_lighting(True)
    expected_command = bytes([0xF1, 0xF1, 0xB5, 0x01, 0x01, 0xB7, 0x7E])

    # Test vibration
    await device.set_vibration(False)
    expected_command = bytes([0xF1, 0xF1, 0xB3, 0x01, 0x00, 0xB4, 0x7E])

    # Test lock status
    await device.set_lock_status(True)
    expected_command = bytes([0xF1, 0xF1, 0xB2, 0x01, 0x01, 0xB4, 0x7E])

    # Test sensitivity level
    await device.set_sensitivity(2)  # Medium
    expected_command = bytes([0xF1, 0xF1, 0x1D, 0x01, 0x02, 0x20, 0x7E])

    # Test clear limits
    await device.clear_height_limits()
    expected_command = bytes([0xF1, 0xF1, 0x23, 0x00, 0x23, 0x7E])

    # Test touch mode
    await device.set_touch_mode(1)  # Press and hold
    expected_command = bytes([0xF1, 0xF1, 0x19, 0x01, 0x01, 0x1B, 0x7E])

    # Test units - not implemented in device
    # result = await device.set_unit("inch")
    # assert result is True
    # expected_command = bytes([0xF1, 0xF1, 0x00, 0x00, 0x00, 0x7E])  # Not implemented


@pytest.mark.parametrize(
    ("limit", "height", "frame"),
    [
        # 1200 = 0x04B0; checksum = (0x21 + 0x02 + 0x04 + 0xB0) & 0xFF = 0xD7
        (HeightLimit.UPPER, 120.0, "f1f1210204b0d77e"),
        # 650 = 0x028A; checksum = (0x22 + 0x02 + 0x02 + 0x8A) & 0xFF = 0xB0
        (HeightLimit.LOWER, 65.0, "f1f12202028ab07e"),
    ],
)
async def test_set_height_limit_frames(
    mock_ble_device, mock_bleak_client, limit, height, frame
):
    """Test each limit is sent with its own command byte, after the handshake."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    await device.set_height_limit(limit, height)

    assert mock_bleak_client.write_gatt_char.call_args_list == [
        call(WRITE_CHARACTERISTIC_UUID, COMMAND_HANDSHAKE),
        call(WRITE_CHARACTERISTIC_UUID, bytes.fromhex(frame)),
    ]


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
        (device.get_lock_status, bytes([0xF1, 0xF1, 0xB2, 0x00, 0xB2, 0x7E])),
        (device.get_limits, bytes([0xF1, 0xF1, 0x0C, 0x00, 0x0C, 0x7E])),
    ]

    for method, expected_command in commands_to_test:
        mock_bleak_client.write_gatt_char.reset_mock()
        await method()
        mock_bleak_client.write_gatt_char.assert_called_once_with(
            WRITE_CHARACTERISTIC_UUID, expected_command
        )


@pytest.mark.parametrize(
    ("header", "value", "attribute", "expected"),
    [
        (LIGHT_COLOR_RESPONSE_HEADER, 0x03, "light_color", 3),
        (BRIGHTNESS_RESPONSE_HEADER, 0x64, "brightness", 100),
        (LIGHTING_RESPONSE_HEADER, 0x01, "lighting_enabled", True),
        (LIGHTING_RESPONSE_HEADER, 0x00, "lighting_enabled", False),
        (VIBRATION_RESPONSE_HEADER, 0x00, "vibration_enabled", False),
        (VIBRATION_RESPONSE_HEADER, 0x01, "vibration_enabled", True),
        (LOCK_STATUS_RESPONSE_HEADER, 0x01, "lock_status", True),
        (LOCK_STATUS_RESPONSE_HEADER, 0x00, "lock_status", False),
        (SENSITIVITY_RESPONSE_HEADER, 0x01, "sensitivity_level", 1),
    ],
)
def test_parse_feature_responses(mock_ble_device, header, value, attribute, expected):
    """Test each setting reply is stored and passed on to the listeners at once."""
    device = DeskBLEDevice(mock_ble_device)
    callback = MagicMock()
    device.register_notification_callback(callback)

    device._handle_notification(None, desk_response(header, value))

    assert getattr(device, attribute) == expected
    callback.assert_called_once_with(0.0, False, False)


@pytest.mark.parametrize(
    ("header", "attribute"),
    [
        (LIGHT_COLOR_RESPONSE_HEADER, "light_color"),
        (BRIGHTNESS_RESPONSE_HEADER, "brightness"),
        (LIGHTING_RESPONSE_HEADER, "lighting_enabled"),
        (VIBRATION_RESPONSE_HEADER, "vibration_enabled"),
        (LOCK_STATUS_RESPONSE_HEADER, "lock_status"),
        (SENSITIVITY_RESPONSE_HEADER, "sensitivity_level"),
    ],
)
def test_truncated_setting_reply_changes_nothing(mock_ble_device, header, attribute):
    """Test a setting reply cut short is ignored and nobody is told."""
    device = DeskBLEDevice(mock_ble_device)
    callback = MagicMock()
    device.register_notification_callback(callback)
    before = getattr(device, attribute)

    device._handle_notification(None, bytearray([*header, 0x01]))

    assert getattr(device, attribute) == before
    callback.assert_not_called()


def test_setting_reply_mid_movement_keeps_the_movement(mock_ble_device):
    """Test a setting reply during a movement passes on the movement unchanged."""
    device = DeskBLEDevice(mock_ble_device)
    _started_movement(
        device, "continuous", "up", start_height=80.0, height=85.0, moved_until=0.0
    )
    callback = MagicMock()
    device.register_notification_callback(callback)

    device._handle_notification(None, desk_response(SENSITIVITY_RESPONSE_HEADER, 0x03))

    assert device.sensitivity_level == 3
    assert device.is_moving is True
    callback.assert_called_once_with(85.0, False, True)


def test_parse_height_limit_responses(mock_ble_device):
    """Test parsing of height limit responses, which are big-endian millimetres."""
    device = DeskBLEDevice(mock_ble_device)

    device._handle_notification(
        None, desk_response(LIMIT_UPPER_RESPONSE_HEADER, 0x04, 0xB0)
    )
    assert device.height_limit_upper == 120.0

    device._handle_notification(
        None, desk_response(LIMIT_LOWER_RESPONSE_HEADER, 0x02, 0x8A)
    )
    assert device.height_limit_lower == 65.0


@pytest.mark.parametrize(
    ("status", "upper", "lower"),
    [(0x00, None, None), (0x01, 120.0, None), (0x10, None, 65.0), (0x11, 120.0, 65.0)],
)
def test_parse_limit_status_response(mock_ble_device, status, upper, lower):
    """Test a limit that the limit status reports as not set reads as None."""
    device = DeskBLEDevice(mock_ble_device)
    callback = MagicMock()
    device.register_notification_callback(callback)
    device._handle_notification(
        None, desk_response(LIMIT_UPPER_RESPONSE_HEADER, 0x04, 0xB0)
    )
    device._handle_notification(
        None, desk_response(LIMIT_LOWER_RESPONSE_HEADER, 0x02, 0x8A)
    )

    device._handle_notification(
        None, desk_response(LIMIT_STATUS_RESPONSE_HEADER, status)
    )

    assert device.height_limit_upper == upper
    assert device.height_limit_lower == lower
    assert device.limits_enabled is (status != 0x00)
    # Each limit frame updates the entities at once
    assert callback.call_count == 3


def test_unknown_limit_status_changes_nothing(mock_ble_device):
    """Test a limit status the desk does not define is ignored and nobody is told."""
    device = DeskBLEDevice(mock_ble_device)
    callback = MagicMock()
    device.register_notification_callback(callback)

    device._handle_notification(None, desk_response(LIMIT_STATUS_RESPONSE_HEADER, 0x02))

    assert device.limits_enabled is False
    callback.assert_not_called()


def test_limits_before_limit_status(mock_ble_device):
    """Test limits read as reported until the desk says whether they are set."""
    device = DeskBLEDevice(mock_ble_device)
    assert device.limits_enabled is False

    device._handle_notification(None, desk_response(LIMIT_STATUS_RESPONSE_HEADER, 0x00))
    device._handle_notification(
        None, desk_response(LIMIT_UPPER_RESPONSE_HEADER, 0x04, 0xB0)
    )
    assert device.height_limit_upper is None

    device._handle_notification(None, desk_response(LIMIT_STATUS_RESPONSE_HEADER, 0x01))
    assert device.height_limit_upper == 120.0


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
            bytes([0xF1, 0xF1, 0xB2, 0x00, 0xB2, 0x7E]),  # get_lock_status
            bytes([0xF1, 0xF1, 0x0C, 0x00, 0x0C, 0x7E]),  # get_limits
        ]

        # Check that all capability queries were sent
        sent_commands = [call[0][1] for call in calls[2:]]
        for expected in expected_queries:
            assert expected in sent_commands
        # The desk never answers the vibration intensity query, so it is not sent
        assert not any(command[2] == 0xA4 for command in sent_commands)


async def test_connect_sends_no_sensitivity_query(
    mock_ble_device, mock_establish_connection, mock_bleak_client
):
    """Connecting reads the sensitivity from the settings block, not its own query.

    The desk's reply to the query can disagree with the settings block, and
    the official app never sends the query.
    """
    device = DeskBLEDevice(mock_ble_device)

    assert await device.connect() is True

    writes = [c.args[1] for c in mock_bleak_client.write_gatt_char.call_args_list]
    assert not any(write.startswith(bytes.fromhex("f1f11d00")) for write in writes)
    assert writes[:2] == [COMMAND_HANDSHAKE, COMMAND_GET_STATUS]


@pytest.mark.parametrize(
    ("method", "value"),
    [
        ("set_light_color", 0),
        ("set_light_color", 8),
        ("set_brightness", -1),
        ("set_brightness", 101),
        ("set_sensitivity", 0),
        ("set_sensitivity", 4),
        ("set_touch_mode", -1),
        ("set_touch_mode", 2),
        ("set_unit", "meters"),
    ],
)
async def test_command_parameter_validation(
    mock_ble_device, mock_bleak_client, method, value
):
    """Test an out-of-range value raises and sends nothing."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    with pytest.raises(ValueError, match="Invalid"):
        await getattr(device, method)(value)

    mock_bleak_client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize("limit", list(HeightLimit))
@pytest.mark.parametrize("height", [59.0, 125.0])
async def test_set_height_limit_out_of_range(
    mock_ble_device, mock_bleak_client, limit, height
):
    """Test a limit outside 60-124 cm raises and sends nothing."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    with pytest.raises(ValueError, match=f"Invalid {limit} height limit"):
        await device.set_height_limit(limit, height)

    mock_bleak_client.write_gatt_char.assert_not_called()


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


async def test_read_device_information_success(
    mock_ble_device, mock_bleak_client_with_device_info
):
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


async def test_read_device_information_service_not_found(
    mock_ble_device, mock_bleak_client
):
    """Test when Device Information Service (0x180A) is not available."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    # Mock services without device info service
    mock_bleak_client.services = [
        MagicMock(uuid="0000fe60-0000-1000-8000-00805f9b34fb")
    ]

    await device._read_device_information()

    # Verify all device information remains None (fallback behavior)
    assert device.manufacturer_name is None
    assert device.model_number is None
    assert device.serial_number is None
    assert device.hardware_revision is None
    assert device.firmware_revision is None
    assert device.software_revision is None


async def test_read_device_information_partial_characteristics(
    mock_ble_device, mock_bleak_client
):
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
        if char_uuid.lower() == "00002a24-0000-1000-8000-00805f9b34fb":
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


async def test_read_device_information_characteristic_read_failure(
    mock_ble_device, mock_bleak_client
):
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


async def test_read_device_information_characteristic_not_readable(
    mock_ble_device, mock_bleak_client
):
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


async def test_read_device_information_utf8_decoding(
    mock_ble_device, mock_bleak_client
):
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
    mock_bleak_client.read_gatt_char = AsyncMock(
        return_value=b"  Test Manufacturer\x00\r\n\t "
    )

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


async def test_device_information_called_during_connect(
    mock_ble_device, mock_bleak_client_with_device_info
):
    """Test that device information is read during connection."""
    device = DeskBLEDevice(mock_ble_device)

    with patch.object(
        device, "_read_device_information", AsyncMock()
    ) as mock_read_device_info:
        with patch(
            "custom_components.desky_desk.bluetooth.establish_connection",
            return_value=mock_bleak_client_with_device_info,
        ):
            result = await device.connect()

            assert result is True
            # Verify device information was read during connection
            mock_read_device_info.assert_called_once()


@patch("time.time")
async def test_jitter_after_finished_move_is_not_a_movement(
    mock_time, mock_ble_device, mock_bleak_client
):
    """A 2 mm wobble long after an upward move neither moves nor collides (#20)."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    callback = MagicMock()
    device.register_notification_callback(callback)

    _replay(device, mock_time, [(0.0, 68.0)])
    mock_time.return_value = 0.0
    await device.move_up()
    # The desk rises to 70.0 cm and stops there
    _replay(
        device,
        mock_time,
        [
            (0.7, 68.5),
            (0.9, 69.0),
            (1.1, 69.5),
            (1.3, 70.0),
            (1.5, 70.0),
            (1.7, 70.0),
            (1.9, 70.0),
            (2.1, 70.0),
        ],
    )

    # More than 30 seconds later one reading drops by 2 mm
    _replay(device, mock_time, [(35.0, 70.0), (35.2, 69.8), (35.4, 69.8)])

    try:
        assert device.is_moving is False
        assert device.collision_detected is False
        assert _collision_starts(callback) == 0
    finally:
        await device.disconnect()


@patch("time.time")
async def test_press_after_bounce_and_long_wait_is_a_fresh_movement(
    mock_time, mock_ble_device, mock_bleak_client
):
    """After a bounce and 25 s of stillness, Move down is a new movement (#20)."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    callback = MagicMock()
    device.register_notification_callback(callback)

    _replay(device, mock_time, [(0.0, 75.0)])
    mock_time.return_value = 0.0
    await device.move_down()
    # The desk descends, hits an obstacle at 70.5 cm and bounces back up; the
    # collision clears itself (shortened here) and the desk sits still for 25 s
    with patch(
        "custom_components.desky_desk.bluetooth.COLLISION_AUTO_CLEAR_SECONDS", 0.01
    ):
        _replay(
            device,
            mock_time,
            [
                (0.4, 74.3),
                (0.6, 73.5),
                (0.8, 72.8),
                (1.0, 72.0),
                (1.2, 71.2),
                (1.4, 70.5),
                (1.6, 71.0),
                (1.8, 71.5),
            ],
        )
        assert _collision_starts(callback) == 1
        assert device.is_moving is False
        await asyncio.sleep(0.05)
    assert device.collision_detected is False
    _replay(device, mock_time, [(2.0 + i, 71.5) for i in range(25)])

    # Move down, the desk descends normally and stops
    mock_time.return_value = 27.0
    await device.move_down()
    _replay(
        device,
        mock_time,
        [
            (27.5, 71.2),
            (27.7, 70.5),
            (27.9, 69.8),
            (28.1, 69.0),
            (28.3, 68.3),
            (28.5, 67.6),
            (28.7, 67.6),
            (28.9, 67.6),
            (29.1, 67.6),
        ],
    )

    try:
        assert device.is_moving is False
        assert device.collision_detected is False
        assert _collision_starts(callback) == 1  # only the real bounce
    finally:
        await device.disconnect()


def _movement_frame(height_cm: float) -> bytearray:
    """Build a movement frame (98 98 00 00 LL HH) for a height in cm."""
    raw = round(height_cm * 10)
    return bytearray([0x98, 0x98, 0x00, 0x00, raw & 0xFF, raw >> 8])


async def _run_sequence(device, mock_time, frame, command, readings):
    """Send a command, feed readings as frames and return the observed outcomes."""
    callback = MagicMock()
    device.register_notification_callback(callback)
    mock_time.return_value = readings[0][0]
    device._handle_notification(None, frame(readings[0][1]))
    await command(device)
    for when, height in readings[1:]:
        mock_time.return_value = when
        device._handle_notification(None, frame(height))
    return [call_args.args for call_args in callback.call_args_list]


MOVEMENT_SEQUENCES = {
    "normal stop": (
        lambda device: device.move_up(),
        [
            (0.0, 80.0),
            (0.4, 80.7),
            (0.6, 81.4),
            (0.8, 82.1),
            (1.0, 82.8),
            (1.2, 83.5),
            (1.4, 84.2),
            (1.6, 84.2),
            (1.8, 84.2),
            (2.0, 84.2),
        ],
    ),
    "bounce": (
        lambda device: device.move_down(),
        [
            (0.0, 80.0),
            (0.4, 79.3),
            (0.6, 78.6),
            (0.8, 77.9),
            (1.0, 78.6),
            (1.2, 78.6),
            (1.4, 78.6),
            (1.6, 78.6),
        ],
    ),
    "stopped away from target": (
        lambda device: device.move_to_height(90.0),
        [
            (0.0, 80.0),
            (0.4, 80.7),
            (0.8, 81.4),
            (1.2, 82.1),
            (1.6, 82.5),
            (1.8, 82.5),
            (2.0, 82.5),
            (2.2, 82.5),
        ],
    ),
}


@pytest.mark.parametrize("sequence", MOVEMENT_SEQUENCES.keys())
@patch("time.time")
async def test_frame_type_does_not_change_movement_behaviour(
    mock_time, sequence, mock_ble_device, mock_bleak_client
):
    """The same heights as movement frames or status frames give the same outcomes."""
    command, readings = MOVEMENT_SEQUENCES[sequence]
    outcomes = []
    for frame in (_movement_frame, _status_frame):
        device = DeskBLEDevice(mock_ble_device)
        device._client = mock_bleak_client
        outcomes.append(
            await _run_sequence(device, mock_time, frame, command, readings)
        )
        await device.disconnect()

    assert outcomes[0] == outcomes[1]
    _, final_collision, final_moving = outcomes[0][-1]
    assert final_moving is False
    assert final_collision is (sequence != "normal stop")
    assert any(moving for _, _, moving in outcomes[0])  # each one really moved


@patch("time.time")
async def test_commanded_movement_begins_past_the_jitter(
    mock_time, mock_ble_device, mock_bleak_client
):
    """A move-up command followed by a rise beyond the jitter is a movement up."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    _replay(device, mock_time, [(0.0, 70.0)])
    await device.move_up()
    _replay(device, mock_time, [(0.4, 70.2), (0.6, 70.5)])
    assert device.is_moving is False  # still within the jitter band

    _replay(device, mock_time, [(0.8, 70.9)])
    assert device.is_moving is True
    assert device.movement_direction == "up"


@patch("time.time")
async def test_jitter_before_the_desk_responds(
    mock_time, mock_ble_device, mock_bleak_client
):
    """A 0.2 cm drop after a move-up command, before the desk moves, is jitter."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    _replay(device, mock_time, [(0.0, 70.0)])
    await device.move_up()
    _replay(device, mock_time, [(0.2, 69.8), (0.4, 69.8), (0.6, 69.8), (0.8, 69.8)])

    assert device.is_moving is False
    assert device.collision_detected is False
    # The command is still in flight: the desk may yet respond
    _replay(device, mock_time, [(1.0, 70.6)])
    assert device.is_moving is True


@patch("time.time")
async def test_movement_down_ignores_a_rise_before_the_desk_responds(
    mock_time, mock_ble_device, mock_bleak_client
):
    """A rise after a move-down command never starts a movement down."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    _replay(device, mock_time, [(0.0, 70.0)])
    await device.move_down()
    _replay(device, mock_time, [(0.4, 71.0)])

    assert device.is_moving is False
    assert device.collision_detected is False


@patch("time.time")
async def test_reversal_within_jitter_is_not_a_bounce(
    mock_time, mock_ble_device, mock_bleak_client
):
    """A 0.2 cm rise while moving down is not a collision; the movement continues."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    _replay(device, mock_time, [(0.0, 80.0)])
    await device.move_down()
    _replay(
        device,
        mock_time,
        [(0.4, 79.3), (0.6, 78.6), (0.8, 78.8), (1.0, 77.9), (1.2, 77.2)],
    )

    assert device.collision_detected is False
    assert device.is_moving is True
    assert device._movement.furthest_height == 77.2


@patch("time.time")
async def test_bounce_is_reported_once(mock_time, mock_ble_device, mock_bleak_client):
    """A real bounce turns the collision on once and ends the movement."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    callback = MagicMock()
    device.register_notification_callback(callback)

    _replay(device, mock_time, [(0.0, 80.0)])
    await device.move_down()
    _replay(
        device,
        mock_time,
        [(0.4, 79.3), (0.6, 78.6), (0.8, 77.9), (1.0, 78.6), (1.2, 79.3)],
    )
    _replay(device, mock_time, [(1.4 + i * 0.2, 79.3) for i in range(10)])

    try:
        assert _collision_starts(callback) == 1
        assert device.is_moving is False
        assert device._movement is None
    finally:
        await device.disconnect()


@patch("time.time")
async def test_command_that_never_moves_the_desk_expires(
    mock_time, mock_ble_device, mock_bleak_client
):
    """A locked desk ignores move-down; a later 0.2 cm wobble is not attributed to it."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    _replay(device, mock_time, [(0.0, 70.0)])
    await device.move_down()
    _replay(device, mock_time, [(1.0, 70.0), (2.0, 70.0)])
    assert device._movement is not None  # still waiting for the desk

    _replay(device, mock_time, [(30.0, 69.8)])
    assert device._movement is None  # expired
    assert device.is_moving is False
    assert device.collision_detected is False

    # Even a large change later belongs to no command
    _replay(device, mock_time, [(31.0, 65.0), (31.2, 60.0)])
    assert device.is_moving is False
    assert device.collision_detected is False


@patch("time.time")
async def test_command_expires_only_after_the_expiry_time(
    mock_time, mock_ble_device, mock_bleak_client
):
    """A desk that responds within the expiry time still starts the movement."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    _replay(device, mock_time, [(0.0, 70.0)])
    await device.move_up()
    _replay(device, mock_time, [(COMMAND_EXPIRY_SECONDS - 0.1, 71.0)])

    assert device.is_moving is True


@patch("time.time")
async def test_long_wait_before_the_stop_is_confirmed(
    mock_time, mock_ble_device, mock_bleak_client
):
    """Stop analysis ends at the last height change, not when the stop is confirmed."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    _replay(device, mock_time, [(0.0, 80.0)])
    await device.move_up()
    # 20 cm in 8 seconds
    _replay(device, mock_time, [(0.5 + i * 0.5, 80.0 + i * 1.25) for i in range(17)])
    assert device.height_cm == 100.0
    # The next readings only arrive 20 seconds later
    _replay(device, mock_time, [(28.5, 100.0), (28.7, 100.0), (28.9, 100.0)])

    assert device.is_moving is False
    assert device.collision_detected is False


async def test_failed_movement_command_ends_the_movement(
    mock_ble_device, mock_bleak_client
):
    """A movement command that cannot be sent leaves no movement behind."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    mock_bleak_client.write_gatt_char.side_effect = Exception("write failed")

    with pytest.raises(DeskCommandError):
        await device.move_up()
    assert device._movement is None
    assert device.movement_direction is None


@patch("time.time")
async def test_collision_from_before_a_drop_is_not_shown_after_reconnecting(
    mock_time, mock_ble_device, mock_bleak_client
):
    """The connection dropping ends the movement and clears its collision."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    _replay(device, mock_time, [(0.0, 80.0)])
    await device.move_down()
    _replay(device, mock_time, [(0.4, 79.3), (0.6, 78.6), (0.8, 79.3)])
    assert device.collision_detected is True

    # Drop while a new movement is under way
    await device.move_up()
    _replay(device, mock_time, [(1.4, 80.0)])
    assert device.is_moving is True
    device._handle_disconnect(mock_bleak_client)

    assert device.is_moving is False
    assert device.collision_detected is False
    assert device._auto_clear_task is None

    # Reconnect: the same height again neither moves nor collides
    device._client = mock_bleak_client
    _replay(device, mock_time, [(5.0, 80.0), (5.2, 80.0)])
    assert device.is_moving is False
    assert device.collision_detected is False


@pytest.mark.parametrize(
    ("kind", "height", "moved_until", "velocities", "expected"),
    [
        # Slowing to a crawl at the end of the movement
        ("continuous", 82.0, 2.0, [0.2, 0.2, 0.2], True),
        ("preset", 82.0, 2.0, [0.2, 0.2, 0.2], True),
        # Far enough, but too slow overall
        ("continuous", 80.8, 2.0, [], True),
        ("preset", 80.8, 2.0, [], True),
        # A short preset at moderate speed completes normally
        ("preset", 80.8, 1.2, [], False),
        # A preset that crept along for more than 10 seconds
        ("preset", 86.0, 11.0, [], True),
        # An unknown movement type is treated as a collision
        ("unknown", 85.0, 2.0, [], True),
    ],
)
def test_collision_stop_heuristics(
    mock_ble_device, kind, height, moved_until, velocities, expected
):
    """Each stop heuristic judges the active part of the movement."""
    device = DeskBLEDevice(mock_ble_device)
    _started_movement(
        device, kind, start_height=80.0, height=height, moved_until=moved_until
    )
    device._movement.velocities = velocities

    assert device._is_collision_stop(device._movement, moved_until) is expected


@pytest.mark.parametrize(
    ("frame", "attribute", "expected"),
    [
        # Frames captured from the desk (L-BTMEB95-07014-03, firmware Rev01)
        ("f2f20e01000f7e", "unit_preference", "cm"),
        ("f2f20e0101107e", "unit_preference", "in"),
        ("f2f21901001a7e", "touch_mode", 0),
        ("f2f21901011b7e", "touch_mode", 1),
        # Values the desk was never seen sending are not guessed
        ("f2f20e0102117e", "unit_preference", None),
        ("f2f21901021c7e", "touch_mode", None),
    ],
)
def test_parse_unit_and_touch_mode_reports(mock_ble_device, frame, attribute, expected):
    """The desk's unit and touch-mode reports update its state and notify at once."""
    device = DeskBLEDevice(mock_ble_device)
    device._height_cm = 80.0
    callback = MagicMock()
    device.register_notification_callback(callback)

    device._handle_notification(None, bytearray.fromhex(frame))

    assert getattr(device, attribute) == expected
    callback.assert_called_once_with(80.0, False, False)


def test_settings_block_after_connecting(mock_ble_device):
    """The settings block the desk sends after connecting sets unit and touch mode."""
    device = DeskBLEDevice(mock_ble_device)
    for frame in (
        "f2f2250202bde67e",  # preset 1
        "f2f2260203b6e17e",  # preset 2
        "f2f227020257827e",  # preset 3
        "f2f2280200002a7e",  # preset 4 (unset)
        "f2f20e01000f7e",  # unit: cm
        "f2f21901001a7e",  # touch mode: one press
        "f2f2170101197e",  # unknown
        "f2f21d01011f7e",  # sensitivity: high
    ):
        device._handle_notification(None, bytearray.fromhex(frame))

    assert device.unit_preference == "cm"
    assert device.touch_mode == 0
    assert device.sensitivity_level == 1


@pytest.mark.parametrize(
    "unknown", [None, "f2f20e01000f7e", "f2f21901001a7e", "f2f21d0102207e"]
)
def test_settings_known_needs_every_setting_of_the_block(
    mock_ble_device, unknown: str | None
):
    """The settings are known once the unit, touch mode and sensitivity all are."""
    device = DeskBLEDevice(mock_ble_device)
    assert device.settings_known is False

    for frame in ("f2f20e01000f7e", "f2f21901001a7e", "f2f21d0102207e"):
        if frame != unknown:
            device._handle_notification(None, bytearray.fromhex(frame))

    assert device.settings_known is (unknown is None)


def test_disconnect_forgets_settings(mock_ble_device, mock_bleak_client):
    """Settings are read again after reconnecting, so a disconnect clears them."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._handle_notification(None, bytearray.fromhex("f2f20e0101107e"))
    device._handle_notification(None, bytearray.fromhex("f2f21901011b7e"))
    device._handle_notification(None, bytearray.fromhex("f2f21d0102207e"))

    device._handle_disconnect(mock_bleak_client)

    assert device.unit_preference is None
    assert device.touch_mode is None
    assert device.sensitivity_level is None


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("move_up", ()),
        ("move_down", ()),
        ("move_to_preset", (2,)),
        ("move_to_height", (90.0,)),
        ("get_settings", ()),
        ("set_light_color", (3,)),
        ("set_brightness", (50,)),
        ("set_lighting", (True,)),
        ("set_vibration", (False,)),
        ("set_lock_status", (True,)),
        ("set_sensitivity", (2,)),
        ("set_touch_mode", (1,)),
        ("set_unit", ("in",)),
        ("set_height_limit", (HeightLimit.UPPER, 110.0)),
        ("set_height_limit", (HeightLimit.LOWER, 70.0)),
        ("clear_height_limits", ()),
    ],
)
async def test_commands_wake_the_desk_first(
    mock_ble_device, mock_bleak_client, method, args
):
    """Movement and settings commands are preceded by the handshake."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._height_cm = 80.0

    await getattr(device, method)(*args)

    writes = [c.args[1] for c in mock_bleak_client.write_gatt_char.call_args_list]
    assert len(writes) == 2
    assert writes[0] == COMMAND_HANDSHAKE
    assert writes[1] != COMMAND_HANDSHAKE


async def test_concurrent_commands_do_not_interleave(
    mock_ble_device, mock_bleak_client
):
    """Two commands sent at the same moment reach the desk one after the other."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._height_cm = 80.0
    writes: list[bytes] = []

    async def _write(_uuid: str, data: bytes) -> None:
        # Yield mid-write, as a real GATT write does, so the other caller can run
        await asyncio.sleep(0)
        writes.append(bytes(data))

    mock_bleak_client.write_gatt_char.side_effect = _write
    light_red = device._create_command_with_byte_param(0xB4, 2)

    await asyncio.gather(device.move_to_preset(2), device.set_light_color(2))

    # Each command stays together with the handshake that wakes the desk for it
    assert writes == [COMMAND_HANDSHAKE, COMMAND_MEMORY_2, COMMAND_HANDSHAKE, light_red]


async def test_failed_write_releases_the_desk_for_the_next_command(
    mock_ble_device, mock_bleak_client
):
    """A write that fails does not block the commands after it."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    mock_bleak_client.write_gatt_char.side_effect = [Exception("busy"), None]

    with pytest.raises(DeskCommandError):
        await device.get_status()
    await device.get_status()

    assert mock_bleak_client.write_gatt_char.call_count == 2


async def test_stop_is_sent_without_waking(mock_ble_device, mock_bleak_client):
    """Stop goes out at once: a moving desk is awake already."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    await device.stop()

    mock_bleak_client.write_gatt_char.assert_called_once_with(
        WRITE_CHARACTERISTIC_UUID, COMMAND_STOP
    )


async def test_get_settings_requests_status_after_handshake(
    mock_ble_device, mock_bleak_client
):
    """The settings block is requested with a handshake followed by a status request."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client

    await device.get_settings()

    assert mock_bleak_client.write_gatt_char.call_args_list == [
        call(WRITE_CHARACTERISTIC_UUID, COMMAND_HANDSHAKE),
        call(WRITE_CHARACTERISTIC_UUID, COMMAND_GET_STATUS),
    ]


@pytest.mark.parametrize(
    ("method", "args"),
    [("move_up", ()), ("set_unit", ("in",)), ("get_settings", ())],
)
async def test_failed_handshake_fails_the_command(
    mock_ble_device, mock_bleak_client, method, args
):
    """If the handshake cannot be written, the command fails and is not sent."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    mock_bleak_client.write_gatt_char.side_effect = Exception("write failed")

    with pytest.raises(DeskCommandError):
        await getattr(device, method)(*args)
    mock_bleak_client.write_gatt_char.assert_called_once_with(
        WRITE_CHARACTERISTIC_UUID, COMMAND_HANDSHAKE
    )
    assert device._movement is None


# Preset 2 run captured in inch mode: 27.0 in -> 37.4 in, about 0.65 s after the command
INCH_MODE_PRESET_RUN = [
    (0.650, "f2f20103010f071b7e"), (0.859, "f2f201030110071c7e"),
    (1.048, "f2f201030112071e7e"), (1.258, "f2f20103011507217e"),
    (1.469, "f2f20103011807247e"), (1.679, "f2f20103011b07277e"),
    (1.885, "f2f20103011e072a7e"), (2.087, "f2f201030120072c7e"),
    (2.285, "f2f201030123072f7e"), (2.448, "f2f20103012607327e"),
    (2.667, "f2f20103012907357e"), (2.873, "f2f20103012c07387e"),
    (3.095, "f2f20103012e073a7e"), (3.299, "f2f201030131073d7e"),
    (3.491, "f2f20103013407407e"), (3.677, "f2f20103013707437e"),
    (3.882, "f2f20103013a07467e"), (4.099, "f2f20103013d07497e"),
    (4.333, "f2f201030140074c7e"), (4.599, "f2f201030143074f7e"),
    (4.749, "f2f20103014507517e"), (5.044, "f2f20103014907557e"),
    (5.163, "f2f20103014b07577e"), (5.360, "f2f20103014f075b7e"),
    (5.640, "f2f201030151075d7e"), (6.075, "f2f20103015407607e"),
    (6.173, "f2f20103015707637e"), (6.236, "f2f20103015a07667e"),
    (6.594, "f2f20103015d07697e"), (6.693, "f2f201030160076c7e"),
    (6.979, "f2f201030163076f7e"), (7.103, "f2f20103016607727e"),
    (7.303, "f2f20103016907757e"), (7.517, "f2f20103016c07787e"),
    (7.694, "f2f20103016f077b7e"), (7.916, "f2f201030171077d7e"),
    (8.424, "f2f201030172077e7e"), (8.437, "f2f20103017407807e"),
    (8.592, "f2f20103017507817e"), (8.830, "f2f20103017607827e"),
]  # fmt: skip

INCH_REPORT = bytearray.fromhex("f2f20e0101107e")
CM_REPORT = bytearray.fromhex("f2f20e01000f7e")


@pytest.mark.parametrize(
    ("unit_report", "frame", "expected"),
    [
        # Frames from #21, captured at the same desk height in both units
        (CM_REPORT, "f2f2010302ba07c77e", 69.8),
        (INCH_REPORT, "f2f201030112071e7e", 69.6),  # 27.4 in
    ],
)
def test_status_frame_is_decoded_in_the_display_unit(
    mock_ble_device, unit_report, frame, expected
):
    """A status frame carries tenths of the display unit; heights are always cm."""
    device = DeskBLEDevice(mock_ble_device)
    device._handle_notification(None, unit_report)

    device._handle_notification(None, bytearray.fromhex(frame))

    assert device.height_cm == expected


@patch("time.time")
def test_unit_switched_while_connected(mock_time, mock_ble_device):
    """Switching cm to inches mid-session changes the height by under 0.5 cm (#21)."""
    device = DeskBLEDevice(mock_ble_device)
    callback = MagicMock()
    device.register_notification_callback(callback)
    device._handle_notification(None, CM_REPORT)
    mock_time.return_value = 0.0
    device._handle_notification(None, bytearray.fromhex("f2f2010302ba07c77e"))

    # The switch from Home Assistant: the desk reports the new unit, then heights
    device._handle_notification(None, INCH_REPORT)
    mock_time.return_value = 4.0
    device._handle_notification(None, bytearray.fromhex("f2f201030112071e7e"))

    assert abs(device.height_cm - 69.8) < 0.5
    assert device.is_moving is False
    assert device.collision_detected is False
    assert all(not moving for _, _, moving in (c.args for c in callback.call_args_list))


def test_first_frame_before_the_unit_report(mock_ble_device):
    """A desk in inches whose first height arrives before its unit report reads right."""
    device = DeskBLEDevice(mock_ble_device)
    callback = MagicMock()
    device.register_notification_callback(callback)

    device._handle_notification(None, bytearray.fromhex("f2f20103017607827e"))
    device._handle_notification(None, INCH_REPORT)

    assert device.height_cm == 95.0  # 37.4 in
    # No reading below the desk's minimum height was ever exposed
    assert all(c.args[0] >= MIN_HEIGHT for c in callback.call_args_list)


def test_first_frame_new_unit_before_its_report(mock_ble_device):
    """A unit change on the hand controller sends the new-unit height before the report."""
    device = DeskBLEDevice(mock_ble_device)
    device._handle_notification(None, INCH_REPORT)
    device._handle_notification(None, bytearray.fromhex("f2f201030162076e7e"))
    assert device.height_cm == 89.9  # 35.4 in

    # Captured: raw 900 arrives 0.46 s before the desk reports cm
    device._handle_notification(None, bytearray.fromhex("f2f20103038407927e"))
    assert device.height_cm == 90.0
    device._handle_notification(None, CM_REPORT)
    assert device.unit_preference == "cm"
    assert device.height_cm == 90.0


async def test_reconnect_after_unit_change_on_the_hand_controller(
    mock_ble_device, mock_bleak_client
):
    """A unit changed while disconnected is not decoded under the stale unit."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._handle_notification(None, CM_REPORT)
    device._handle_notification(None, bytearray.fromhex("f2f2010302ba07c77e"))
    device._handle_disconnect(mock_bleak_client)

    # Switched to inches on the hand controller; the first height after
    # reconnecting arrives before the unit report
    device._client = mock_bleak_client
    device._handle_notification(None, bytearray.fromhex("f2f201030112071e7e"))

    assert device.height_cm == 69.6


def test_implausible_height_is_logged(mock_ble_device, caplog):
    """A height that fits neither unit is still decoded, and logged with its frame."""
    device = DeskBLEDevice(mock_ble_device)
    caplog.set_level("DEBUG", logger="custom_components.desky_desk.bluetooth")
    device._handle_notification(None, CM_REPORT)

    device._handle_notification(None, bytearray.fromhex("f2f20103057807887e"))

    assert device.height_cm == 140.0
    assert "fits neither unit (frame f2f20103057807887e)" in caplog.text


@pytest.mark.parametrize("frame", [_status_frame, _movement_frame])
@patch("time.time")
async def test_inch_mode_movement_reports_physical_heights(
    mock_time, frame, mock_ble_device, mock_bleak_client
):
    """A movement captured in inch mode is tracked in cm, whichever frame type it uses."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._handle_notification(None, INCH_REPORT)
    mock_time.return_value = 0.0
    device._handle_notification(None, bytearray.fromhex("f2f20103010e071a7e"))
    assert device.height_cm == 68.6  # 27.0 in
    callback = MagicMock()
    device.register_notification_callback(callback)

    await device.move_to_preset(2)
    for when, captured in INCH_MODE_PRESET_RUN:
        mock_time.return_value = when
        raw = int(captured[8:12], 16)
        device._handle_notification(None, frame(raw / 10.0))
    for when in (9.0, 9.2, 9.4):
        mock_time.return_value = when
        device._handle_notification(None, frame(37.4))

    heights = [c.args[0] for c in callback.call_args_list]
    assert all(MIN_HEIGHT <= height <= MAX_HEIGHT for height in heights)
    assert heights[-1] == 95.0  # 37.4 in
    assert any(c.args[2] for c in callback.call_args_list)  # it moved
    assert device.is_moving is False
    assert device.collision_detected is False


@pytest.mark.parametrize("unit_report", [CM_REPORT, INCH_REPORT])
async def test_move_to_height_target_is_always_mm(
    mock_ble_device, mock_bleak_client, unit_report
):
    """The move-to-height target is in mm, whatever the display unit."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._handle_notification(None, unit_report)
    device._handle_notification(None, bytearray.fromhex("f2f2010302ba07c77e"))

    await device.move_to_height(85.0)

    # 850 mm = 0x0352
    mock_bleak_client.write_gatt_char.assert_called_with(
        WRITE_CHARACTERISTIC_UUID,
        bytes([0xF1, 0xF1, 0x1B, 0x02, 0x03, 0x52, 0x72, 0x7E]),
    )


@pytest.mark.parametrize(
    ("unit_report", "height_frame", "sent", "response", "read_back"),
    [
        # cm: tenths of a cm (mm)
        (CM_REPORT, "f2f2010302ba07c77e", 1100, "f2f22102044c737e", 110.0),
        # inches: 110 cm is sent as 43.3 in; the desk reports 43.2 in back
        (INCH_REPORT, "f2f201030112071e7e", 433, "f2f2210201b0d47e", 109.7),
    ],
)
async def test_height_limits_round_trip_in_cm(
    mock_ble_device,
    mock_bleak_client,
    unit_report,
    height_frame,
    sent,
    response,
    read_back,
):
    """Height limits are in the display unit on the wire and in cm everywhere else."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._handle_notification(None, unit_report)
    device._handle_notification(None, bytearray.fromhex(height_frame))

    await device.set_height_limit(HeightLimit.UPPER, 110.0)
    await device.set_height_limit(HeightLimit.LOWER, 70.0)

    writes = [c.args[1] for c in mock_bleak_client.write_gatt_char.call_args_list]
    assert writes[1] == device._create_command_with_word_param(0x21, sent)
    lower = 700 if unit_report is CM_REPORT else 276  # 70 cm = 27.6 in
    assert writes[3] == device._create_command_with_word_param(0x22, lower)

    # The desk truncates the stored limit, so in inches it reads back a step low
    device._handle_notification(None, bytearray.fromhex(response))
    assert device.height_limit_upper == read_back


@pytest.mark.parametrize(("height", "sent"), [(61.0, 240), (121.9, 480)])
async def test_inch_limit_range_ends_are_sent_within_24_48_in(
    mock_ble_device, mock_bleak_client, height, sent
):
    """The ends of the inch limit range, 61.0 and 121.9 cm, are 24.0 and 48.0 in."""
    device = DeskBLEDevice(mock_ble_device)
    device._client = mock_bleak_client
    device._handle_notification(None, INCH_REPORT)

    await device.set_height_limit(HeightLimit.UPPER, height)

    assert mock_bleak_client.write_gatt_char.call_args_list[-1] == call(
        WRITE_CHARACTERISTIC_UUID, device._create_command_with_word_param(0x21, sent)
    )
