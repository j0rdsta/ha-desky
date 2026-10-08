"""Common test fixtures for Desky Desk integration tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

from bleak import BleakClient
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

from custom_components.desky_desk.const import DOMAIN
from custom_components.desky_desk.coordinator import DeskData

from . import BluetoothCallbacks, desk_data, make_service_info


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override setup entry."""
    with patch(
        "custom_components.desky_desk.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="AA:BB:CC:DD:EE:FF",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        },
        title="Desky Desk",
    )


@pytest.fixture
def mock_ble_device() -> MagicMock:
    """Return a mock BLE device."""
    device = MagicMock()
    device.address = "AA:BB:CC:DD:EE:FF"
    device.name = "Desky"
    return device


@pytest.fixture
def mock_service_info() -> BluetoothServiceInfoBleak:
    """Return a mock Bluetooth service info."""
    return make_service_info()


@pytest.fixture
def mock_bleak_client() -> MagicMock:
    """Return a mock Bleak client shaped like the current Bleak API."""
    client = MagicMock(spec=BleakClient)
    client.is_connected = True
    client.connect = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()

    # Bleak exposes discovered services through the `services` property
    mock_service = MagicMock()
    mock_service.uuid = "0000fe60-0000-1000-8000-00805f9b34fb"
    mock_char1 = MagicMock()
    mock_char1.uuid = "0000fe61-0000-1000-8000-00805f9b34fb"
    mock_char1.properties = ["write"]
    mock_char2 = MagicMock()
    mock_char2.uuid = "0000fe62-0000-1000-8000-00805f9b34fb"
    mock_char2.properties = ["notify"]
    mock_service.characteristics = [mock_char1, mock_char2]
    client.services = [mock_service]

    return client


@pytest.fixture
def mock_device_info_service():
    """Return a mock Device Information Service for BLE."""
    service = MagicMock()
    service.uuid = "0000180a-0000-1000-8000-00805f9b34fb"

    # Create mock characteristics
    characteristics = []
    device_info_chars = [
        ("00002a29-0000-1000-8000-00805f9b34fb", b"Test Manufacturer"),  # Manufacturer
        ("00002a24-0000-1000-8000-00805f9b34fb", b"Test Model"),  # Model
        ("00002a25-0000-1000-8000-00805f9b34fb", b"TEST123456"),  # Serial
        ("00002a27-0000-1000-8000-00805f9b34fb", b"1.0"),  # Hardware
        ("00002a26-0000-1000-8000-00805f9b34fb", b"2.1.0"),  # Firmware
        ("00002a28-0000-1000-8000-00805f9b34fb", b"1.5.2"),  # Software
    ]

    for uuid, data in device_info_chars:
        char = MagicMock()
        char.uuid = uuid
        char.properties = ["read"]
        char.read_data = data
        characteristics.append(char)

    service.characteristics = characteristics
    return service


@pytest.fixture
def mock_bleak_client_with_device_info(mock_bleak_client, mock_device_info_service):
    """Return a mock Bleak client with Device Information Service."""
    mock_bleak_client.services = [
        *mock_bleak_client.services,
        mock_device_info_service,
    ]

    # Mock read_gatt_char to return device info data
    async def mock_read_char(char_uuid):
        for char in mock_device_info_service.characteristics:
            if char.uuid.lower() == char_uuid.lower():
                return char.read_data
        return b""

    mock_bleak_client.read_gatt_char = AsyncMock(side_effect=mock_read_char)
    return mock_bleak_client


@pytest.fixture
def mock_establish_connection(mock_bleak_client):
    """Mock the establish_connection function."""
    with patch(
        "custom_components.desky_desk.bluetooth.establish_connection",
        return_value=mock_bleak_client,
    ) as mock:
        yield mock


@pytest.fixture
def mock_bluetooth_device_from_address(mock_ble_device):
    """Mock the async_ble_device_from_address function."""
    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=mock_ble_device,
    ) as mock:
        yield mock


@pytest.fixture
def mock_bluetooth() -> Generator[None]:
    """Skip setting up Home Assistant's Bluetooth stack.

    On Linux the real setup connects to BlueZ over D-Bus, and Home Assistant
    2025.10 leaves that socket open, which fails the test with a ResourceWarning.
    """
    with (
        patch("homeassistant.components.bluetooth.async_setup", return_value=True),
        patch(
            "homeassistant.components.bluetooth_adapters.async_setup",
            return_value=True,
        ),
    ):
        yield


@pytest.fixture
def mock_bluetooth_callbacks(mock_bluetooth: None) -> Generator[BluetoothCallbacks]:
    """Capture the advertisement and unavailable callbacks the desk registers."""
    with (
        patch(
            "homeassistant.components.bluetooth.async_register_callback",
            return_value=MagicMock(),
        ) as register,
        patch(
            "homeassistant.components.bluetooth.async_track_unavailable",
            return_value=MagicMock(),
        ) as track_unavailable,
    ):
        yield BluetoothCallbacks(register, track_unavailable)


@pytest.fixture
def mock_desk(mock_bluetooth_callbacks: BluetoothCallbacks) -> Generator[MagicMock]:
    """Patch the desk's BLE device with a connected desk and return it.

    The values match `mock_coordinator_data`. Use `notify_desk()` or
    `disconnect_desk()` to push a change to the coordinator.
    """
    with patch(
        "custom_components.desky_desk.coordinator.DeskBLEDevice", autospec=True
    ) as desk_class:
        desk = desk_class.return_value
        desk.name = "Desky Desk"
        desk.address = "AA:BB:CC:DD:EE:FF"
        desk.connect.return_value = True
        for key, value in asdict(desk_data()).items():
            setattr(desk, key, value)
        yield desk


@pytest.fixture
def mock_coordinator_data() -> DeskData:
    """Return coordinator data for a connected desk."""
    return desk_data()


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_desk: MagicMock,
) -> AsyncGenerator[MockConfigEntry]:
    """Set up the Desky Desk integration with a connected desk."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.bluetooth.async_ble_device_from_address",
        return_value=MagicMock(address="AA:BB:CC:DD:EE:FF"),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        yield mock_config_entry


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in every test."""


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return a snapshot assertion that uses the Home Assistant extension.

    The harness defines the same override, but with syrupy 6 the plain syrupy
    fixture wins, so snapshots would land in `__snapshots__` on newer pins.
    """
    return snapshot.use_extension(HomeAssistantSnapshotExtension)
