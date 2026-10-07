"""Tests for the Desky Desk integration."""

from dataclasses import dataclass, replace
from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothServiceInfoBleak,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.desky_desk.coordinator import DeskData

CONNECTED_DESK = DeskData(
    is_connected=True,
    height_cm=80.0,
    collision_detected=False,
    is_moving=False,
    movement_direction=None,
    light_color=1,  # White
    brightness=50,
    lighting_enabled=True,
    vibration_enabled=True,
    vibration_intensity=75,
    lock_status=False,
    sensitivity_level=2,  # Medium
    height_limit_upper=120.0,
    height_limit_lower=65.0,
    limits_enabled=True,
    touch_mode=0,  # One press
    unit_preference="cm",
    manufacturer_name="Test Manufacturer",
    model_number="Test Model",
    serial_number="TEST123456",
    hardware_revision="1.0",
    firmware_revision="2.1.0",
    software_revision="1.5.2",
)


def desk_data(**changes: Any) -> DeskData:
    """Return coordinator data for a connected desk, with optional changes."""
    return replace(CONNECTED_DESK, **changes)


async def set_desk_state(
    hass: HomeAssistant, entry: MockConfigEntry, **changes: Any
) -> None:
    """Change the desk's coordinator data and wait for entities to update."""
    coordinator = entry.runtime_data
    coordinator.async_set_updated_data(replace(coordinator.data, **changes))
    await hass.async_block_till_done()


def notify_desk(desk: MagicMock, **changes: Any) -> None:
    """Change the mocked desk's state and send a height notification."""
    for key, value in changes.items():
        setattr(desk, key, value)
    callback = desk.register_notification_callback.call_args.args[0]
    callback(desk.height_cm, desk.collision_detected, desk.is_moving)


def disconnect_desk(desk: MagicMock) -> None:
    """Mark the mocked desk disconnected and run its disconnect callback."""
    desk.is_connected = False
    desk.register_disconnect_callback.call_args.args[0]()


def make_service_info(
    address: str = "AA:BB:CC:DD:EE:FF", name: str = "Desky", device: Any = None
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
        device=device if device is not None else MagicMock(),
        advertisement=MagicMock(),
        connectable=True,
        time=0,
        tx_power=None,
        raw=None,
    )


@dataclass
class BluetoothCallbacks:
    """The desk's Bluetooth stack callbacks, registered through patched helpers."""

    register: MagicMock
    track_unavailable: MagicMock

    def advertise(self, ble_device: Any = None) -> None:
        """Deliver an advertisement from the desk, optionally via a given route."""
        callback = self.register.call_args.args[1]
        callback(make_service_info(device=ble_device), BluetoothChange.ADVERTISEMENT)

    def lose_sight(self) -> None:
        """Report that the Bluetooth stack no longer sees the desk."""
        self.track_unavailable.call_args.args[1](make_service_info())
