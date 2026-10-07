"""Test the Desky Desk update coordinator.

Setup, retry and unload are covered in `test_init.py`. These tests drive a
loaded entry through Home Assistant time and the mocked desk's callbacks.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.desky_desk.bluetooth import DeskCommandError
from custom_components.desky_desk.const import (
    DOMAIN,
    RECONNECT_BACKOFF_MAX_SECONDS,
    RECONNECT_BACKOFF_MIN_SECONDS,
    UPDATE_INTERVAL_SECONDS,
)
from custom_components.desky_desk.coordinator import DeskData, DeskUpdateCoordinator

from . import BluetoothCallbacks, desk_data, disconnect_desk, notify_desk

ADDRESS = "AA:BB:CC:DD:EE:FF"
COORDINATOR_LOGGER = "custom_components.desky_desk.coordinator"
INTEGRATION_LOGGER = "custom_components.desky_desk"
HEIGHT_ENTITY = "number.desky_desk_height"

NO_DEVICE_INFO = {
    "manufacturer_name": None,
    "model_number": None,
    "serial_number": None,
    "hardware_revision": None,
    "firmware_revision": None,
    "software_revision": None,
}


async def _advance(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    """Move Home Assistant time forward and run whatever became due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Run the coordinator's next scheduled poll."""
    await _advance(hass, freezer, UPDATE_INTERVAL_SECONDS)


def _entity_states(hass: HomeAssistant, entry: MockConfigEntry) -> list[str]:
    """Return the states of the entry's entities."""
    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    return [
        state.state
        for entity in entries
        if (state := hass.states.get(entity.entity_id)) is not None
    ]


def _desk_device(hass: HomeAssistant, entry: MockConfigEntry) -> dr.DeviceEntry:
    """Return the desk's device registry entry."""
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return device


async def _lose_desk(hass: HomeAssistant, desk: MagicMock) -> None:
    """Drop the connection to a desk that then refuses to reconnect."""
    desk.connect.side_effect = None
    desk.connect.return_value = False
    disconnect_desk(desk)
    await hass.async_block_till_done(wait_background_tasks=True)


def _desk_stops_answering(desk: MagicMock) -> None:
    """Make the desk ignore commands on a connection that still looks open."""
    desk.get_status.side_effect = DeskCommandError("Not connected")
    desk.connect.return_value = False

    async def _disconnect() -> None:
        desk.is_connected = False

    desk.disconnect.side_effect = _disconnect


def _reconnect_succeeds(desk: MagicMock) -> None:
    """Make the desk's next connection attempt succeed."""

    async def _connect() -> bool:
        desk.is_connected = True
        return True

    desk.connect.side_effect = _connect


