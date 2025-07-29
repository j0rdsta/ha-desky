"""Bluetooth communication for Desky Desk."""
from __future__ import annotations

import logging
from typing import Any, Callable

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .const import (
    COMMAND_GET_STATUS,
    COMMAND_MEMORY_1,
    COMMAND_MEMORY_2,
    COMMAND_MEMORY_3,
    COMMAND_MEMORY_4,
    COMMAND_MOVE_DOWN,
    COMMAND_MOVE_UP,
    COMMAND_STOP,
    HEIGHT_NOTIFICATION_HEADER,
    NOTIFY_CHARACTERISTIC_UUID,
    WRITE_CHARACTERISTIC_UUID,
)

_LOGGER = logging.getLogger(__name__)


class DeskBLEDevice:
    """Handle BLE communication with Desky desk."""

    def __init__(self, ble_device: BLEDevice, advertisement_data: dict[str, Any] | None = None) -> None:
        """Initialize the desk device."""
        self._ble_device = ble_device
        self._advertisement_data = advertisement_data
        self._client: BleakClient | None = None
        self._height_cm: float = 0.0
        self._collision_detected: bool = False
        self._is_moving: bool = False
        self._notification_callbacks: list[Callable[[float, bool, bool], None]] = []
        self._disconnect_callbacks: list[Callable[[], None]] = []

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
        """Return if desk is currently moving."""
        return self._is_moving

    @property
    def is_connected(self) -> bool:
        """Return if connected to the desk."""
        return self._client is not None and self._client.is_connected

    def register_notification_callback(self, callback: Callable[[float, bool, bool], None]) -> None:
        """Register a callback for height/status notifications."""
        self._notification_callbacks.append(callback)

    def register_disconnect_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback for disconnection events."""
        self._disconnect_callbacks.append(callback)

    async def connect(self) -> bool:
        """Connect to the desk."""
        if self.is_connected:
            return True

        try:
            _LOGGER.debug("Connecting to Desky desk at %s", self.address)
            self._client = await establish_connection(
                BleakClient,
                self._ble_device,
                self.name,
                disconnected_callback=self._handle_disconnect,
            )
            
            # Start notifications
            await self._client.start_notify(
                NOTIFY_CHARACTERISTIC_UUID,
                self._handle_notification
            )
            
            # Get initial status
            await self.get_status()
            
            _LOGGER.info("Connected to Desky desk at %s", self.address)
            return True
            
        except Exception as err:
            _LOGGER.error("Failed to connect to desk: %s", err)
            self._client = None
            return False

    async def disconnect(self) -> None:
        """Disconnect from the desk."""
        if self._client:
            try:
                await self._client.stop_notify(NOTIFY_CHARACTERISTIC_UUID)
                await self._client.disconnect()
            except Exception as err:
                _LOGGER.debug("Error during disconnect: %s", err)
            finally:
                self._client = None

    async def _send_command(self, command: bytes) -> bool:
        """Send a command to the desk."""
        if not self.is_connected:
            _LOGGER.warning("Cannot send command: not connected")
            return False

        try:
            await self._client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, command)
            return True
        except Exception as err:
            _LOGGER.error("Failed to send command: %s", err)
            return False

    async def move_up(self) -> bool:
        """Start moving the desk up."""
        self._is_moving = True
        return await self._send_command(COMMAND_MOVE_UP)

    async def move_down(self) -> bool:
        """Start moving the desk down."""
        self._is_moving = True
        return await self._send_command(COMMAND_MOVE_DOWN)

    async def stop(self) -> bool:
        """Stop desk movement."""
        self._is_moving = False
        return await self._send_command(COMMAND_STOP)

    async def get_status(self) -> bool:
        """Request current desk status."""
        return await self._send_command(COMMAND_GET_STATUS)

    async def move_to_preset(self, preset: int) -> bool:
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
            _LOGGER.error("Invalid preset number: %s", preset)
            return False
        
        self._is_moving = True
        return await self._send_command(command)

    def _handle_notification(self, sender: int, data: bytearray) -> None:
        """Handle notification from the desk."""
        if len(data) >= 6 and bytes(data[:2]) == HEIGHT_NOTIFICATION_HEADER:
            # Extract height from bytes 4-5 (little-endian)
            height_raw = data[4] | (data[5] << 8)
            self._height_cm = height_raw / 10.0
            
            # Check for collision flag (this needs to be determined from actual data)
            # For now, we'll assume no collision detection in basic notifications
            self._collision_detected = False
            
            # Notify callbacks
            for callback in self._notification_callbacks:
                callback(self._height_cm, self._collision_detected, self._is_moving)
            
            _LOGGER.debug("Height update: %.1f cm", self._height_cm)

    def _handle_disconnect(self, client: BleakClient) -> None:
        """Handle disconnection from the desk."""
        _LOGGER.warning("Disconnected from Desky desk")
        self._client = None
        self._is_moving = False
        
        # Notify callbacks
        for callback in self._disconnect_callbacks:
            callback()