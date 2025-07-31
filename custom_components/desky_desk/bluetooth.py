"""Bluetooth communication for Desky Desk."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .const import (
    COMMAND_GET_STATUS,
    COMMAND_HANDSHAKE,
    COMMAND_MEMORY_1,
    COMMAND_MEMORY_2,
    COMMAND_MEMORY_3,
    COMMAND_MEMORY_4,
    COMMAND_MOVE_DOWN,
    COMMAND_MOVE_UP,
    COMMAND_STOP,
    DIRECT_CONNECTION_TIMEOUT,
    DIRECT_MAX_ATTEMPTS,
    HEIGHT_NOTIFICATION_HEADER,
    NOTIFY_CHARACTERISTIC_UUID,
    PROXY_CONNECTION_TIMEOUT,
    PROXY_MAX_ATTEMPTS,
    STATUS_NOTIFICATION_HEADER,
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

    def _is_esphome_proxy(self, ble_device: BLEDevice) -> bool:
        """Detect if connection will use ESPHome proxy."""
        if not ble_device.details:
            _LOGGER.debug("No device details available for proxy detection")
            return False
        
        # Log details for debugging
        _LOGGER.debug("BLE device details: %s", ble_device.details)
        
        # Check for proxy indicators in details
        details_str = str(ble_device.details).lower()
        
        # Primary indicators
        if 'via_device' in ble_device.details:
            _LOGGER.debug("Detected ESPHome proxy via 'via_device' indicator")
            return True
        
        # Check source field
        source = ble_device.details.get('source', '').lower()
        if any(indicator in source for indicator in ['esphome', 'proxy', 'esp32']):
            _LOGGER.debug("Detected ESPHome proxy via source: %s", source)
            return True
        
        # Check for ESPHome specific keys
        esphome_keys = ['esp_platform', 'esphome_version', 'scanner']
        if any(key in ble_device.details for key in esphome_keys):
            scanner = str(ble_device.details.get('scanner', '')).lower()
            if 'esp' in scanner:
                _LOGGER.debug("Detected ESPHome proxy via scanner: %s", scanner)
                return True
        
        # Check adapter/path information
        if 'path' in ble_device.details:
            path = str(ble_device.details.get('path', '')).lower()
            if 'esphome' in path or 'proxy' in path:
                _LOGGER.debug("Detected ESPHome proxy via path: %s", path)
                return True
        
        _LOGGER.debug("No ESPHome proxy indicators found")
        return False

    async def connect(self) -> bool:
        """Connect to the desk."""
        if self.is_connected:
            return True

        # Detect if using ESPHome proxy
        is_proxy = self._is_esphome_proxy(self._ble_device)
        timeout = PROXY_CONNECTION_TIMEOUT if is_proxy else DIRECT_CONNECTION_TIMEOUT
        max_attempts = PROXY_MAX_ATTEMPTS if is_proxy else DIRECT_MAX_ATTEMPTS
        
        _LOGGER.debug(
            "Connecting to Desky desk at %s (proxy: %s, timeout: %s)",
            self.address, is_proxy, timeout
        )

        try:
            self._client = await establish_connection(
                BleakClient,
                self._ble_device,
                self.name,
                disconnected_callback=self._handle_disconnect,
                timeout=timeout,
                max_attempts=max_attempts,
                use_services_cache=True,  # Improves proxy performance
                # Callback for device updates during connection
                ble_device_callback=lambda: self._get_updated_device()
            )
            
            # Discover services to verify characteristics
            _LOGGER.debug("Connected, discovering services...")
            services = await self._client.get_services()
            for service in services:
                _LOGGER.debug("Service: %s", service.uuid)
                for char in service.characteristics:
                    _LOGGER.debug("  Characteristic: %s, properties: %s", char.uuid, char.properties)
            
            # Start notifications
            await self._client.start_notify(
                NOTIFY_CHARACTERISTIC_UUID,
                self._handle_notification
            )
            
            # Send handshake command to enable movement controls
            _LOGGER.debug("Sending handshake command...")
            handshake_result = await self._send_command(COMMAND_HANDSHAKE)
            if not handshake_result:
                _LOGGER.warning("Handshake command failed, movement controls may not work")
            else:
                _LOGGER.debug("Handshake command sent successfully")
            
            # Get initial status
            await self.get_status()
            
            _LOGGER.info(
                "Connected to Desky desk at %s via %s", 
                self.address,
                "ESPHome proxy" if is_proxy else "direct Bluetooth"
            )
            return True
            
        except asyncio.TimeoutError:
            _LOGGER.error(
                "Connection timeout after %ss to desk at %s",
                timeout, self.address
            )
            self._client = None
            return False
        except Exception as err:
            _LOGGER.error("Failed to connect to desk: %s", err)
            self._client = None
            return False

    def _get_updated_device(self) -> BLEDevice | None:
        """Get updated device during connection attempts."""
        # This callback is used by bleak_retry_connector to get
        # fresh device information during reconnection attempts
        return self._ble_device

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

    async def move_to_height(self, height_cm: float) -> bool:
        """Move desk to a specific height in cm."""
        # Convert cm to mm
        height_mm = int(height_cm * 10)
        
        # Ensure height is within valid range
        from .const import MIN_HEIGHT, MAX_HEIGHT
        if height_cm < MIN_HEIGHT or height_cm > MAX_HEIGHT:
            _LOGGER.error(
                "Height %.1f cm is out of range (%.1f-%.1f cm)",
                height_cm, MIN_HEIGHT, MAX_HEIGHT
            )
            return False
        
        # Build move-to-height command
        # Command structure: [0xF1, 0xF1, 0x1B, 0x02, height_high, height_low, checksum, 0x7E]
        height_high = (height_mm >> 8) & 0xFF
        height_low = height_mm & 0xFF
        checksum = (0x1B + 0x02 + height_high + height_low) & 0xFF
        
        command = bytes([0xF1, 0xF1, 0x1B, 0x02, height_high, height_low, checksum, 0x7E])
        
        _LOGGER.debug(
            "Moving to height %.1f cm (command: %s)",
            height_cm, command.hex()
        )
        
        self._is_moving = True
        return await self._send_command(command)

    def _handle_notification(self, sender: int, data: bytearray) -> None:
        """Handle notification from the desk."""
        _LOGGER.debug("Received notification: %s", data.hex())
        
        # Check for height notification (0x98 0x98 header)
        if len(data) >= 6 and bytes(data[:2]) == HEIGHT_NOTIFICATION_HEADER:
            # Extract height from bytes 4-5 (little-endian)
            height_raw = data[4] | (data[5] << 8)
            self._height_cm = height_raw / 10.0
            
            # Check for collision flag (this needs to be determined from actual data)
            # For now, we'll assume no collision detection in basic notifications
            self._collision_detected = False
            
            _LOGGER.debug("Height notification (0x98 0x98): %.1f cm", self._height_cm)
            
            # Notify callbacks
            for callback in self._notification_callbacks:
                callback(self._height_cm, self._collision_detected, self._is_moving)
        
        # Check for status notification (0xF2 0xF2 0x01 0x03 header)
        elif len(data) >= 6 and bytes(data[:4]) == STATUS_NOTIFICATION_HEADER:
            # Extract height from bytes 4-5 (big-endian for status notifications)
            height_raw = (data[4] << 8) | data[5]
            self._height_cm = height_raw / 10.0
            
            # Check for collision flag (this needs to be determined from actual data)
            # For now, we'll assume no collision detection in basic notifications
            self._collision_detected = False
            
            _LOGGER.debug("Status notification (0xF2 0xF2 0x01 0x03): %.1f cm", self._height_cm)
            
            # Notify callbacks
            for callback in self._notification_callbacks:
                callback(self._height_cm, self._collision_detected, self._is_moving)
        else:
            _LOGGER.debug("Unknown notification format: %s", data.hex())

    def _handle_disconnect(self, client: BleakClient) -> None:
        """Handle disconnection from the desk."""
        _LOGGER.warning("Disconnected from Desky desk")
        self._client = None
        self._is_moving = False
        
        # Notify callbacks
        for callback in self._disconnect_callbacks:
            callback()