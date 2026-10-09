"""Tests for the Desky Desk integration."""

import asyncio
from dataclasses import dataclass, replace
import heapq
from typing import Any
from unittest.mock import MagicMock

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.components.bluetooth import (
    MONOTONIC_TIME,
    SOURCE_LOCAL,
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
    lock_status=False,
    sensitivity_level=2,  # Medium
    height_limit_upper=120.0,
    height_limit_lower=65.0,
    limits_enabled=True,
    touch_mode=0,  # One press
    unit_preference="cm",
    limit_range=(60.0, 124.0),
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


def desk_response(header: bytes, *payload: int) -> bytearray:
    """Build a desk response frame: header, payload, checksum and terminator."""
    checksum = (sum(header[2:]) + sum(payload)) & 0xFF
    return bytearray([*header, *payload, checksum, 0x7E])


def deliver_frame(client: MagicMock, frame: bytearray) -> None:
    """Pass a frame to the real desk code, as the desk does over Bluetooth.

    For tests using `desk_client`, where the desk code has subscribed to the
    mocked Bleak client's notifications.
    """
    handler = client.start_notify.call_args.args[1]
    handler(None, frame)


def disconnect_desk(desk: MagicMock) -> None:
    """Mark the mocked desk disconnected and run its disconnect callback."""
    desk.is_connected = False
    desk.register_disconnect_callback.call_args.args[0]()


def make_service_info(
    address: str = "AA:BB:CC:DD:EE:FF", name: str = "Desky", device: Any = None
) -> BluetoothServiceInfoBleak:
    """Build what Home Assistant's Bluetooth stack reports for a desk, seen now."""
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-50,
        manufacturer_data={},
        service_data={},
        service_uuids=[],
        source=SOURCE_LOCAL,
        device=device if device is not None else BLEDevice(address, name, {}),
        advertisement=AdvertisementData(
            local_name=name,
            manufacturer_data={},
            service_data={},
            service_uuids=[],
            tx_power=None,
            rssi=-50,
            platform_data=(),
        ),
        connectable=True,
        time=MONOTONIC_TIME(),
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


async def settle() -> None:
    """Let every task that is ready run until it waits again."""
    for _ in range(20):
        await asyncio.sleep(0)


class FakeClock:
    """A virtual clock for the desk's frame timing.

    With auto set, every pause passes at once and the clock jumps past it, so
    tests that do not look at timing never wait. With auto off, a pause lasts
    until advance() moves the clock past it, so a test decides exactly when
    each timed frame goes out.

    With auto set, the sequencer's settle cap (WRITE_SETTLE_SECONDS) passes at
    once too, so a write cancelled mid-flight is given up straight away. A
    test that cancels during a write and expects it to finish must turn auto
    off.
    """

    def __init__(self) -> None:
        """Start the clock at zero, passing pauses at once."""
        self.now = 0.0
        self.auto = True
        self._pauses: list[tuple[float, int, asyncio.Future[None]]] = []
        self._count = 0

    def time(self) -> float:
        """Return the virtual time in seconds."""
        return self.now

    async def sleep(self, seconds: float) -> None:
        """Pause until the virtual clock reaches the end of the pause."""
        if self.auto:
            self.now += seconds
            await asyncio.sleep(0)
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._count += 1
        heapq.heappush(self._pauses, (self.now + seconds, self._count, future))
        await future

    async def advance(self, seconds: float) -> None:
        """Move the clock on, ending each pause in turn at its own time."""
        target = self.now + seconds
        await settle()
        while self._pauses and self._pauses[0][0] <= target + 1e-9:
            wake, _, future = heapq.heappop(self._pauses)
            self.now = max(self.now, wake)
            if not future.done():
                future.set_result(None)
            await settle()
        self.now = target
        await settle()


def record_frames(client: MagicMock, clock: FakeClock) -> list[tuple[float, str]]:
    """Record each frame written to the client, with its virtual time in seconds."""
    frames: list[tuple[float, str]] = []

    async def _write(_uuid: str, data: bytes, *args: Any, **kwargs: Any) -> None:
        frames.append((round(clock.now, 3), bytes(data).hex()))

    client.write_gatt_char.side_effect = _write
    return frames
