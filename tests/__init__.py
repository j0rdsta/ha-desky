"""Tests for the Desky Desk integration."""

from unittest.mock import MagicMock

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak


def make_service_info(
    address: str = "AA:BB:CC:DD:EE:FF", name: str = "Desky"
) -> BluetoothServiceInfoBleak:
    """Build Bluetooth service info for a discovered desk."""
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-50,
        manufacturer_data={},
        service_data={},
        service_uuids=[],
        source="local",
        device=MagicMock(),
        advertisement=MagicMock(),
        connectable=True,
        time=0,
        tx_power=None,
        raw=None,
    )
