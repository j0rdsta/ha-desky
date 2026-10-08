"""Bluetooth communication for Desky Desk."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import time
from typing import Any

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .const import (
    BRIGHTNESS_RESPONSE_HEADER,
    CM_PER_INCH,
    COMMAND_CLEAR_LIMITS,
    COMMAND_GET_BRIGHTNESS,
    COMMAND_GET_LIGHT_COLOR,
    COMMAND_GET_LIGHTING,
    COMMAND_GET_LIMITS,
    COMMAND_GET_LOCK_STATUS,
    COMMAND_GET_SENSITIVITY,
    COMMAND_GET_STATUS,
    COMMAND_GET_VIBRATION,
    COMMAND_GET_VIBRATION_INTENSITY,
    COMMAND_HANDSHAKE,
    COMMAND_MEMORY_1,
    COMMAND_MEMORY_2,
    COMMAND_MEMORY_3,
    COMMAND_MEMORY_4,
    COMMAND_MOVE_DOWN,
    COMMAND_MOVE_UP,
    COMMAND_STOP,
    DEVICE_INFORMATION_SERVICE_UUID,
    DISPLAY_UNITS,
    FIRMWARE_REVISION_CHAR_UUID,
    HARDWARE_REVISION_CHAR_UUID,
    HEIGHT_NOTIFICATION_HEADER,
    LIGHT_COLOR_RESPONSE_HEADER,
    LIGHTING_RESPONSE_HEADER,
    LIMIT_LOWER_RESPONSE_HEADER,
    LIMIT_STATUS_RESPONSE_HEADER,
    LIMIT_UPPER_RESPONSE_HEADER,
    LOCK_STATUS_RESPONSE_HEADER,
    MANUFACTURER_NAME_CHAR_UUID,
    MAX_HEIGHT,
    MIN_HEIGHT,
    MODEL_NUMBER_CHAR_UUID,
    NOTIFY_CHARACTERISTIC_UUID,
    SENSITIVITY_RESPONSE_HEADER,
    SERIAL_NUMBER_CHAR_UUID,
    SOFTWARE_REVISION_CHAR_UUID,
    STATUS_NOTIFICATION_HEADER,
    TOUCH_MODE_RESPONSE_HEADER,
    TOUCH_MODES,
    UNIT_RESPONSE_HEADER,
    VIBRATION_INTENSITY_RESPONSE_HEADER,
    VIBRATION_RESPONSE_HEADER,
    WRITE_CHARACTERISTIC_UUID,
)

_LOGGER = logging.getLogger(__name__)

# Connection attempts bleak-retry-connector makes before giving up
CONNECT_MAX_ATTEMPTS = 3

# Headers of this many recent runs of notifications are kept for diagnostics. A
# run is consecutive frames with the same header: an idle desk streams status
# frames, which would otherwise push out the replies a bug report needs.
RECENT_NOTIFICATION_HEADERS = 20

# Auto-clear collision after this many seconds
COLLISION_AUTO_CLEAR_SECONDS = 10.0

# A height change within this band is reading jitter: it never starts a movement
# and never counts as a reversal. Measured on hardware: no drift at all while
# idle, up to 0.3 cm of settling after a move, and one inch-mode count is 0.254 cm.
HEIGHT_JITTER_CM = 0.5

# A command that has not moved the desk within this time is dropped. Measured on
# hardware: 0.4-0.7 s from a command to the first height change.
COMMAND_EXPIRY_SECONDS = 5.0

# A movement has ended after this many readings without a height change
UNCHANGED_READINGS_TO_STOP = 3

# Heights the desk reports, in tenths of its display unit, are physically
# 60-130 cm or about 23.6-51.2 in. The ranges do not overlap, so a value below
# this split is in inches and one above it in centimetres.
UNIT_SPLIT = 55.0
# A decoded height outside this range fits neither unit
PLAUSIBLE_HEIGHT_CM = (MIN_HEIGHT - 5.0, MAX_HEIGHT + 5.0)


class DeskError(Exception):
    """A command could not be sent to the desk."""


class DeskNotConnectedError(DeskError):
    """The desk is not connected."""


class DeskCommandError(DeskError):
    """Writing a command to the desk failed."""


@dataclass(slots=True)
class _Movement:
    """A movement command in flight and, once the desk responds, its progress."""

    kind: str  # "continuous", "targeted" or "preset"
    direction: str | None  # commanded direction; unknown for presets
    target_height: float | None
    command_time: float
    command_height: float
    started: bool = False
    start_time: float = 0.0
    last_change_time: float = 0.0
    last_height: float = 0.0
    furthest_height: float = 0.0  # furthest point reached in the commanded direction
    unchanged_readings: int = 0
    velocities: list[float] = field(default_factory=list)  # recent speeds in cm/s

    def average_velocity(self) -> float:
        """Return the average of the recent velocity measurements."""
        if not self.velocities:
            return 0.0
        return sum(self.velocities) / len(self.velocities)


def _to_cm(value: float, unit: str) -> float:
    """Convert a height in the given display unit to centimetres."""
    return round(value * CM_PER_INCH, 1) if unit == "in" else value


def _plausible(height_cm: float) -> bool:
    """Return if a height is one the desk can physically report."""
    low, high = PLAUSIBLE_HEIGHT_CM
    return low <= height_cm <= high


class DeskBLEDevice:
    """Handle BLE communication with Desky desk."""

    def __init__(
        self, ble_device: BLEDevice, advertisement_data: dict[str, Any] | None = None
    ) -> None:
        """Initialize the desk device."""
        self._ble_device = ble_device
        self._advertisement_data = advertisement_data
        self._client: BleakClient | None = None
        # Commands go out one at a time, so concurrent callers never interleave
        self._write_lock = asyncio.Lock()
        self._height_cm: float = 0.0
        self._collision_detected: bool = False
        self._collision_time: float | None = None  # When collision was detected
        self._auto_clear_task: asyncio.Task | None = (
            None  # Task for auto-clearing collision
        )
        # The movement command in flight, if any; None once the movement ends
        self._movement: _Movement | None = None
        self._last_notification_time: float = 0.0  # Time of last height notification
        self._notification_callbacks: list[Callable[[float, bool, bool], None]] = []
        self._disconnect_callbacks: list[Callable[[], None]] = []
        # The first four bytes of recent frames, without the values they carry,
        # as [header, count] runs
        self._recent_headers: deque[list[Any]] = deque(
            maxlen=RECENT_NOTIFICATION_HEADERS
        )

        # New device features
        self._light_color: int | None = None
        self._brightness: int | None = None
        self._lighting_enabled: bool | None = None
        self._vibration_enabled: bool | None = None
        self._vibration_intensity: int | None = None
        self._lock_status: bool = False
        self._sensitivity_level: int | None = None
        self._height_limit_upper: float | None = None
        self._height_limit_lower: float | None = None
        # Whether each limit is set, as the limit status reports; None until reported
        self._height_limit_upper_set: bool | None = None
        self._height_limit_lower_set: bool | None = None
        self._touch_mode: int | None = None
        self._unit_preference: str | None = None  # "cm" or "in", as the desk reports
        # The unit the last height was actually in, for heights sent to the desk
        self._effective_unit: str | None = None

        # Device information from BLE Device Information Service (0x180A)
        self._manufacturer_name: str | None = None
        self._model_number: str | None = None
        self._serial_number: str | None = None
        self._hardware_revision: str | None = None
        self._firmware_revision: str | None = None
        self._software_revision: str | None = None

    @property
    def address(self) -> str:
        """Return the device address."""
        return self._ble_device.address

    @property
    def name(self) -> str:
        """Return the device name."""
        return self._ble_device.name or "Desky Desk"

    @property
    def height_cm(self) -> float:
        """Return current height in cm."""
        return self._height_cm

    @property
    def collision_detected(self) -> bool:
        """Return if collision was detected."""
        return self._collision_detected

    @property
    def is_moving(self) -> bool:
        """Return if the desk is moving in response to a command."""
        return self._movement is not None and self._movement.started

    @property
    def movement_direction(self) -> str | None:
        """Return the commanded movement direction ('up', 'down', or None)."""
        return self._movement.direction if self._movement else None

    @property
    def is_connected(self) -> bool:
        """Return if connected to the desk."""
        return self._client is not None and self._client.is_connected

    @property
    def light_color(self) -> int | None:
        """Return the current light color setting (1-7)."""
        return self._light_color

    @property
    def brightness(self) -> int | None:
        """Return the current brightness level (0-100)."""
        return self._brightness

    @property
    def lighting_enabled(self) -> bool | None:
        """Return if lighting is enabled."""
        return self._lighting_enabled

    @property
    def vibration_enabled(self) -> bool | None:
        """Return if vibration is enabled."""
        return self._vibration_enabled

    @property
    def vibration_intensity(self) -> int | None:
        """Return vibration intensity level."""
        return self._vibration_intensity

    @property
    def lock_status(self) -> bool:
        """Return if desk controls are locked."""
        return self._lock_status

    @property
    def sensitivity_level(self) -> int | None:
        """Return collision sensitivity level (1=High, 2=Medium, 3=Low)."""
        return self._sensitivity_level

    @property
    def height_limit_upper(self) -> float | None:
        """Return upper height limit in cm, or None when it is not set."""
        if self._height_limit_upper_set is False:
            return None
        return self._height_limit_upper

    @property
    def height_limit_lower(self) -> float | None:
        """Return lower height limit in cm, or None when it is not set."""
        if self._height_limit_lower_set is False:
            return None
        return self._height_limit_lower

    @property
    def limits_enabled(self) -> bool:
        """Return if any height limit is set."""
        return bool(self._height_limit_upper_set or self._height_limit_lower_set)

    @property
    def touch_mode(self) -> int | None:
        """Return touch mode (0=One press, 1=Press and hold)."""
        return self._touch_mode

    @property
    def unit_preference(self) -> str | None:
        """Return unit preference (cm or in)."""
        return self._unit_preference

    @property
    def manufacturer_name(self) -> str | None:
        """Return manufacturer name from device information service."""
        return self._manufacturer_name

    @property
    def model_number(self) -> str | None:
        """Return model number from device information service."""
        return self._model_number

    @property
    def serial_number(self) -> str | None:
        """Return serial number from device information service."""
        return self._serial_number

    @property
    def hardware_revision(self) -> str | None:
        """Return hardware revision from device information service."""
        return self._hardware_revision

    @property
    def firmware_revision(self) -> str | None:
        """Return firmware revision from device information service."""
        return self._firmware_revision

    @property
    def software_revision(self) -> str | None:
        """Return software revision from device information service."""
        return self._software_revision

    @property
    def recent_notification_headers(self) -> list[dict[str, Any]]:
        """Return the most recent runs of notification headers, oldest first."""
        return [
            {"header": header, "count": count} for header, count in self._recent_headers
        ]

    def register_notification_callback(
        self, callback: Callable[[float, bool, bool], None]
    ) -> None:
        """Register a callback for height/status notifications."""
        self._notification_callbacks.append(callback)

    def register_disconnect_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback for disconnection events."""
        self._disconnect_callbacks.append(callback)

    async def connect(self) -> bool:
        """Connect to the desk.

        Returns False when the desk could not be reached; the caller decides how
        loudly to report it. A link that comes up but cannot be set up is closed
        again first, so it does not keep an adapter or proxy connection slot.
        """
        if self.is_connected:
            return True

        _LOGGER.debug("Connecting to Desky desk at %s", self.address)

        try:
            # bleak-retry-connector picks the adapter or proxy that currently
            # hears the desk and waits for a free connection slot
            client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self.name,
                disconnected_callback=self._handle_disconnect,
                max_attempts=CONNECT_MAX_ATTEMPTS,
                ble_device_callback=self._get_ble_device,
            )
        except Exception as err:
            _LOGGER.debug("Failed to connect to desk at %s: %s", self.address, err)
            return False

        # Commands write through self._client, so setting up needs it set
        self._client = client
        try:
            await self._set_up_connection(client)
        except Exception as err:
            _LOGGER.debug("Failed to connect to desk at %s: %s", self.address, err)
            await self._release_client(client)
            return False

        _LOGGER.debug("Connected to Desky desk at %s", self.address)
        return True

    async def _set_up_connection(self, client: BleakClient) -> None:
        """Subscribe to the desk's notifications and ask for its state."""
        _LOGGER.debug("Connected, discovering services...")
        for service in client.services:
            _LOGGER.debug("Service: %s", service.uuid)
            for char in service.characteristics:
                _LOGGER.debug(
                    "  Characteristic: %s, properties: %s",
                    char.uuid,
                    char.properties,
                )

        await client.start_notify(NOTIFY_CHARACTERISTIC_UUID, self._handle_notification)

        # The handshake enables movement controls
        _LOGGER.debug("Sending handshake command...")
        await self._send_command(COMMAND_HANDSHAKE)
        await self.get_status()
        await self._query_device_capabilities()

        # Device Information Service (0x180A)
        await self._read_device_information()

    async def _release_client(self, client: BleakClient) -> None:
        """Close a link that could not be set up.

        The desk is reported disconnected here, once. The link's own disconnect
        callback then finds it is no longer current and is ignored.
        """
        if client is self._client:
            self._handle_disconnect(client)
        try:
            await client.disconnect()
        except Exception as err:
            _LOGGER.debug(
                "Error closing the connection to desk at %s: %s", self.address, err
            )

    def _get_ble_device(self) -> BLEDevice:
        """Return the latest BLE device, for retries during a connection attempt."""
        return self._ble_device

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Use a newly seen BLE device, so the next connection takes its route."""
        self._ble_device = ble_device

    async def disconnect(self) -> None:
        """Disconnect from the desk."""
        # Cancel any pending auto-clear task
        self._cancel_collision_auto_clear()

        if self._client:
            try:
                await self._client.stop_notify(NOTIFY_CHARACTERISTIC_UUID)
                await self._client.disconnect()
            except Exception as err:
                _LOGGER.debug("Error during disconnect: %s", err)
            finally:
                self._reset_link_state()

    async def _write(self, *commands: bytes) -> None:
        """Write commands to the desk in order, with no other write in between.

        The lock is held only for the writes, never while waiting on
        notifications, so a stop is never held up behind a running move.
        """
        async with self._write_lock:
            if not self.is_connected:
                raise DeskNotConnectedError("The desk is not connected")
            assert self._client is not None  # guaranteed by is_connected
            for command in commands:
                try:
                    await self._client.write_gatt_char(
                        WRITE_CHARACTERISTIC_UUID, command
                    )
                except Exception as err:
                    raise DeskCommandError(str(err) or type(err).__name__) from err

    async def _send_command(self, command: bytes) -> None:
        """Send a command to the desk."""
        await self._write(command)

    def _begin_movement(
        self, kind: str, direction: str | None, target_height: float | None = None
    ) -> None:
        """Record a movement command; the movement starts once the desk responds."""
        self._movement = _Movement(
            kind=kind,
            direction=direction,
            target_height=target_height,
            command_time=time.time(),
            command_height=self._height_cm,
        )

    def _end_movement(self) -> None:
        """Forget the current movement, so no later reading is attributed to it."""
        self._movement = None

    async def _send_awake_command(self, command: bytes) -> None:
        """Wake the desk with the handshake, then send a command.

        The desk's controller ignores commands while its display is asleep.
        """
        await self._write(COMMAND_HANDSHAKE, command)

    async def _send_movement_command(self, command: bytes) -> None:
        """Send a movement command, dropping the movement if the write fails."""
        try:
            await self._send_awake_command(command)
        except DeskError:
            self._end_movement()
            raise

    async def move_up(self) -> None:
        """Start moving the desk up."""
        self._begin_movement("continuous", "up")
        await self._send_movement_command(COMMAND_MOVE_UP)

    async def move_down(self) -> None:
        """Start moving the desk down."""
        self._begin_movement("continuous", "down")
        await self._send_movement_command(COMMAND_MOVE_DOWN)

    async def stop(self) -> None:
        """Stop desk movement."""
        self._end_movement()
        # Sent at once: a moving desk is awake, and a sleeping one has nothing to stop
        await self._send_command(COMMAND_STOP)

    async def get_status(self) -> None:
        """Request current desk status."""
        await self._send_command(COMMAND_GET_STATUS)

    async def get_settings(self) -> None:
        """Ask the desk to report its settings, including unit and touch mode.

        The desk sends its settings block for a status request that follows a
        handshake; it has no query for a single setting.
        """
        await self._send_awake_command(COMMAND_GET_STATUS)

    async def move_to_preset(self, preset: int) -> None:
        """Move desk to a preset position (1-4)."""
        if preset == 1:
            command = COMMAND_MEMORY_1
        elif preset == 2:
            command = COMMAND_MEMORY_2
        elif preset == 3:
            command = COMMAND_MEMORY_3
        elif preset == 4:
            command = COMMAND_MEMORY_4
        else:
            raise ValueError(f"Invalid preset number: {preset}")

        # The preset height is unknown, so the direction is too
        self._begin_movement("preset", None)
        await self._send_movement_command(command)

    def _create_command_with_byte_param(self, command_byte: int, param: int) -> bytes:
        """Create a command with a single byte parameter."""
        checksum = (command_byte + 0x01 + param) & 0xFF
        return bytes([0xF1, 0xF1, command_byte, 0x01, param & 0xFF, checksum, 0x7E])

    def _create_command_with_word_param(self, command_byte: int, param: int) -> bytes:
        """Create a command with a 2-byte (word) parameter."""
        high_byte = (param >> 8) & 0xFF
        low_byte = param & 0xFF
        checksum = (command_byte + 0x02 + high_byte + low_byte) & 0xFF
        return bytes(
            [0xF1, 0xF1, command_byte, 0x02, high_byte, low_byte, checksum, 0x7E]
        )

    async def move_to_height(self, height_cm: float) -> None:
        """Move desk to a specific height in cm."""
        # The target is always in mm, whatever the desk's display unit
        height_mm = int(height_cm * 10)

        # Ensure height is within valid range

        if height_cm < MIN_HEIGHT or height_cm > MAX_HEIGHT:
            raise ValueError(
                f"Height {height_cm:.1f} cm is out of range "
                f"({MIN_HEIGHT:.1f}-{MAX_HEIGHT:.1f} cm)"
            )

        if height_cm == self._height_cm:
            # Already at target height
            self._end_movement()
            return

        # Build move-to-height command
        # Command structure: [0xF1, 0xF1, 0x1B, 0x02, height_high, height_low, checksum, 0x7E]
        height_high = (height_mm >> 8) & 0xFF
        height_low = height_mm & 0xFF
        checksum = (0x1B + 0x02 + height_high + height_low) & 0xFF

        command = bytes(
            [0xF1, 0xF1, 0x1B, 0x02, height_high, height_low, checksum, 0x7E]
        )

        _LOGGER.debug(
            "Moving to height %.1f cm (command: %s)", height_cm, command.hex()
        )

        direction = "up" if height_cm > self._height_cm else "down"
        self._begin_movement("targeted", direction, height_cm)
        await self._send_movement_command(command)

    # Get device status methods
    async def get_light_color(self) -> None:
        """Request current light color setting."""
        await self._send_command(COMMAND_GET_LIGHT_COLOR)

    async def get_brightness(self) -> None:
        """Request current brightness level."""
        await self._send_command(COMMAND_GET_BRIGHTNESS)

    async def get_lighting_status(self) -> None:
        """Request current lighting on/off status."""
        await self._send_command(COMMAND_GET_LIGHTING)

    async def get_vibration_status(self) -> None:
        """Request current vibration on/off status."""
        await self._send_command(COMMAND_GET_VIBRATION)

    async def get_vibration_intensity(self) -> None:
        """Request current vibration intensity."""
        await self._send_command(COMMAND_GET_VIBRATION_INTENSITY)

    async def get_lock_status(self) -> None:
        """Request current lock status."""
        await self._send_command(COMMAND_GET_LOCK_STATUS)

    async def get_sensitivity(self) -> None:
        """Request current collision sensitivity level."""
        await self._send_command(COMMAND_GET_SENSITIVITY)

    async def get_limits(self) -> None:
        """Request current height limit settings."""
        await self._send_command(COMMAND_GET_LIMITS)

    # Set device configuration methods
    async def set_light_color(self, color: int) -> None:
        """Set light color (1-7)."""
        if color < 1 or color > 7:
            raise ValueError(f"Invalid light color: {color} (must be 1-7)")
        command = self._create_command_with_byte_param(0xB4, color)
        await self._send_awake_command(command)

    async def set_brightness(self, level: int) -> None:
        """Set brightness level (0-100)."""
        if level < 0 or level > 100:
            raise ValueError(f"Invalid brightness level: {level} (must be 0-100)")
        command = self._create_command_with_byte_param(0xB6, level)
        await self._send_awake_command(command)

    async def set_lighting(self, enabled: bool) -> None:
        """Enable or disable lighting."""
        value = 1 if enabled else 0
        command = self._create_command_with_byte_param(0xB5, value)
        await self._send_awake_command(command)

    async def set_vibration(self, enabled: bool) -> None:
        """Enable or disable vibration."""
        value = 1 if enabled else 0
        command = self._create_command_with_byte_param(0xB3, value)
        await self._send_awake_command(command)

    async def set_vibration_intensity(self, level: int) -> None:
        """Set vibration intensity level."""
        if level < 0 or level > 100:
            raise ValueError(f"Invalid vibration intensity: {level} (must be 0-100)")
        command = self._create_command_with_byte_param(0xA4, level)
        await self._send_awake_command(command)

    async def set_lock_status(self, locked: bool) -> None:
        """Lock or unlock desk controls."""
        value = 1 if locked else 0
        command = self._create_command_with_byte_param(0xB2, value)
        await self._send_awake_command(command)
        # Shown at once; the desk confirms it in its next lock status report
        self._lock_status = locked

    async def set_sensitivity(self, level: int) -> None:
        """Set collision sensitivity level (1=High, 2=Medium, 3=Low)."""
        if level < 1 or level > 3:
            raise ValueError(f"Invalid sensitivity level: {level} (must be 1-3)")
        command = self._create_command_with_byte_param(0x1D, level)
        await self._send_awake_command(command)

    async def set_touch_mode(self, mode: int) -> None:
        """Set touch mode (0=One press, 1=Press and hold)."""
        if mode not in [0, 1]:
            raise ValueError(f"Invalid touch mode: {mode} (must be 0 or 1)")
        command = self._create_command_with_byte_param(0x19, mode)
        await self._send_awake_command(command)

    async def set_unit(self, unit: str) -> None:
        """Set display unit preference."""
        if unit not in ["cm", "in"]:
            raise ValueError(f"Invalid unit: {unit} (must be 'cm' or 'in')")
        value = 0 if unit == "cm" else 1
        command = self._create_command_with_byte_param(0x0E, value)
        await self._send_awake_command(command)

    async def set_height_limit_upper(self, height_cm: float) -> None:
        """Set upper height limit in cm."""
        if not MIN_HEIGHT <= height_cm <= MAX_HEIGHT:
            raise ValueError(
                f"Invalid upper height limit: {height_cm:.1f} "
                f"(must be {MIN_HEIGHT:.1f}-{MAX_HEIGHT:.1f})"
            )
        # Limits are in the desk's display unit, unlike move-to-height targets
        command = self._create_command_with_word_param(
            0x21, self._encode_height(height_cm)
        )
        await self._send_awake_command(command)

    async def set_height_limit_lower(self, height_cm: float) -> None:
        """Set lower height limit in cm."""
        if not MIN_HEIGHT <= height_cm <= MAX_HEIGHT:
            raise ValueError(
                f"Invalid lower height limit: {height_cm:.1f} "
                f"(must be {MIN_HEIGHT:.1f}-{MAX_HEIGHT:.1f})"
            )
        # Limits are in the desk's display unit, unlike move-to-height targets
        command = self._create_command_with_word_param(
            0x22, self._encode_height(height_cm)
        )
        await self._send_awake_command(command)

    async def clear_height_limits(self) -> None:
        """Clear all height limits."""
        await self._send_awake_command(COMMAND_CLEAR_LIMITS)

    async def _query_device_capabilities(self) -> None:
        """Ask the desk for its settings; the answers arrive as notifications.

        A desk without a feature does not answer its query. A write that fails
        means the connection is gone, so the error fails the connect.
        """
        _LOGGER.debug("Querying device capabilities...")
        await self.get_lighting_status()
        await self.get_light_color()
        await self.get_brightness()
        await self.get_vibration_status()
        await self.get_vibration_intensity()
        await self.get_lock_status()
        await self.get_sensitivity()
        await self.get_limits()
        _LOGGER.debug("Device capability query complete")

    async def _read_device_information(self) -> None:
        """Read device information from BLE Device Information Service (0x180A)."""
        if not self.is_connected:
            _LOGGER.debug("Not connected - cannot read device information")
            return
        assert self._client is not None  # guaranteed by is_connected

        _LOGGER.debug(
            "Starting device information read from Device Information Service..."
        )

        # Log all available services for debugging
        try:
            # IMPORTANT: DO NOT use await self._client.get_services() - it's deprecated!
            # Use the services property instead. Service discovery is already complete
            # when this method is called from within connect() after connection is established.
            # The services property is synchronous and returns the already-discovered services.
            services = self._client.services
            service_count = 0
            device_info_service = None

            # Iterate through services
            for service in services:
                service_count += 1
                _LOGGER.debug("Service UUID: %s", service.uuid)

                # Check if this is the Device Information Service
                if service.uuid.lower() == DEVICE_INFORMATION_SERVICE_UUID.lower():
                    device_info_service = service
                    _LOGGER.debug("Found Device Information Service: %s", service.uuid)

                # Also log characteristics for debugging
                for char in service.characteristics:
                    _LOGGER.debug(
                        "  - Characteristic: %s (properties: %s)",
                        char.uuid,
                        char.properties,
                    )

            _LOGGER.debug("Total services discovered: %d", service_count)

        except Exception as e:
            _LOGGER.debug("Error discovering services: %s", e)
            return

        if not device_info_service:
            _LOGGER.debug(
                "Device Information Service (0x180A) not found in %d services",
                service_count,
            )
            return

        _LOGGER.debug(
            "Device Information Service has %d characteristics",
            len(device_info_service.characteristics),
        )

        # Mapping of characteristic UUIDs to property names and storage attributes
        char_mapping = {
            MANUFACTURER_NAME_CHAR_UUID: ("manufacturer_name", "_manufacturer_name"),
            MODEL_NUMBER_CHAR_UUID: ("model_number", "_model_number"),
            SERIAL_NUMBER_CHAR_UUID: ("serial_number", "_serial_number"),
            HARDWARE_REVISION_CHAR_UUID: ("hardware_revision", "_hardware_revision"),
            FIRMWARE_REVISION_CHAR_UUID: ("firmware_revision", "_firmware_revision"),
            SOFTWARE_REVISION_CHAR_UUID: ("software_revision", "_software_revision"),
        }

        # Read each characteristic if available
        for char in device_info_service.characteristics:
            char_uuid = char.uuid.lower()
            _LOGGER.debug(
                "Found characteristic: %s with properties: %s",
                char.uuid,
                char.properties,
            )

            for expected_uuid, (prop_name, attr_name) in char_mapping.items():
                if char_uuid == expected_uuid.lower():
                    _LOGGER.debug(
                        "Matched characteristic %s for %s", char.uuid, prop_name
                    )
                    try:
                        # Check if characteristic supports read operation
                        if "read" in char.properties:
                            _LOGGER.debug("Reading characteristic %s...", prop_name)
                            data = await self._client.read_gatt_char(char.uuid)
                            if data:
                                _LOGGER.debug(
                                    "Raw data for %s: %s (len=%d)",
                                    prop_name,
                                    data.hex(),
                                    len(data),
                                )
                                # Decode as UTF-8 string and strip whitespace/null bytes
                                value = data.decode("utf-8", errors="ignore").strip(
                                    "\x00\r\n\t "
                                )
                                if value:  # Only store non-empty values
                                    setattr(self, attr_name, value)
                                    _LOGGER.debug(
                                        "Device info - %s: %s", prop_name, value
                                    )
                                else:
                                    _LOGGER.debug(
                                        "Device info - %s: (empty after decode)",
                                        prop_name,
                                    )
                            else:
                                _LOGGER.debug(
                                    "Device info - %s: (no data returned)", prop_name
                                )
                        else:
                            _LOGGER.debug(
                                "Device info - %s: characteristic not readable (properties: %s)",
                                prop_name,
                                char.properties,
                            )
                    except Exception as e:
                        _LOGGER.debug("Failed to read %s: %s", prop_name, e)
                    break

        # Log summary of what was read
        device_info_summary = []
        if self._manufacturer_name:
            device_info_summary.append(f"Manufacturer: {self._manufacturer_name}")
        if self._model_number:
            device_info_summary.append(f"Model: {self._model_number}")
        if self._serial_number:
            device_info_summary.append(f"Serial: {self._serial_number}")
        if self._hardware_revision:
            device_info_summary.append(f"HW: {self._hardware_revision}")
        if self._firmware_revision:
            device_info_summary.append(f"FW: {self._firmware_revision}")
        if self._software_revision:
            device_info_summary.append(f"SW: {self._software_revision}")

        if device_info_summary:
            _LOGGER.debug("Device information: %s", ", ".join(device_info_summary))
        else:
            _LOGGER.debug("No device information characteristics found or readable")

    def _handle_notification(
        self, sender: BleakGATTCharacteristic | None, data: bytearray
    ) -> None:
        """Handle notification from the desk."""
        _LOGGER.debug("Received notification: %s", data.hex())
        header = data[:4].hex(" ")
        if self._recent_headers and self._recent_headers[-1][0] == header:
            self._recent_headers[-1][1] += 1
        else:
            self._recent_headers.append([header, 1])

        # Check for height notification (0x98 0x98 header)
        if len(data) >= 6 and bytes(data[:2]) == HEIGHT_NOTIFICATION_HEADER:
            # Extract height from bytes 4-5 (little-endian)
            height_cm = self._decode_height(data[4] | (data[5] << 8), data)
            _LOGGER.debug("Height notification (0x98 0x98): %.1f cm", height_cm)
            self._process_height(height_cm)

        # Check for status notification (0xF2 0xF2 0x01 0x03 header)
        elif len(data) >= 6 and bytes(data[:4]) == STATUS_NOTIFICATION_HEADER:
            # Extract height from bytes 4-5 (big-endian for status notifications)
            height_cm = self._decode_height((data[4] << 8) | data[5], data)
            _LOGGER.debug(
                "Status notification (0xF2 0xF2 0x01 0x03): %.1f cm", height_cm
            )
            self._process_height(height_cm)

        # Check for light color response
        elif len(data) >= 6 and bytes(data[:4]) == LIGHT_COLOR_RESPONSE_HEADER:
            self._light_color = data[4]
            _LOGGER.debug("Light color response: %s", self._light_color)

        # Check for brightness response
        elif len(data) >= 6 and bytes(data[:4]) == BRIGHTNESS_RESPONSE_HEADER:
            self._brightness = data[4]
            _LOGGER.debug("Brightness response: %s", self._brightness)

        # Check for lighting status response
        elif len(data) >= 6 and bytes(data[:4]) == LIGHTING_RESPONSE_HEADER:
            self._lighting_enabled = data[4] != 0
            _LOGGER.debug("Lighting enabled response: %s", self._lighting_enabled)

        # Check for vibration status response
        elif len(data) >= 6 and bytes(data[:4]) == VIBRATION_RESPONSE_HEADER:
            self._vibration_enabled = data[4] != 0
            _LOGGER.debug("Vibration enabled response: %s", self._vibration_enabled)

        # Check for vibration intensity response
        elif len(data) >= 6 and bytes(data[:4]) == VIBRATION_INTENSITY_RESPONSE_HEADER:
            self._vibration_intensity = data[4]
            _LOGGER.debug("Vibration intensity response: %s", self._vibration_intensity)

        # Check for lock status response
        elif len(data) >= 6 and bytes(data[:4]) == LOCK_STATUS_RESPONSE_HEADER:
            self._lock_status = data[4] != 0
            _LOGGER.debug("Lock status response: %s", self._lock_status)

        # Check for sensitivity response
        elif len(data) >= 6 and bytes(data[:4]) == SENSITIVITY_RESPONSE_HEADER:
            self._sensitivity_level = data[4]
            _LOGGER.debug("Sensitivity level response: %s", self._sensitivity_level)

        # Check for display unit response
        elif len(data) >= 6 and bytes(data[:4]) == UNIT_RESPONSE_HEADER:
            self._unit_preference = DISPLAY_UNITS.get(data[4])
            _LOGGER.debug("Display unit response: %s", self._unit_preference)
            self._notify_callbacks()

        # Check for touch mode response
        elif len(data) >= 6 and bytes(data[:4]) == TOUCH_MODE_RESPONSE_HEADER:
            self._touch_mode = data[4] if data[4] in TOUCH_MODES else None
            _LOGGER.debug("Touch mode response: %s", self._touch_mode)
            self._notify_callbacks()

        # Check for upper limit response (in display units, like heights)
        elif len(data) >= 7 and bytes(data[:4]) == LIMIT_UPPER_RESPONSE_HEADER:
            self._height_limit_upper = self._decode_height(
                (data[4] << 8) | data[5], data
            )
            _LOGGER.debug("Upper limit response: %.1f cm", self._height_limit_upper)
            self._notify_callbacks()

        # Check for lower limit response (in display units, like heights)
        elif len(data) >= 7 and bytes(data[:4]) == LIMIT_LOWER_RESPONSE_HEADER:
            self._height_limit_lower = self._decode_height(
                (data[4] << 8) | data[5], data
            )
            _LOGGER.debug("Lower limit response: %.1f cm", self._height_limit_lower)
            self._notify_callbacks()

        # Check for limit status response (0xF2 0xF2 0x20 0x01):
        # 0x00 no limits, 0x01 upper only, 0x10 lower only, 0x11 both
        elif (
            len(data) >= 6
            and bytes(data[:4]) == LIMIT_STATUS_RESPONSE_HEADER
            and data[4] in (0x00, 0x01, 0x10, 0x11)
        ):
            self._height_limit_upper_set = bool(data[4] & 0x01)
            self._height_limit_lower_set = bool(data[4] & 0x10)
            _LOGGER.debug(
                "Limit status response: upper %s, lower %s",
                "set" if self._height_limit_upper_set else "not set",
                "set" if self._height_limit_lower_set else "not set",
            )
            self._notify_callbacks()

        else:
            _LOGGER.debug("Unknown notification format: %s", data.hex())

    def _decode_height(self, raw: int, data: bytearray) -> float:
        """Turn a height in tenths of the display unit into centimetres.

        The frame is read in the unit the desk reported, unless its value is
        impossible in that unit but plausible in the other one, which happens
        while a unit change is under way. Before the desk reports its unit, the
        value's range decides.
        """
        value = raw / 10.0
        unit = self._unit_preference
        if unit is None:
            unit = "in" if value < UNIT_SPLIT else "cm"
        else:
            other = "cm" if unit == "in" else "in"
            if not _plausible(_to_cm(value, unit)) and _plausible(_to_cm(value, other)):
                unit = other

        height_cm = _to_cm(value, unit)
        if not _plausible(height_cm):
            _LOGGER.debug(
                "Height %.1f cm fits neither unit (frame %s)", height_cm, data.hex()
            )
        self._effective_unit = unit
        return height_cm

    def _encode_height(self, height_cm: float) -> int:
        """Turn centimetres into tenths of the unit the desk currently uses."""
        if (self._effective_unit or self._unit_preference) == "in":
            return round(height_cm / CM_PER_INCH * 10)
        return round(height_cm * 10)

    def _process_height(self, height_cm: float) -> None:
        """Take a new height reading, track the movement in flight and notify."""
        now = time.time()
        previous_height = self._height_cm
        previous_time = self._last_notification_time
        self._height_cm = height_cm
        self._last_notification_time = now

        movement = self._movement
        if movement is not None and not movement.started:
            if now - movement.command_time > COMMAND_EXPIRY_SECONDS:
                _LOGGER.debug("Command expired without the desk moving")
                self._end_movement()
            else:
                self._check_movement_start(movement, now)
        elif movement is not None:
            self._track_movement(movement, previous_height, previous_time, now)

        self._notify_callbacks()

    def _check_movement_start(self, movement: _Movement, now: float) -> None:
        """Start the movement once the height has left the jitter band."""
        change = self._height_cm - movement.command_height
        if movement.direction == "up":
            moved = change > HEIGHT_JITTER_CM
        elif movement.direction == "down":
            moved = -change > HEIGHT_JITTER_CM
        else:
            moved = abs(change) > HEIGHT_JITTER_CM
        if not moved:
            return

        movement.started = True
        movement.start_time = now
        movement.last_change_time = now
        movement.last_height = self._height_cm
        movement.furthest_height = self._height_cm
        _LOGGER.debug("Movement started - collision detection enabled")

    def _track_movement(
        self,
        movement: _Movement,
        previous_height: float,
        previous_time: float,
        now: float,
    ) -> None:
        """Follow a started movement: detect its stop and any bounce-back."""
        height = self._height_cm
        if abs(height - movement.last_height) < 0.05:
            movement.unchanged_readings += 1
            if movement.unchanged_readings >= UNCHANGED_READINGS_TO_STOP:
                self._finish_movement(movement)
            return

        if previous_time > 0 and now > previous_time:
            movement.velocities.append(
                (height - previous_height) / (now - previous_time)
            )
            # Keep only the last 10 velocity measurements
            del movement.velocities[:-10]
        movement.unchanged_readings = 0
        movement.last_height = height
        movement.last_change_time = now

        # A bounce is a reversal from the furthest point reached in the
        # commanded direction; presets have no known direction to reverse
        if movement.direction == "up":
            movement.furthest_height = max(movement.furthest_height, height)
            reversal = movement.furthest_height - height
        elif movement.direction == "down":
            movement.furthest_height = min(movement.furthest_height, height)
            reversal = height - movement.furthest_height
        else:
            reversal = 0.0
        if reversal > HEIGHT_JITTER_CM:
            self._set_collision_detected(True)
            _LOGGER.info(
                "Bounce-back detected! Commanded %s but reversed %.1f cm to %.1f cm",
                movement.direction,
                reversal,
                height,
            )
            self._end_movement()
            return

        # Clear a collision once the desk has moved successfully for a while after it
        if self._collision_detected and self._collision_time:
            time_since_collision = now - self._collision_time
            if time_since_collision > 2.0:
                _LOGGER.info(
                    "Clearing collision state after %.1f seconds of successful movement",
                    time_since_collision,
                )
                self._set_collision_detected(False)

    def _finish_movement(self, movement: _Movement) -> None:
        """End a movement whose height stopped changing, judging if it collided."""
        # Measure the active part of the movement, not the wait for the stop
        duration = movement.last_change_time - movement.start_time
        _LOGGER.debug(
            "Auto-stop detected: height unchanged for %d notifications",
            UNCHANGED_READINGS_TO_STOP,
        )
        if duration > 1.0:  # Require at least 1 second of movement
            if self._is_collision_stop(movement, duration):
                self._set_collision_detected(True)
                _LOGGER.info(
                    "Collision detected at %.1f cm after %.1f seconds",
                    self._height_cm,
                    duration,
                )
            else:
                _LOGGER.debug(
                    "Normal stop at %.1f cm after %.1f seconds",
                    self._height_cm,
                    duration,
                )
        else:
            _LOGGER.debug(
                "Auto-stop after %.1f seconds - too short for collision", duration
            )
        self._end_movement()

    def _notify_callbacks(self) -> None:
        """Pass the current height, collision and moving state to every listener."""
        for callback in self._notification_callbacks:
            callback(self._height_cm, self._collision_detected, self.is_moving)

    def _is_collision_stop(self, movement: _Movement, duration: float) -> bool:
        """Determine if a stop was a collision, from the movement type and context."""
        distance_moved = abs(self._height_cm - movement.command_height)
        avg_overall_speed = distance_moved / duration if duration > 0 else 0
        avg_recent_velocity = abs(movement.average_velocity())

        if movement.kind == "continuous":
            # For manual up/down movements, analyze movement patterns like presets
            _LOGGER.debug(
                "Continuous movement: %.1f cm in %.1f seconds (overall: %.2f cm/s, recent: %.2f cm/s)",
                distance_moved,
                duration,
                avg_overall_speed,
                avg_recent_velocity,
            )

            # If minimal movement occurred, likely a collision
            if distance_moved < 0.5:  # Less than 5mm movement
                _LOGGER.debug(
                    "Continuous collision: minimal movement (%.1f cm)", distance_moved
                )
                return True

            # Check recent velocity for signs of collision (very slow recent movement)
            if len(movement.velocities) >= 3 and avg_recent_velocity < 0.3:
                _LOGGER.debug(
                    "Continuous collision: recent velocity too slow (%.2f cm/s)",
                    avg_recent_velocity,
                )
                return True

            # If overall movement was too slow, likely hit an obstacle
            if avg_overall_speed < 0.5:  # Less than 0.5 cm/s average speed
                _LOGGER.debug(
                    "Continuous collision: abnormally slow overall movement (%.2f cm/s)",
                    avg_overall_speed,
                )
                return True

            # Reasonable distance and speed: the user released the button
            _LOGGER.debug(
                "Normal continuous stop: %.1f cm at %.2f cm/s",
                distance_moved,
                avg_overall_speed,
            )
            return False

        if movement.kind == "targeted" and movement.target_height is not None:
            target_height = movement.target_height
            # First check if we hit a physical height limit
            height_limit_tolerance = 3.0  # Allow 3cm tolerance for height limits

            # Check if we're near the minimum height limit
            if (
                self._height_cm <= MIN_HEIGHT + height_limit_tolerance
                and target_height < self._height_cm  # Was trying to go down
            ):
                _LOGGER.debug(
                    "Hit minimum height limit at %.1f cm (target: %.1f cm)",
                    self._height_cm,
                    target_height,
                )
                return False

            # Check if we're near the maximum height limit
            # This handles cases where desk can't reach the configured maximum
            if (
                target_height >= MAX_HEIGHT - 1.0  # Target was near max height
                and target_height > self._height_cm  # Was trying to go up
            ):
                # If we stopped within reasonable range of maximum, likely hit physical limit
                distance_from_max = MAX_HEIGHT - self._height_cm
                if distance_from_max <= 8.0:  # Within 8cm of configured maximum
                    _LOGGER.debug(
                        "Hit maximum height limit at %.1f cm (target: %.1f cm, %.1f cm from max)",
                        self._height_cm,
                        target_height,
                        distance_from_max,
                    )
                    return False

            # For targeted movements, check if we're close to the target
            height_tolerance = 1.0  # Allow 1cm tolerance
            if abs(self._height_cm - target_height) <= height_tolerance:
                _LOGGER.debug(
                    "Reached target height %.1f cm (current: %.1f cm)",
                    target_height,
                    self._height_cm,
                )
                return False
            _LOGGER.debug(
                "Stopped at %.1f cm, away from target %.1f cm",
                self._height_cm,
                target_height,
            )
            return True

        if movement.kind == "preset":
            # For preset movements, analyze movement patterns instead of arbitrary time threshold
            _LOGGER.debug(
                "Preset movement: %.1f cm in %.1f seconds (overall: %.2f cm/s, recent: %.2f cm/s)",
                distance_moved,
                duration,
                avg_overall_speed,
                avg_recent_velocity,
            )

            # If minimal movement occurred, likely a collision
            if distance_moved < 0.5:  # Less than 5mm movement
                _LOGGER.debug(
                    "Preset collision: minimal movement (%.1f cm)", distance_moved
                )
                return True

            # Check recent velocity for signs of collision (very slow recent movement)
            if len(movement.velocities) >= 3 and avg_recent_velocity < 0.3:
                _LOGGER.debug(
                    "Preset collision: recent velocity too slow (%.2f cm/s)",
                    avg_recent_velocity,
                )
                return True

            # If overall movement was too slow, likely hit an obstacle
            if avg_overall_speed < 0.5:  # Less than 0.5 cm/s average speed
                _LOGGER.debug(
                    "Preset collision: abnormally slow overall movement (%.2f cm/s)",
                    avg_overall_speed,
                )
                return True

            # For normal preset movements (reasonable distance and speed), not a collision
            if distance_moved >= 1.0 and avg_overall_speed >= 1.0:
                _LOGGER.debug(
                    "Normal preset completion: %.1f cm at %.2f cm/s",
                    distance_moved,
                    avg_overall_speed,
                )
                return False

            # Otherwise fall back to duration: very long preset movements might be collisions
            if duration > 10.0:
                _LOGGER.debug(
                    "Very long preset movement (%.1f s) - possible collision", duration
                )
                return True
            _LOGGER.debug(
                "Normal duration preset movement (%.1f s) - likely completed normally",
                duration,
            )
            return False

        # Default to collision for unknown movement types
        return True

    def _set_collision_detected(self, detected: bool) -> None:
        """Set collision detected state and manage auto-clear."""
        self._collision_detected = detected

        if detected:
            # Record when collision was detected
            self._collision_time = time.time()
            # Schedule auto-clear
            self._schedule_collision_auto_clear()
        else:
            # Cancel any pending auto-clear
            self._cancel_collision_auto_clear()
            self._collision_time = None

    def _schedule_collision_auto_clear(self) -> None:
        """Schedule automatic clearing of collision state."""
        # Cancel any existing auto-clear task
        self._cancel_collision_auto_clear()

        # Create new auto-clear task
        async def auto_clear():
            await asyncio.sleep(COLLISION_AUTO_CLEAR_SECONDS)
            if self._collision_detected:
                _LOGGER.info(
                    "Auto-clearing collision state after %.0f seconds",
                    COLLISION_AUTO_CLEAR_SECONDS,
                )
                self._collision_detected = False
                self._collision_time = None
                # Notify callbacks about the state change
                self._notify_callbacks()

        # Schedule the task only if there's a running event loop
        try:
            asyncio.get_running_loop()
            self._auto_clear_task = asyncio.create_task(auto_clear())
        except RuntimeError:
            # No event loop running (e.g., in sync tests)
            _LOGGER.debug("No event loop available for auto-clear scheduling")

    def _cancel_collision_auto_clear(self) -> None:
        """Cancel any pending collision auto-clear task."""
        if self._auto_clear_task and not self._auto_clear_task.done():
            self._auto_clear_task.cancel()
        self._auto_clear_task = None

    def _reset_link_state(self) -> None:
        """Forget everything that belongs to the current connection."""
        self._client = None

        # The movement ends with the connection, and a collision from before the
        # drop is not shown again after reconnecting
        self._end_movement()
        self._set_collision_detected(False)

        # Settings can change on the hand controller while disconnected, so they
        # are read from the desk again on reconnecting
        self._unit_preference = None
        self._effective_unit = None
        self._touch_mode = None

    def _handle_disconnect(self, client: BleakClient) -> None:
        """Handle disconnection from the desk."""
        if client is not self._client:
            # A link that is no longer current, such as one closed after a failed
            # attempt; it says nothing about the current connection
            _LOGGER.debug("Ignoring a disconnect from an earlier connection")
            return

        # The coordinator logs the outage once; this repeats on every drop
        _LOGGER.debug("Disconnected from Desky desk")
        self._reset_link_state()

        for callback in self._disconnect_callbacks:
            callback()