async def test_first_refresh_reads_desk(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test setup requests the desk's status and builds the data from it."""
    coordinator = init_integration.runtime_data

    mock_desk.get_status.assert_awaited_once()
    assert isinstance(coordinator.data, DeskData)
    assert coordinator.data == desk_data()
    assert coordinator.device is mock_desk


async def test_poll_reads_desk(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test each poll requests the status and rebuilds every field from the desk."""
    changes = {
        "height_cm": 95.5,
        "light_color": 4,  # Blue
        "brightness": 100,
        "lighting_enabled": False,
        "vibration_enabled": False,
        "vibration_intensity": 25,
        "lock_status": True,
        "sensitivity_level": 1,  # High
        "height_limit_upper": 130.0,
        "height_limit_lower": 60.0,
        "limits_enabled": False,
        "touch_mode": 1,  # Double press
        "unit_preference": "inch",
        "manufacturer_name": "FlexiSpot",
        "model_number": "E7",
        "serial_number": "FS12345678",
        "hardware_revision": "2.0",
        "firmware_revision": "3.1.0",
        "software_revision": "2.0.1",
    }
    for key, value in changes.items():
        setattr(mock_desk, key, value)

    await _poll(hass, freezer)

    assert mock_desk.get_status.await_count == 2
    assert init_integration.runtime_data.data == desk_data(**changes)


async def test_poll_without_device_information_service(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test polling a desk that reports no device information."""
    caplog.set_level(logging.DEBUG, logger=COORDINATOR_LOGGER)
    for key, value in NO_DEVICE_INFO.items():
        setattr(mock_desk, key, value)

    await _poll(hass, freezer)

    assert init_integration.runtime_data.data == desk_data(**NO_DEVICE_INFO)
    assert "No device information available in coordinator" in caplog.text


async def test_notification_updates_data(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test a notification rebuilds the data from the desk without polling."""
    notify_desk(
        mock_desk,
        height_cm=95.0,
        is_moving=True,
        movement_direction="up",
        collision_detected=True,
        light_color=6,  # Party mode
    )
    await hass.async_block_till_done()

    assert init_integration.runtime_data.data == desk_data(
        height_cm=95.0,
        is_moving=True,
        movement_direction="up",
        collision_detected=True,
        light_color=6,
    )
    mock_desk.get_status.assert_awaited_once()
    assert hass.states.get(HEIGHT_ENTITY).state == "95.0"


async def test_disconnect_keeps_last_known_state(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test a disconnect clears movement and collision but keeps the rest."""
    notify_desk(
        mock_desk,
        height_cm=95.0,
        is_moving=True,
        movement_direction="down",
        collision_detected=True,
    )

    # The desk still reports moving and a collision, but it is gone
    disconnect_desk(mock_desk)
    await hass.async_block_till_done()

    assert init_integration.runtime_data.data == desk_data(
        is_connected=False,
        height_cm=95.0,
        is_moving=False,
        movement_direction=None,
        collision_detected=False,
    )
    assert all(
        state == STATE_UNAVAILABLE for state in _entity_states(hass, init_integration)
    )


async def test_disconnect_reconnects_at_once(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test a dropped connection is re-established without waiting for a poll."""
    _reconnect_succeeds(mock_desk)
    mock_desk.height_cm = 72.0
    # The desk reports new firmware once it is back
    mock_desk.firmware_revision = "2.2.0"

    disconnect_desk(mock_desk)
    await hass.async_block_till_done(wait_background_tasks=True)

    coordinator = init_integration.runtime_data
    assert mock_desk.connect.await_count == 2
    assert coordinator.data == desk_data(height_cm=72.0, firmware_revision="2.2.0")
    assert STATE_UNAVAILABLE not in _entity_states(hass, init_integration)
    assert _desk_device(hass, init_integration).sw_version == "2.2.0"
    assert not init_integration._background_tasks


async def test_desk_returns_to_range(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    mock_bluetooth_callbacks: BluetoothCallbacks,
) -> None:
    """Test a desk that comes back reconnects as soon as it advertises."""
    await _lose_desk(hass, mock_desk)
    mock_bluetooth_callbacks.lose_sight()
    assert all(
        state == STATE_UNAVAILABLE for state in _entity_states(hass, init_integration)
    )

    # No fixed interval: the advertisement itself starts the reconnect
    _reconnect_succeeds(mock_desk)
    mock_bluetooth_callbacks.advertise()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_desk.connect.await_count == 3
    assert init_integration.runtime_data.data.is_connected
    assert STATE_UNAVAILABLE not in _entity_states(hass, init_integration)


async def test_desk_moves_between_proxies(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    mock_bluetooth_callbacks: BluetoothCallbacks,
) -> None:
    """Test the reconnect uses the proxy that heard the desk most recently."""
    await _lose_desk(hass, mock_desk)
    mock_bluetooth_callbacks.lose_sight()

    routes: list[MagicMock] = []

    async def _connect() -> bool:
        routes.append(mock_desk.set_ble_device.call_args.args[0])
        mock_desk.is_connected = True
        return True

    mock_desk.connect.side_effect = _connect
    other_proxy = MagicMock(address=ADDRESS)
    mock_bluetooth_callbacks.advertise(other_proxy)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert routes == [other_proxy]


async def test_advertisement_while_connected_only_updates_the_route(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    mock_bluetooth_callbacks: BluetoothCallbacks,
) -> None:
    """Test advertisements from a connected desk do not reconnect it."""
    route = MagicMock(address=ADDRESS)
    mock_bluetooth_callbacks.advertise(route)
    await hass.async_block_till_done(wait_background_tasks=True)

    mock_desk.set_ble_device.assert_called_with(route)
    mock_desk.connect.assert_awaited_once()


async def test_advertisements_during_a_reconnect_start_no_other(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    mock_bluetooth_callbacks: BluetoothCallbacks,
) -> None:
    """Test advertisements arriving while connecting do not start more attempts."""
    release = asyncio.Event()

    async def _connect() -> bool:
        await release.wait()
        mock_desk.is_connected = True
        return True

    mock_desk.connect.side_effect = _connect
    disconnect_desk(mock_desk)
    await hass.async_block_till_done()
    for _ in range(5):
        mock_bluetooth_callbacks.advertise()
    release.set()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_desk.connect.await_count == 2
    assert init_integration.runtime_data.data.is_connected


async def test_repeated_connect_failures_back_off(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    mock_bluetooth_callbacks: BluetoothCallbacks,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test retries against an advertising desk wait longer each time, up to a cap."""
    await _lose_desk(hass, mock_desk)
    attempts = mock_desk.connect.await_count

    delays = [5, 10, 20, 40, 80, 120, 120]
    assert delays[0] == RECONNECT_BACKOFF_MIN_SECONDS
    assert delays[-1] == RECONNECT_BACKOFF_MAX_SECONDS
    for delay in delays:
        # The desk keeps advertising, but that does not cut the wait short
        mock_bluetooth_callbacks.advertise()
        await _advance(hass, freezer, delay - 1)
        assert mock_desk.connect.await_count == attempts

        await _advance(hass, freezer, 1)
        attempts += 1
        assert mock_desk.connect.await_count == attempts

    # A success resets the delay for the next outage
    _reconnect_succeeds(mock_desk)
    await _advance(hass, freezer, RECONNECT_BACKOFF_MAX_SECONDS)
    assert init_integration.runtime_data.data.is_connected

    await _lose_desk(hass, mock_desk)
    attempts = mock_desk.connect.await_count
    await _advance(hass, freezer, RECONNECT_BACKOFF_MIN_SECONDS)
    assert mock_desk.connect.await_count == attempts + 1


async def test_retry_waits_for_a_desk_out_of_range(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    mock_bluetooth_callbacks: BluetoothCallbacks,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a retry is skipped while the desk is not seen, until it advertises."""
    await _lose_desk(hass, mock_desk)
    attempts = mock_desk.connect.await_count

    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        await _advance(hass, freezer, RECONNECT_BACKOFF_MIN_SECONDS)
    assert mock_desk.connect.await_count == attempts

    # Nothing retries on a timer any more...
    await _advance(hass, freezer, RECONNECT_BACKOFF_MAX_SECONDS)
    assert mock_desk.connect.await_count == attempts

    # ...and the desk's next advertisement reconnects at once
    _reconnect_succeeds(mock_desk)
    mock_bluetooth_callbacks.advertise()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_desk.connect.await_count == attempts + 1
    assert init_integration.runtime_data.data.is_connected


async def test_desk_powered_off(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    mock_bluetooth_callbacks: BluetoothCallbacks,
) -> None:
    """Test a desk the stack stops seeing goes unavailable if it stops answering."""
    _desk_stops_answering(mock_desk)

    mock_bluetooth_callbacks.lose_sight()
    await hass.async_block_till_done(wait_background_tasks=True)

    mock_desk.disconnect.assert_awaited_once()
    assert not init_integration.runtime_data.data.is_connected
    assert all(
        state == STATE_UNAVAILABLE for state in _entity_states(hass, init_integration)
    )


async def test_stack_loses_sight_of_a_desk_that_still_answers(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    mock_bluetooth_callbacks: BluetoothCallbacks,
) -> None:
    """Test a connected desk that stops advertising but still answers stays up."""
    mock_bluetooth_callbacks.lose_sight()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_desk.get_status.await_count == 2
    mock_desk.disconnect.assert_not_called()
    assert STATE_UNAVAILABLE not in _entity_states(hass, init_integration)


async def test_settings_missed_at_power_on_are_asked_for_again(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a desk reached while booting is asked for its settings at the next poll.

    Measured on hardware: a desk connected within a second of powering up
    ignores the settings request sent while connecting.
    """
    await _lose_desk(hass, mock_desk)
    _reconnect_succeeds(mock_desk)
    # The disconnect forgot the settings, and the booting desk does not resend them
    notify_desk(mock_desk, unit_preference=None, touch_mode=None)
    await _advance(hass, freezer, RECONNECT_BACKOFF_MIN_SECONDS)
    assert init_integration.runtime_data.data.is_connected
    status_requests = mock_desk.get_status.await_count

    await _poll(hass, freezer)
    mock_desk.get_settings.assert_awaited_once_with()
    assert mock_desk.get_status.await_count == status_requests

    # Asked once per connection, so a desk that never reports them is left alone
    await _poll(hass, freezer)
    await _poll(hass, freezer)
    mock_desk.get_settings.assert_awaited_once_with()
    assert mock_desk.get_status.await_count == status_requests + 2


async def test_settings_reported_while_connecting_are_not_asked_for_again(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a reconnect that read the settings polls the status as usual."""
    await _lose_desk(hass, mock_desk)
    _reconnect_succeeds(mock_desk)
    await _advance(hass, freezer, RECONNECT_BACKOFF_MIN_SECONDS)
    assert init_integration.runtime_data.data.is_connected
    status_requests = mock_desk.get_status.await_count

    await _poll(hass, freezer)

    mock_desk.get_settings.assert_not_called()
    assert mock_desk.get_status.await_count == status_requests + 1


async def test_settings_missing_after_setup_are_asked_for_at_the_first_poll(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the refresh right after setup does not ask, but the first poll does."""
    mock_desk.unit_preference = None
    mock_config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=MagicMock(address=ADDRESS),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    mock_desk.get_settings.assert_not_called()

    await _poll(hass, freezer)

    mock_desk.get_settings.assert_awaited_once_with()


async def test_poll_drops_a_connection_the_desk_no_longer_answers(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a failed status request closes the connection and marks it unavailable."""
    _desk_stops_answering(mock_desk)

    await _poll(hass, freezer)

    mock_desk.disconnect.assert_awaited_once()
    assert all(
        state == STATE_UNAVAILABLE for state in _entity_states(hass, init_integration)
    )


async def test_dropped_connection_is_logged_once(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test closing a dead connection, which Bleak also reports, logs one warning."""
    _desk_stops_answering(mock_desk)
    disconnected = mock_desk.register_disconnect_callback.call_args.args[0]

    async def _disconnect() -> None:
        mock_desk.is_connected = False
        # Bleak reports the disconnect it was asked for as well
        disconnected()

    mock_desk.disconnect.side_effect = _disconnect

    await _poll(hass, freezer)

    assert caplog.text.count("is unavailable") == 1
    # The second report does not start a second attempt before the backoff
    assert mock_desk.connect.await_count == 2


async def test_poll_while_disconnected_reports_unavailable(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test polling a disconnected desk sends nothing and is not an update failure."""
    await _lose_desk(hass, mock_desk)

    await _poll(hass, freezer)

    coordinator = init_integration.runtime_data
    assert coordinator.last_update_success
    assert not coordinator.data.is_connected
    mock_desk.get_status.assert_awaited_once()


async def test_extended_outage_logs_one_warning(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    mock_bluetooth_callbacks: BluetoothCallbacks,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test an hour of failing retries logs the outage once, at warning level."""
    caplog.set_level(logging.DEBUG, logger=INTEGRATION_LOGGER)
    await _lose_desk(hass, mock_desk)

    for _ in range(60):
        mock_bluetooth_callbacks.advertise()
        await _advance(hass, freezer, 60)
        await _poll(hass, freezer)
    assert mock_desk.connect.await_count > 30

    problems = [
        record
        for record in caplog.records
        if record.name.startswith(INTEGRATION_LOGGER)
        and record.levelno >= logging.WARNING
    ]
    assert [(record.levelno, record.getMessage()) for record in problems] == [
        (logging.WARNING, f"The desk at {ADDRESS} is unavailable")
    ]
    assert f"Could not reconnect to the desk at {ADDRESS}" in caplog.text


async def test_recovery_logs_one_info_message(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    mock_bluetooth_callbacks: BluetoothCallbacks,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the desk coming back is logged once, at info level."""
    await _lose_desk(hass, mock_desk)
    await _advance(hass, freezer, RECONNECT_BACKOFF_MIN_SECONDS)
    caplog.clear()

    _reconnect_succeeds(mock_desk)
    await _advance(hass, freezer, 2 * RECONNECT_BACKOFF_MIN_SECONDS)
    await _poll(hass, freezer)

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name.startswith(INTEGRATION_LOGGER) and record.levelno >= logging.INFO
    ]
    assert messages == [f"The desk at {ADDRESS} is available again"]

    # The next outage is logged again
    await _lose_desk(hass, mock_desk)
    assert f"The desk at {ADDRESS} is unavailable" in caplog.text


async def test_shutdown_stops_reconnecting_and_disconnects(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    mock_bluetooth_callbacks: BluetoothCallbacks,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test shutting the coordinator down cancels retries and disconnects."""
    await _lose_desk(hass, mock_desk)
    attempts = mock_desk.connect.await_count

    await init_integration.runtime_data.async_shutdown()
    await hass.async_block_till_done()

    mock_desk.disconnect.assert_awaited_once()
    # Neither the retry timer nor an advertisement reconnects any more
    await _advance(hass, freezer, RECONNECT_BACKOFF_MAX_SECONDS)
    mock_bluetooth_callbacks.advertise()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_desk.connect.await_count == attempts


async def test_shutdown_cancels_a_running_reconnect(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test shutting down while a reconnect is in progress cancels it."""
    started = asyncio.Event()

    async def _connect() -> bool:
        started.set()
        await asyncio.Event().wait()
        return True

    mock_desk.connect.side_effect = _connect
    disconnect_desk(mock_desk)
    await started.wait()
    reconnect = init_integration.runtime_data._reconnect_task

    await init_integration.runtime_data.async_shutdown()

    assert reconnect.cancelled()


async def test_shutdown_without_disconnect_logs_nothing(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the disconnect caused by unloading is not reported as an outage."""
    await init_integration.runtime_data.async_shutdown()
    disconnect_desk(mock_desk)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert "is unavailable" not in caplog.text
    mock_desk.connect.assert_awaited_once()


async def test_device_info_before_connecting(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the device info falls back to defaults before the desk reports any."""
    coordinator = DeskUpdateCoordinator(hass, mock_config_entry)

    assert coordinator.get_device_info() == dr.DeviceInfo(
        identifiers={(DOMAIN, ADDRESS)},
        connections={(dr.CONNECTION_BLUETOOTH, ADDRESS)},
        name="Desky Desk",
        manufacturer="Desky",
        model="Standing Desk",
    )


async def test_device_info_from_desk(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the device info carries everything the desk reported."""
    assert init_integration.runtime_data.get_device_info() == dr.DeviceInfo(
        identifiers={(DOMAIN, ADDRESS)},
        connections={(dr.CONNECTION_BLUETOOTH, ADDRESS)},
        name="Desky Desk",
        manufacturer="Test Manufacturer",
        model="Test Model",
        serial_number="TEST123456",
        hw_version="1.0",
        sw_version="2.1.0",
    )


async def test_device_info_without_device_information_service(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test the device info falls back when the desk reports no device info."""
    notify_desk(mock_desk, **NO_DEVICE_INFO)

    assert init_integration.runtime_data.get_device_info() == dr.DeviceInfo(
        identifiers={(DOMAIN, ADDRESS)},
        connections={(dr.CONNECTION_BLUETOOTH, ADDRESS)},
        name="Desky Desk",
        manufacturer="Desky",
        model="Standing Desk",
    )


async def test_device_info_ignores_placeholders(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test placeholder strings some desks report are left out of the device info."""
    notify_desk(
        mock_desk,
        manufacturer_name="Manufacturer Name",
        model_number="L-BTMEB95",
        serial_number="Serial Number",
        hardware_revision="Hardware Revision",
        firmware_revision="Rev01",
    )

    assert init_integration.runtime_data.get_device_info() == dr.DeviceInfo(
        identifiers={(DOMAIN, ADDRESS)},
        connections={(dr.CONNECTION_BLUETOOTH, ADDRESS)},
        name="Desky Desk",
        manufacturer="Desky",
        model="L-BTMEB95",
        sw_version="Rev01",
    )


async def test_update_device_registry(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test only the fields the desk reported are written to the registry."""
    notify_desk(
        mock_desk,
        manufacturer_name=None,
        model_number="Model Number",
        serial_number="SN42",
        hardware_revision="2.0",
        firmware_revision="3.0.0",
    )

    await init_integration.runtime_data.async_update_device_registry()

    devices = dr.async_entries_for_config_entry(
        device_registry, init_integration.entry_id
    )
    assert len(devices) == 1
    device = devices[0]
    assert device.connections == {(dr.CONNECTION_BLUETOOTH, ADDRESS)}
    # Fields the desk did not report keep their earlier values
    assert device.manufacturer == "Test Manufacturer"
    assert device.model == "Test Model"
    assert device.serial_number == "SN42"
    assert device.hw_version == "2.0"
    assert device.sw_version == "3.0.0"


async def test_update_device_registry_only_placeholders(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test nothing is written when the desk reports only placeholders."""
    notify_desk(
        mock_desk,
        manufacturer_name="Manufacturer Name",
        model_number=None,
        serial_number="Serial Number",
        hardware_revision="Hardware Revision",
        firmware_revision="Firmware Revision",
        software_revision="1.5.2",
    )
    device = _desk_device(hass, init_integration)

    with patch.object(
        device_registry,
        "async_get_or_create",
        wraps=device_registry.async_get_or_create,
    ) as get_or_create:
        await init_integration.runtime_data.async_update_device_registry()

    get_or_create.assert_not_called()
    assert _desk_device(hass, init_integration) == device


async def test_update_device_registry_error_is_logged(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    init_integration: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a registry failure is logged rather than raised."""
    with patch.object(
        device_registry, "async_get_or_create", side_effect=ValueError("registry boom")
    ):
        await init_integration.runtime_data.async_update_device_registry()

    assert "Failed to update device registry: registry boom" in caplog.text


async def test_update_device_registry_before_connecting(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the registry is left alone before the desk is connected."""
    coordinator = DeskUpdateCoordinator(hass, mock_config_entry)

    with patch.object(device_registry, "async_get_or_create") as get_or_create:
        await coordinator.async_update_device_registry()

    get_or_create.assert_not_called()
