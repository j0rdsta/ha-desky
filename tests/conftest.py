"""Common test fixtures for Desky Desk integration tests."""

from __future__ import annotations

from collections.abc import Generator
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

from . import make_service_info


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
def mock_discovered_service_info(mock_service_info):
    """Mock the async_discovered_service_info function."""
    with patch(
        "custom_components.desky_desk.config_flow.async_discovered_service_info",
        return_value=[mock_service_info],
    ) as mock:
        yield mock


@pytest.fixture
def mock_coordinator_data():
    """Return mock coordinator data."""
    return {
        "height_cm": 80.0,
        "collision_detected": False,
        "is_moving": False,
        "is_connected": True,
        "movement_direction": None,
        # New device features
        "light_color": 1,  # White
        "brightness": 50,
        "lighting_enabled": True,
        "vibration_enabled": True,
        "vibration_intensity": 75,
        "lock_status": False,
        "sensitivity_level": 2,  # Medium
        "height_limit_upper": 120.0,
        "height_limit_lower": 65.0,
        "limits_enabled": True,
        "touch_mode": 0,  # One press
        "unit_preference": "cm",
        # Device information from Device Information Service (0x180A)
        "manufacturer_name": "Test Manufacturer",
        "model_number": "Test Model",
        "serial_number": "TEST123456",
        "hardware_revision": "1.0",
        "firmware_revision": "2.1.0",
        "software_revision": "1.5.2",
    }


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> MockConfigEntry:
    """Set up the Desky Desk integration in Home Assistant."""
    # First, mock the bluetooth and bluetooth_adapters components to avoid setup failures
    with (
        patch("homeassistant.components.bluetooth.async_setup", return_value=True),
        patch(
            "homeassistant.components.bluetooth_adapters.async_setup", return_value=True
        ),
        patch(
            "homeassistant.components.bluetooth.async_ble_device_from_address"
        ) as mock_ble_device_from_address,
    ):
        # Mock the BLE device
        mock_ble_device = MagicMock()
        mock_ble_device.address = "AA:BB:CC:DD:EE:FF"
        mock_ble_device.name = "Desky"
        mock_ble_device_from_address.return_value = mock_ble_device

        # Add the config entry
        mock_config_entry.add_to_hass(hass)

        # Mock the DeskBLEDevice; the integration runs a real coordinator
        with (
            patch(
                "custom_components.desky_desk.bluetooth.establish_connection"
            ) as mock_establish_connection,
            patch(
                "custom_components.desky_desk.coordinator.DeskBLEDevice"
            ) as mock_desk_device,
        ):
            # Mock the BLE client
            mock_client = MagicMock()
            mock_client.is_connected = True
            mock_establish_connection.return_value = mock_client

            # Mock the device
            mock_device_instance = mock_desk_device.return_value
            mock_device_instance.name = "Desky Desk"
            mock_device_instance.connect = AsyncMock(return_value=True)
            mock_device_instance.disconnect = AsyncMock()
            mock_device_instance.is_connected = True
            mock_device_instance.height_cm = 80.0
            mock_device_instance.collision_detected = False
            mock_device_instance.is_moving = False
            mock_device_instance.get_status = AsyncMock()
            mock_device_instance.register_notification_callback = MagicMock()
            mock_device_instance.register_disconnect_callback = MagicMock()

            # Add all the new device methods
            mock_device_instance.set_lighting = AsyncMock(return_value=True)
            mock_device_instance.get_lighting_status = AsyncMock(return_value=True)
            mock_device_instance.set_light_color = AsyncMock(return_value=True)
            mock_device_instance.get_light_color = AsyncMock(return_value=True)
            mock_device_instance.set_brightness = AsyncMock(return_value=True)
            mock_device_instance.get_brightness = AsyncMock(return_value=True)
            mock_device_instance.set_vibration = AsyncMock(return_value=True)
            mock_device_instance.get_vibration_status = AsyncMock(return_value=True)
            mock_device_instance.set_vibration_intensity = AsyncMock(return_value=True)
            mock_device_instance.get_vibration_intensity = AsyncMock(return_value=True)
            mock_device_instance.set_lock_status = AsyncMock(return_value=True)
            mock_device_instance.get_lock_status = AsyncMock(return_value=True)
            mock_device_instance.set_sensitivity = AsyncMock(return_value=True)
            mock_device_instance.get_sensitivity = AsyncMock(return_value=True)
            mock_device_instance.set_touch_mode = AsyncMock(return_value=True)
            mock_device_instance.set_unit = AsyncMock(return_value=True)
            mock_device_instance.set_height_limit_upper = AsyncMock(return_value=True)
            mock_device_instance.set_height_limit_lower = AsyncMock(return_value=True)
            mock_device_instance.get_limits = AsyncMock(return_value=True)
            mock_device_instance.move_to_height = AsyncMock(return_value=True)

            # Setup the integration using the proper setup flow
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

    return mock_config_entry


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
