"""Test the Desky Desk update coordinator.

Setup, retry and unload are covered in `test_init.py`. These tests drive a
loaded entry through Home Assistant time and the mocked desk's callbacks.
"""

from __future__ import annotations

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

from custom_components.desky_desk.const import (
    DOMAIN,
    RECONNECT_INTERVAL_SECONDS,
    UPDATE_INTERVAL_SECONDS,
)
from custom_components.desky_desk.coordinator import DeskData, DeskUpdateCoordinator

from . import desk_data, disconnect_desk, notify_desk

ADDRESS = "AA:BB:CC:DD:EE:FF"
COORDINATOR_LOGGER = "custom_components.desky_desk.coordinator"
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
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: int
) -> None:
    """Move Home Assistant time forward and run whatever became due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


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


async def _start_failing_reconnect(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    desk: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Disconnect the desk and let a poll start a reconnect that keeps failing."""
    desk.connect.return_value = False
    disconnect_desk(desk)
    await _poll(hass, freezer)
    assert len(entry._background_tasks) == 1


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


async def test_poll_while_disconnected_starts_one_reconnect(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test polling a disconnected desk fails and starts a single reconnect loop."""
    caplog.set_level(logging.DEBUG, logger=COORDINATOR_LOGGER)
    coordinator = init_integration.runtime_data

    await _start_failing_reconnect(hass, init_integration, mock_desk, freezer)

    assert not coordinator.last_update_success
    assert all(
        state == STATE_UNAVAILABLE for state in _entity_states(hass, init_integration)
    )
    # The poll does not ask a disconnected desk for its status
    mock_desk.get_status.assert_awaited_once()
    assert mock_desk.connect.await_count == 2
    assert "Connection attempt failed" in caplog.text
    (reconnect,) = init_integration._background_tasks
    assert not reconnect.done()

    # Later polls leave the running reconnect alone
    await _poll(hass, freezer)
    await _poll(hass, freezer)

    assert init_integration._background_tasks == {reconnect}
    assert not coordinator.last_update_success


async def test_reconnect_restores_desk(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a successful reconnect refreshes the data and the device registry."""
    await _start_failing_reconnect(hass, init_integration, mock_desk, freezer)

    _reconnect_succeeds(mock_desk)
    # The desk reports new firmware once it is back
    mock_desk.firmware_revision = "2.2.0"
    mock_desk.height_cm = 72.0
    await _advance(hass, freezer, RECONNECT_INTERVAL_SECONDS)
    await hass.async_block_till_done(wait_background_tasks=True)

    coordinator = init_integration.runtime_data
    assert coordinator.data == desk_data(height_cm=72.0, firmware_revision="2.2.0")
    assert coordinator.last_update_success
    assert not init_integration._background_tasks
    assert STATE_UNAVAILABLE not in _entity_states(hass, init_integration)
    assert _desk_device(hass, init_integration).sw_version == "2.2.0"
    # The reconnect used the BLE device Home Assistant currently sees
    assert mock_desk._ble_device.address == ADDRESS


async def test_reconnect_retries_after_missing_device_and_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the reconnect loop keeps going when the desk is absent or errors."""
    caplog.set_level(logging.DEBUG, logger=COORDINATOR_LOGGER)
    mock_desk.connect.side_effect = OSError("adapter busy")
    disconnect_desk(mock_desk)

    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        await _poll(hass, freezer)
    assert f"BLE device not found at address {ADDRESS}" in caplog.text
    assert mock_desk.connect.await_count == 1

    await _advance(hass, freezer, RECONNECT_INTERVAL_SECONDS)
    assert "Reconnection failed: adapter busy" in caplog.text
    assert mock_desk.connect.await_count == 2
    assert len(init_integration._background_tasks) == 1

    _reconnect_succeeds(mock_desk)
    await _advance(hass, freezer, RECONNECT_INTERVAL_SECONDS)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_desk.connect.await_count == 3
    assert init_integration.runtime_data.data == desk_data()
    assert not init_integration._background_tasks


async def test_reconnect_stops_when_desk_is_back(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the reconnect loop ends without connecting once the desk is connected."""
    await _start_failing_reconnect(hass, init_integration, mock_desk, freezer)

    mock_desk.is_connected = True
    await _advance(hass, freezer, RECONNECT_INTERVAL_SECONDS)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_desk.connect.await_count == 2
    assert not init_integration._background_tasks


async def test_shutdown_cancels_reconnect_and_disconnects(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test shutting the coordinator down stops reconnecting and disconnects."""
    await _start_failing_reconnect(hass, init_integration, mock_desk, freezer)
    (reconnect,) = init_integration._background_tasks

    await init_integration.runtime_data.async_shutdown()
    await hass.async_block_till_done()

    assert reconnect.cancelled()
    assert not init_integration._background_tasks
    mock_desk.disconnect.assert_awaited_once()

    # Nothing tries to reconnect afterwards
    await _advance(hass, freezer, RECONNECT_INTERVAL_SECONDS)
    assert mock_desk.connect.await_count == 2
    assert not init_integration._background_tasks


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
