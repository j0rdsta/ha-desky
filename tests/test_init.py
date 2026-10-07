"""Test Desky Desk config entry setup, retry, unload and the desk's device entry."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.bluetooth import BluetoothScanningMode
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.desky_desk import PLATFORMS
from custom_components.desky_desk.const import DOMAIN, RECONNECT_BACKOFF_MAX_SECONDS
from custom_components.desky_desk.coordinator import DeskUpdateCoordinator

from . import BluetoothCallbacks, disconnect_desk

ADDRESS = "AA:BB:CC:DD:EE:FF"


def _desk_entity_states(hass: HomeAssistant, entry: MockConfigEntry) -> list[str]:
    """Return the states of the entry's entities."""
    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    return [
        state.state
        for entity in entries
        if (state := hass.states.get(entity.entity_id)) is not None
    ]


async def test_setup_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test a reachable desk loads with all its entities available."""
    assert init_integration.state is ConfigEntryState.LOADED
    assert isinstance(init_integration.runtime_data, DeskUpdateCoordinator)
    mock_desk.connect.assert_awaited_once()

    states = _desk_entity_states(hass, init_integration)
    assert len(states) == 21
    assert STATE_UNAVAILABLE not in states


async def test_setup_retry_when_desk_not_found(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test setup retries with a reason when the desk is not advertising."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert mock_config_entry.reason == (
        f"Could not find the desk at {ADDRESS}. "
        "Make sure it is powered on and in Bluetooth range"
    )
    mock_desk.connect.assert_not_called()
    assert _desk_entity_states(hass, mock_config_entry) == []


async def test_setup_retry_when_connection_refused(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test setup retries and cleans up when the desk refuses the connection."""
    mock_desk.connect.return_value = False
    mock_config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=MagicMock(address=ADDRESS),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert mock_config_entry.reason == f"Could not connect to the desk at {ADDRESS}"
    assert _desk_entity_states(hass, mock_config_entry) == []
    # The failed attempt releases the desk before the next retry
    mock_desk.disconnect.assert_awaited_once()


async def test_setup_retry_succeeds_when_desk_comes_into_range(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a later retry loads the entry once the desk is connectable."""
    mock_desk.connect.return_value = False
    mock_config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=MagicMock(address=ADDRESS),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY

        mock_desk.connect.return_value = True
        freezer.tick(timedelta(minutes=1))
        async_fire_time_changed(hass)
        # Home Assistant runs the retry as a background task
        await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    states = _desk_entity_states(hass, mock_config_entry)
    assert len(states) == 21
    assert STATE_UNAVAILABLE not in states


async def test_unload_while_connected(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test unloading closes the connection and leaves no background work."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED
    mock_desk.disconnect.assert_awaited_once()
    assert not init_integration._background_tasks


async def test_unload_cancels_pending_reconnect(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_desk: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test unloading while a reconnect retry is pending cancels it cleanly."""
    mock_desk.connect.return_value = False
    disconnect_desk(mock_desk)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert all(
        state == STATE_UNAVAILABLE
        for state in _desk_entity_states(hass, init_integration)
    )

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED
    assert not init_integration._background_tasks
    mock_desk.disconnect.assert_awaited_once()

    # The retry that was waiting never runs
    freezer.tick(timedelta(seconds=RECONNECT_BACKOFF_MAX_SECONDS))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_desk.connect.await_count == 2


async def test_unload_releases_bluetooth_callbacks(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_bluetooth_callbacks: BluetoothCallbacks,
) -> None:
    """Test the advertisement and unavailable callbacks are removed on unload."""
    unregister = mock_bluetooth_callbacks.register.return_value
    untrack = mock_bluetooth_callbacks.track_unavailable.return_value
    _, _, matcher, mode = mock_bluetooth_callbacks.register.call_args.args
    assert matcher == {"address": ADDRESS, "connectable": True}
    assert mode is BluetoothScanningMode.ACTIVE
    assert mock_bluetooth_callbacks.track_unavailable.call_args.kwargs == {
        "connectable": True
    }

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    unregister.assert_called_once_with()
    untrack.assert_called_once_with()


async def test_failed_setup_registers_no_bluetooth_callbacks(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
    mock_bluetooth_callbacks: BluetoothCallbacks,
) -> None:
    """Test a desk that cannot be connected at setup is not watched for."""
    mock_desk.connect.return_value = False
    mock_config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=MagicMock(address=ADDRESS),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_bluetooth_callbacks.register.assert_not_called()
    mock_bluetooth_callbacks.track_unavailable.assert_not_called()


async def test_reload(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_desk: MagicMock
) -> None:
    """Test reloading sets up again from a clean state."""
    coordinator = init_integration.runtime_data
    entity_count = len(hass.states.async_all())

    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.LOADED
    assert init_integration.runtime_data is not coordinator
    assert len(hass.states.async_all()) == entity_count
    assert mock_desk.connect.await_count == 2
    mock_desk.disconnect.assert_awaited_once()


async def test_platforms() -> None:
    """Test every entity platform is forwarded."""
    assert set(PLATFORMS) == {
        Platform.BINARY_SENSOR,
        Platform.BUTTON,
        Platform.COVER,
        Platform.LIGHT,
        Platform.NUMBER,
        Platform.SELECT,
        Platform.SENSOR,
        Platform.SWITCH,
    }


async def test_device_has_bluetooth_connection(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Test the desk's device records its Bluetooth address as a connection."""
    devices = dr.async_entries_for_config_entry(
        device_registry, init_integration.entry_id
    )
    assert len(devices) == 1
    device = devices[0]
    assert device.identifiers == {(DOMAIN, ADDRESS)}
    assert device.connections == {(dr.CONNECTION_BLUETOOTH, ADDRESS)}
    assert device.name == "Desky Desk"
    assert device.manufacturer == "Test Manufacturer"
    assert device.model == "Test Model"
    assert device.serial_number == "TEST123456"
    assert device.hw_version == "1.0"
    assert device.sw_version == "2.1.0"


async def test_upgrade_keeps_one_device(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
) -> None:
    """Test an existing device without a connection gains it instead of being duplicated."""
    mock_config_entry.add_to_hass(hass)
    # Earlier releases created the device with only the identifier
    existing = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, ADDRESS)},
        name="Desky Desk",
        manufacturer="Desky",
        model="Standing Desk",
    )
    assert not existing.connections

    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=MagicMock(address=ADDRESS),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    devices = dr.async_entries_for_config_entry(
        device_registry, mock_config_entry.entry_id
    )
    assert [device.id for device in devices] == [existing.id]
    assert devices[0].connections == {(dr.CONNECTION_BLUETOOTH, ADDRESS)}
