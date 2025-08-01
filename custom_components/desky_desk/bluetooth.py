"""Bluetooth communication for Desky Desk."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .const import (
    BRIGHTNESS_RESPONSE_HEADER,
    COMMAND_CLEAR_LIMITS,
    COMMAND_GET_BRIGHTNESS,
    COMMAND_GET_LIGHTING,
    COMMAND_GET_LIGHT_COLOR,
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
    DIRECT_CONNECTION_TIMEOUT,
    DIRECT_MAX_ATTEMPTS,
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
    PROXY_CONNECTION_TIMEOUT,
    PROXY_MAX_ATTEMPTS,
    SENSITIVITY_RESPONSE_HEADER,
    SERIAL_NUMBER_CHAR_UUID,
    SOFTWARE_REVISION_CHAR_UUID,
    STATUS_NOTIFICATION_HEADER,
    VIBRATION_INTENSITY_RESPONSE_HEADER,
    VIBRATION_RESPONSE_HEADER,
    WRITE_CHARACTERISTIC_UUID,
)

_LOGGER = logging.getLogger(__name__)

# Auto-clear collision after this many seconds
COLLISION_AUTO_CLEAR_SECONDS = 10.0


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
        self._movement_direction: str | None = None  # "up", "down", or None
        self._last_height_cm: float = 0.0  # Track last height for auto-stop detection
        self._height_unchanged_count: int = 0  # Count notifications with unchanged height
        self._movement_start_time: float = 0.0  # Track when movement started
        self._commanded_direction: str | None = None  # What user commanded ("up" or "down")
        self._recent_heights: list[tuple[float, float]] = []  # Track recent (time, height) for bounce detection
        self._bounce_detected: bool = False  # Track if bounce-back was detected
        self._collision_time: float | None = None  # When collision was detected
        self._auto_clear_task: asyncio.Task | None = None  # Task for auto-clearing collision
        self._target_height: float | None = None  # Target height for movement (if known)
        self._movement_type: str | None = None  # "targeted", "preset", or "continuous"
        self._movement_start_height: float | None = None  # Height when movement started
        self._recent_velocities: list[float] = []  # Track recent movement velocities (cm/s)
        self._last_notification_time: float = 0.0  # Time of last height notification
        self._notification_callbacks: list[Callable[[float, bool, bool], None]] = []
        self._disconnect_callbacks: list[Callable[[], None]] = []
        
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
        self._limits_enabled: bool = False
        self._touch_mode: int | None = None
        self._unit_preference: str | None = None  # "cm" or "in"
        
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
        """Return if desk is currently moving."""
        return self._is_moving
    
    @property
    def movement_direction(self) -> str | None:
        """Return the current movement direction ('up', 'down', or None)."""
        return self._movement_direction

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
        """Return upper height limit in cm."""
        return self._height_limit_upper
    
    @property
    def height_limit_lower(self) -> float | None:
        """Return lower height limit in cm."""
        return self._height_limit_lower
    
    @property
    def limits_enabled(self) -> bool:
        """Return if height limits are enabled."""
        return self._limits_enabled
    
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
            services = self._client.services
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
            
            # Query device capabilities (ignore failures - not all desks support all features)
            await self._query_device_capabilities()
            
            # Small delay to ensure all services are properly discovered
            await asyncio.sleep(0.5)
            
            # Read device information from Device Information Service (0x180A)
            await self._read_device_information()
            
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
        # Cancel any pending auto-clear task
        self._cancel_collision_auto_clear()
        
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
        # Set movement intent but don't start collision detection until actual movement is detected
        self._movement_direction = "up"
        self._commanded_direction = "up"  # Track what user commanded
        self._target_height = None  # No specific target for continuous movement
        self._movement_type = "continuous"
        self._bounce_detected = False  # Reset bounce detection
        self._recent_heights = []  # Clear recent heights
        self._movement_start_height = None  # Reset starting height for new movement
        self._recent_velocities = []  # Clear velocity measurements for new movement
        # Note: _is_moving, _movement_start_time, and collision detection will be set when actual movement is detected
        return await self._send_command(COMMAND_MOVE_UP)

    async def move_down(self) -> bool:
        """Start moving the desk down."""
        # Set movement intent but don't start collision detection until actual movement is detected
        self._movement_direction = "down"
        self._commanded_direction = "down"  # Track what user commanded
        self._target_height = None  # No specific target for continuous movement
        self._movement_type = "continuous"
        self._bounce_detected = False  # Reset bounce detection
        self._recent_heights = []  # Clear recent heights
        self._movement_start_height = None  # Reset starting height for new movement
        self._recent_velocities = []  # Clear velocity measurements for new movement
        # Note: _is_moving, _movement_start_time, and collision detection will be set when actual movement is detected
        return await self._send_command(COMMAND_MOVE_DOWN)

    async def stop(self) -> bool:
        """Stop desk movement."""
        self._is_moving = False
        self._movement_direction = None
        self._commanded_direction = None
        self._height_unchanged_count = 0
        self._bounce_detected = False
        self._target_height = None
        self._movement_type = None
        self._movement_start_height = None
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
        
        # Set movement intent but don't start collision detection until actual movement is detected
        # We don't know the preset height, so can't set direction
        self._movement_direction = None
        self._commanded_direction = None  # Clear previous movement direction for presets
        self._target_height = None  # We don't know preset heights
        self._movement_type = "preset"
        self._bounce_detected = False  # Reset bounce detection
        self._recent_heights = []  # Clear recent heights
        self._movement_start_height = None  # Reset starting height for new movement
        self._recent_velocities = []  # Clear velocity measurements for new movement
        # Note: _is_moving, _movement_start_time, and collision detection will be set when actual movement is detected
        return await self._send_command(command)

    def _create_command_with_byte_param(self, command_byte: int, param: int) -> bytes:
        """Create a command with a single byte parameter."""
        checksum = (command_byte + 0x01 + param) & 0xFF
        return bytes([0xF1, 0xF1, command_byte, 0x01, param & 0xFF, checksum, 0x7E])
    
    def _create_command_with_word_param(self, command_byte: int, param: int) -> bytes:
        """Create a command with a 2-byte (word) parameter."""
        high_byte = (param >> 8) & 0xFF
        low_byte = param & 0xFF
        checksum = (command_byte + 0x02 + high_byte + low_byte) & 0xFF
        return bytes([0xF1, 0xF1, command_byte, 0x02, high_byte, low_byte, checksum, 0x7E])

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
        
        # Determine movement direction based on current height
        if height_cm > self._height_cm:
            self._movement_direction = "up"
            self._commanded_direction = "up"
        elif height_cm < self._height_cm:
            self._movement_direction = "down"
            self._commanded_direction = "down"
        else:
            # Already at target height
            self._movement_direction = None
            self._commanded_direction = None
            self._is_moving = False
            return True
        
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
        
        # Set movement intent but don't start collision detection until actual movement is detected
        self._movement_direction = "up" if height_cm > self._height_cm else "down"
        self._commanded_direction = self._movement_direction
        self._target_height = height_cm  # Store the target height
        self._movement_type = "targeted"
        self._bounce_detected = False  # Reset bounce detection
        self._recent_heights = []  # Clear recent heights
        self._movement_start_height = None  # Reset starting height for new movement
        self._recent_velocities = []  # Clear velocity measurements for new movement
        # Note: _is_moving, _movement_start_time, and collision detection will be set when actual movement is detected
        return await self._send_command(command)
    
    # Get device status methods
    async def get_light_color(self) -> bool:
        """Request current light color setting."""
        return await self._send_command(COMMAND_GET_LIGHT_COLOR)
    
    async def get_brightness(self) -> bool:
        """Request current brightness level."""
        return await self._send_command(COMMAND_GET_BRIGHTNESS)
    
    async def get_lighting_status(self) -> bool:
        """Request current lighting on/off status."""
        return await self._send_command(COMMAND_GET_LIGHTING)
    
    async def get_vibration_status(self) -> bool:
        """Request current vibration on/off status."""
        return await self._send_command(COMMAND_GET_VIBRATION)
    
    async def get_vibration_intensity(self) -> bool:
        """Request current vibration intensity."""
        return await self._send_command(COMMAND_GET_VIBRATION_INTENSITY)
    
    async def get_lock_status(self) -> bool:
        """Request current lock status."""
        return await self._send_command(COMMAND_GET_LOCK_STATUS)
    
    async def get_sensitivity(self) -> bool:
        """Request current collision sensitivity level."""
        return await self._send_command(COMMAND_GET_SENSITIVITY)
    
    async def get_limits(self) -> bool:
        """Request current height limit settings."""
        return await self._send_command(COMMAND_GET_LIMITS)
    
    # Set device configuration methods
    async def set_light_color(self, color: int) -> bool:
        """Set light color (1-7)."""
        if color < 1 or color > 7:
            _LOGGER.error("Invalid light color: %s (must be 1-7)", color)
            return False
        command = self._create_command_with_byte_param(0xB4, color)
        return await self._send_command(command)
    
    async def set_brightness(self, level: int) -> bool:
        """Set brightness level (0-100)."""
        if level < 0 or level > 100:
            _LOGGER.error("Invalid brightness level: %s (must be 0-100)", level)
            return False
        command = self._create_command_with_byte_param(0xB6, level)
        return await self._send_command(command)
    
    async def set_lighting(self, enabled: bool) -> bool:
        """Enable or disable lighting."""
        value = 1 if enabled else 0
        command = self._create_command_with_byte_param(0xB5, value)
        return await self._send_command(command)
    
    async def set_vibration(self, enabled: bool) -> bool:
        """Enable or disable vibration."""
        value = 1 if enabled else 0
        command = self._create_command_with_byte_param(0xB3, value)
        return await self._send_command(command)
    
    async def set_vibration_intensity(self, level: int) -> bool:
        """Set vibration intensity level."""
        if level < 0 or level > 100:
            _LOGGER.error("Invalid vibration intensity: %s (must be 0-100)", level)
            return False
        command = self._create_command_with_byte_param(0xA4, level)
        return await self._send_command(command)
    
    async def set_lock_status(self, locked: bool) -> bool:
        """Lock or unlock desk controls."""
        value = 1 if locked else 0
        command = self._create_command_with_byte_param(0xB2, value)
        self._lock_status = locked  # Update local state immediately
        return await self._send_command(command)
    
    async def set_sensitivity(self, level: int) -> bool:
        """Set collision sensitivity level (1=High, 2=Medium, 3=Low)."""
        if level < 1 or level > 3:
            _LOGGER.error("Invalid sensitivity level: %s (must be 1-3)", level)
            return False
        command = self._create_command_with_byte_param(0x1D, level)
        return await self._send_command(command)
    
    async def set_touch_mode(self, mode: int) -> bool:
        """Set touch mode (0=One press, 1=Press and hold)."""
        if mode not in [0, 1]:
            _LOGGER.error("Invalid touch mode: %s (must be 0 or 1)", mode)
            return False
        command = self._create_command_with_byte_param(0x19, mode)
        return await self._send_command(command)
    
    async def set_unit(self, unit: str) -> bool:
        """Set display unit preference."""
        if unit not in ["cm", "in"]:
            _LOGGER.error("Invalid unit: %s (must be 'cm' or 'in')", unit)
            return False
        value = 0 if unit == "cm" else 1
        command = self._create_command_with_byte_param(0x0E, value)
        return await self._send_command(command)
    
    async def set_height_limit_upper(self, height_cm: float) -> bool:
        """Set upper height limit in cm."""
        if not MIN_HEIGHT <= height_cm <= MAX_HEIGHT:
            _LOGGER.error(
                "Invalid upper height limit: %.1f (must be %.1f-%.1f)",
                height_cm,
                MIN_HEIGHT,
                MAX_HEIGHT,
            )
            return False
        height_mm = int(height_cm * 10)
        command = self._create_command_with_word_param(0x21, height_mm)
        return await self._send_command(command)
    
    async def set_height_limit_lower(self, height_cm: float) -> bool:
        """Set lower height limit in cm."""
        if not MIN_HEIGHT <= height_cm <= MAX_HEIGHT:
            _LOGGER.error(
                "Invalid lower height limit: %.1f (must be %.1f-%.1f)",
                height_cm,
                MIN_HEIGHT,
                MAX_HEIGHT,
            )
            return False
        height_mm = int(height_cm * 10)
        command = self._create_command_with_word_param(0x22, height_mm)
        return await self._send_command(command)
    
    async def clear_height_limits(self) -> bool:
        """Clear all height limits."""
        return await self._send_command(COMMAND_CLEAR_LIMITS)
    
    async def _query_device_capabilities(self) -> None:
        """Query device capabilities to determine supported features."""
        _LOGGER.debug("Querying device capabilities...")
        
        # Query each capability with a short delay between commands
        # We ignore failures as not all desks support all features
        
        try:
            # Lighting features
            await self.get_lighting_status()
            await asyncio.sleep(0.1)
            await self.get_light_color()
            await asyncio.sleep(0.1)
            await self.get_brightness()
            await asyncio.sleep(0.1)
        except Exception as e:
            _LOGGER.debug("Lighting features not supported: %s", e)
        
        try:
            # Vibration features
            await self.get_vibration_status()
            await asyncio.sleep(0.1)
            await self.get_vibration_intensity()
            await asyncio.sleep(0.1)
        except Exception as e:
            _LOGGER.debug("Vibration features not supported: %s", e)
        
        try:
            # Lock status
            await self.get_lock_status()
            await asyncio.sleep(0.1)
        except Exception as e:
            _LOGGER.debug("Lock feature not supported: %s", e)
        
        try:
            # Collision sensitivity
            await self.get_sensitivity()
            await asyncio.sleep(0.1)
        except Exception as e:
            _LOGGER.debug("Sensitivity adjustment not supported: %s", e)
        
        try:
            # Height limits
            await self.get_limits()
            await asyncio.sleep(0.1)
        except Exception as e:
            _LOGGER.debug("Height limits not supported: %s", e)
        
        _LOGGER.debug("Device capability query complete")
    
    async def _read_device_information(self) -> None:
        """Read device information from BLE Device Information Service (0x180A)."""
        if not self.is_connected:
            _LOGGER.debug("Not connected - cannot read device information")
            return
        
        _LOGGER.info("Starting device information read from Device Information Service...")
        
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
                    _LOGGER.info("Found Device Information Service: %s", service.uuid)
                    
                # Also log characteristics for debugging
                for char in service.characteristics:
                    _LOGGER.debug("  - Characteristic: %s (properties: %s)", char.uuid, char.properties)
            
            _LOGGER.debug("Total services discovered: %d", service_count)
            
        except Exception as e:
            _LOGGER.error("Error discovering services: %s", e)
            return
        
        if not device_info_service:
            _LOGGER.warning("Device Information Service (0x180A) not found in %d services", service_count)
            return
        
        _LOGGER.debug("Device Information Service has %d characteristics", len(device_info_service.characteristics))
        
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
            _LOGGER.debug("Found characteristic: %s with properties: %s", char.uuid, char.properties)
            
            for expected_uuid, (prop_name, attr_name) in char_mapping.items():
                if char_uuid == expected_uuid.lower():
                    _LOGGER.debug("Matched characteristic %s for %s", char.uuid, prop_name)
                    try:
                        # Check if characteristic supports read operation
                        if "read" in char.properties:
                            _LOGGER.debug("Reading characteristic %s...", prop_name)
                            data = await self._client.read_gatt_char(char.uuid)
                            if data:
                                _LOGGER.debug("Raw data for %s: %s (len=%d)", prop_name, data.hex(), len(data))
                                # Decode as UTF-8 string and strip whitespace/null bytes
                                value = data.decode('utf-8', errors='ignore').strip('\x00\r\n\t ')
                                if value:  # Only store non-empty values
                                    setattr(self, attr_name, value)
                                    _LOGGER.info("Device info - %s: %s", prop_name, value)
                                else:
                                    _LOGGER.debug("Device info - %s: (empty after decode)", prop_name)
                            else:
                                _LOGGER.debug("Device info - %s: (no data returned)", prop_name)
                        else:
                            _LOGGER.warning("Device info - %s: characteristic not readable (properties: %s)", prop_name, char.properties)
                    except Exception as e:
                        _LOGGER.error("Failed to read %s: %s", prop_name, e)
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
            _LOGGER.info("Device information: %s", ", ".join(device_info_summary))
        else:
            _LOGGER.debug("No device information characteristics found or readable")

    def _handle_notification(self, sender: int, data: bytearray) -> None:
        """Handle notification from the desk."""
        _LOGGER.debug("Received notification: %s", data.hex())
        
        # Check for height notification (0x98 0x98 header)
        if len(data) >= 6 and bytes(data[:2]) == HEIGHT_NOTIFICATION_HEADER:
            # Extract height from bytes 4-5 (little-endian)
            height_raw = data[4] | (data[5] << 8)
            new_height = height_raw / 10.0
            
            # Calculate velocity if we have previous data
            current_time = time.time()
            if self._last_notification_time > 0 and self._height_cm != new_height:
                time_diff = current_time - self._last_notification_time
                height_diff = new_height - self._height_cm
                if time_diff > 0:
                    velocity = height_diff / time_diff  # cm/s
                    self._recent_velocities.append(velocity)
                    # Keep only last 10 velocity measurements
                    if len(self._recent_velocities) > 10:
                        self._recent_velocities.pop(0)
            
            self._height_cm = new_height
            self._last_notification_time = current_time
            
            # Check for collision flag (this needs to be determined from actual data)
            # For now, we'll assume no collision detection in basic notifications
            # NOTE: Don't clear collision here - it should only be cleared by auto-clear or successful movement
            
            _LOGGER.debug("Height notification (0x98 0x98): %.1f cm", self._height_cm)
            
            # Detect actual movement start
            if not self._is_moving and self._movement_type and abs(self._height_cm - self._last_height_cm) > 0.1:
                # Movement has actually started - begin collision detection
                self._is_moving = True
                self._movement_start_time = time.time()
                self._movement_start_height = self._last_height_cm  # Record starting height
                self._height_unchanged_count = 0
                _LOGGER.debug("Movement started - collision detection enabled")
            
            # Track recent heights for bounce detection
            if self._is_moving:
                current_time = time.time()
                self._recent_heights.append((current_time, self._height_cm))
                # Keep only last 10 heights (about 3 seconds of data)  
                if len(self._recent_heights) > 10:
                    self._recent_heights.pop(0)
                
                # Bounce detection: check if direction reversed
                if self._commanded_direction and len(self._recent_heights) >= 3:
                    # Check if we've changed direction from commanded direction
                    recent_direction = self._detect_movement_direction()
                    if recent_direction and recent_direction != self._commanded_direction:
                        self._bounce_detected = True
                        self._set_collision_detected(True)
                        _LOGGER.info("Bounce-back detected! Commanded %s but now moving %s at %.1f cm", 
                                   self._commanded_direction, recent_direction, self._height_cm)
                        self._is_moving = False
                        self._movement_direction = None
                        self._commanded_direction = None
                        self._height_unchanged_count = 0
                        self._movement_start_height = None  # Reset after collision analysis
                        # Don't reset _movement_start_height here - it's needed for collision analysis
            
            # Auto-stop detection: check if height hasn't changed
            if self._is_moving and not self._bounce_detected:
                if abs(self._height_cm - self._last_height_cm) < 0.1:  # Less than 1mm change
                    self._height_unchanged_count += 1
                    if self._height_unchanged_count >= 3:  # 3 notifications without change
                        _LOGGER.debug("Auto-stop detected: height unchanged for 3 notifications")
                        # Check if movement has been going on for minimum duration
                        movement_duration = time.time() - self._movement_start_time
                        if movement_duration > 1.0:  # Require at least 1 second of movement
                            # Check if this is a collision based on movement type
                            is_collision = self._is_collision_stop()
                            if is_collision:
                                self._set_collision_detected(True)
                                _LOGGER.info("Collision detected at %.1f cm after %.1f seconds", 
                                           self._height_cm, movement_duration)
                            else:
                                _LOGGER.debug("Normal stop at %.1f cm after %.1f seconds", 
                                           self._height_cm, movement_duration)
                        else:
                            _LOGGER.debug("Auto-stop after %.1f seconds - too short for collision", 
                                        movement_duration)
                        self._is_moving = False
                        self._movement_direction = None
                        self._height_unchanged_count = 0
                else:
                    self._height_unchanged_count = 0
                    self._last_height_cm = self._height_cm
                    
                    # Clear collision if we've been moving successfully for a while AFTER collision was detected
                    if self._collision_detected and self._collision_time:
                        time_since_collision = time.time() - self._collision_time
                        if time_since_collision > 2.0:
                            _LOGGER.info("Clearing collision state after %.1f seconds of successful movement", time_since_collision)
                            self._set_collision_detected(False)
            
            # Notify callbacks
            for callback in self._notification_callbacks:
                callback(self._height_cm, self._collision_detected, self._is_moving)
        
        # Check for status notification (0xF2 0xF2 0x01 0x03 header)
        elif len(data) >= 6 and bytes(data[:4]) == STATUS_NOTIFICATION_HEADER:
            # Extract height from bytes 4-5 (big-endian for status notifications)
            height_raw = (data[4] << 8) | data[5]
            new_height = height_raw / 10.0
            
            # Calculate velocity if we have previous data
            current_time = time.time()
            if self._last_notification_time > 0 and self._height_cm != new_height:
                time_diff = current_time - self._last_notification_time
                height_diff = new_height - self._height_cm
                if time_diff > 0:
                    velocity = height_diff / time_diff  # cm/s
                    self._recent_velocities.append(velocity)
                    # Keep only last 10 velocity measurements
                    if len(self._recent_velocities) > 10:
                        self._recent_velocities.pop(0)
            
            self._height_cm = new_height
            self._last_notification_time = current_time
            
            # Check for collision flag (this needs to be determined from actual data)
            # For now, we'll assume no collision detection in basic notifications
            # NOTE: Don't clear collision here - it should only be cleared by auto-clear or successful movement
            
            _LOGGER.debug("Status notification (0xF2 0xF2 0x01 0x03): %.1f cm", self._height_cm)
            
            # Detect actual movement start
            if not self._is_moving and self._movement_type and abs(self._height_cm - self._last_height_cm) > 0.1:
                # Movement has actually started - begin collision detection
                self._is_moving = True
                self._movement_start_time = time.time()
                self._movement_start_height = self._last_height_cm  # Record starting height
                self._height_unchanged_count = 0
                _LOGGER.debug("Movement started - collision detection enabled")
            
            # Track recent heights for bounce detection
            if self._is_moving:
                current_time = time.time()
                self._recent_heights.append((current_time, self._height_cm))
                # Keep only last 10 heights
                if len(self._recent_heights) > 10:
                    self._recent_heights.pop(0)
                
                # Bounce detection: check if direction reversed
                if self._commanded_direction and len(self._recent_heights) >= 3:
                    # Check if we've changed direction from commanded direction
                    recent_direction = self._detect_movement_direction()
                    if recent_direction and recent_direction != self._commanded_direction:
                        self._bounce_detected = True
                        self._set_collision_detected(True)
                        _LOGGER.info("Bounce-back detected! Commanded %s but now moving %s at %.1f cm", 
                                   self._commanded_direction, recent_direction, self._height_cm)
                        self._is_moving = False
                        self._movement_direction = None
                        self._commanded_direction = None
                        self._height_unchanged_count = 0
                        self._movement_start_height = None  # Reset after collision analysis
                        # Don't reset _movement_start_height here - it's needed for collision analysis
            
            # Auto-stop detection for status notifications too
            if self._is_moving and not self._bounce_detected:
                if abs(self._height_cm - self._last_height_cm) < 0.1:  # Less than 1mm change
                    self._height_unchanged_count += 1
                    if self._height_unchanged_count >= 3:  # 3 notifications without change
                        _LOGGER.debug("Auto-stop detected: height unchanged for 3 notifications")
                        # Check if movement has been going on for minimum duration
                        movement_duration = time.time() - self._movement_start_time
                        if movement_duration > 1.0:  # Require at least 1 second of movement
                            # Check if this is a collision based on movement type
                            is_collision = self._is_collision_stop()
                            if is_collision:
                                self._set_collision_detected(True)
                                _LOGGER.info("Collision detected at %.1f cm after %.1f seconds", 
                                           self._height_cm, movement_duration)
                            else:
                                _LOGGER.debug("Normal stop at %.1f cm after %.1f seconds", 
                                           self._height_cm, movement_duration)
                        else:
                            _LOGGER.debug("Auto-stop after %.1f seconds - too short for collision", 
                                        movement_duration)
                        self._is_moving = False
                        self._movement_direction = None
                        self._height_unchanged_count = 0
                else:
                    self._height_unchanged_count = 0
                    self._last_height_cm = self._height_cm
                    
                    # Clear collision if we've been moving successfully for a while AFTER collision was detected
                    if self._collision_detected and self._collision_time:
                        time_since_collision = time.time() - self._collision_time
                        if time_since_collision > 2.0:
                            _LOGGER.info("Clearing collision state after %.1f seconds of successful movement", time_since_collision)
                            self._set_collision_detected(False)
            
            # Notify callbacks
            for callback in self._notification_callbacks:
                callback(self._height_cm, self._collision_detected, self._is_moving)
        
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
        
        # Check for upper limit response
        elif len(data) >= 7 and bytes(data[:4]) == LIMIT_UPPER_RESPONSE_HEADER:
            height_raw = (data[4] << 8) | data[5]
            self._height_limit_upper = height_raw / 10.0
            _LOGGER.debug("Upper limit response: %.1f cm", self._height_limit_upper)
        
        # Check for lower limit response
        elif len(data) >= 7 and bytes(data[:4]) == LIMIT_LOWER_RESPONSE_HEADER:
            height_raw = (data[4] << 8) | data[5]
            self._height_limit_lower = height_raw / 10.0
            _LOGGER.debug("Lower limit response: %.1f cm", self._height_limit_lower)
        
        # Check for limit status response (0xF2 0xF2 0x20 0x01)
        elif len(data) >= 6 and bytes(data[:5]) == bytes([0xF2, 0xF2, 0x20, 0x01, 0x00]):
            # No limits
            self._limits_enabled = False
            _LOGGER.debug("No limits set")
        elif len(data) >= 6 and bytes(data[:5]) == bytes([0xF2, 0xF2, 0x20, 0x01, 0x01]):
            # Upper limit only
            self._limits_enabled = True
            _LOGGER.debug("Upper limit only set")
        elif len(data) >= 6 and bytes(data[:5]) == bytes([0xF2, 0xF2, 0x20, 0x01, 0x10]):
            # Lower limit only
            self._limits_enabled = True
            _LOGGER.debug("Lower limit only set")
        elif len(data) >= 6 and bytes(data[:5]) == bytes([0xF2, 0xF2, 0x20, 0x01, 0x11]):
            # Both limits set
            self._limits_enabled = True
            _LOGGER.debug("Both limits set")
        
        else:
            _LOGGER.debug("Unknown notification format: %s", data.hex())

    def _detect_movement_direction(self) -> str | None:
        """Detect movement direction from recent height changes."""
        if len(self._recent_heights) < 2:
            return None
        
        # Compare last few heights to determine direction
        recent_changes = []
        for i in range(1, min(4, len(self._recent_heights))):
            if i < len(self._recent_heights):
                height_diff = self._recent_heights[-1][1] - self._recent_heights[-(i+1)][1]
                if abs(height_diff) > 0.1:  # More than 1mm change
                    recent_changes.append(height_diff)
        
        if not recent_changes:
            return None
        
        # Determine overall direction from recent changes
        avg_change = sum(recent_changes) / len(recent_changes)
        if avg_change > 0.1:
            return "up"
        elif avg_change < -0.1:
            return "down"
        return None

    def _get_average_velocity(self) -> float:
        """Get average velocity from recent measurements."""
        if not self._recent_velocities:
            return 0.0
        return sum(self._recent_velocities) / len(self._recent_velocities)

    def _is_collision_stop(self) -> bool:
        """Determine if current stop is a collision based on movement type and context."""
        if self._movement_type == "continuous":
            # For manual up/down movements, analyze movement patterns like presets
            movement_duration = time.time() - self._movement_start_time
            
            # Calculate movement distance and average speed
            if hasattr(self, '_movement_start_height') and self._movement_start_height is not None:
                distance_moved = abs(self._height_cm - self._movement_start_height)
                avg_overall_speed = distance_moved / movement_duration if movement_duration > 0 else 0
                avg_recent_velocity = abs(self._get_average_velocity())  # Get recent velocity magnitude
                
                _LOGGER.debug("Continuous movement: %.1f cm in %.1f seconds (overall: %.2f cm/s, recent: %.2f cm/s)", 
                            distance_moved, movement_duration, avg_overall_speed, avg_recent_velocity)
                
                # If minimal movement occurred, likely a collision
                if distance_moved < 0.5:  # Less than 5mm movement
                    _LOGGER.debug("Continuous collision: minimal movement (%.1f cm)", distance_moved)
                    return True
                
                # Check recent velocity for signs of collision (very slow recent movement)
                if len(self._recent_velocities) >= 3 and avg_recent_velocity < 0.3:
                    _LOGGER.debug("Continuous collision: recent velocity too slow (%.2f cm/s)", avg_recent_velocity)
                    return True
                
                # If overall movement was too slow, likely hit an obstacle
                if avg_overall_speed < 0.5:  # Less than 0.5 cm/s average speed
                    _LOGGER.debug("Continuous collision: abnormally slow overall movement (%.2f cm/s)", avg_overall_speed)
                    return True
                
                # For normal continuous movements (reasonable distance and speed), not a collision
                if distance_moved >= 0.5 and avg_overall_speed >= 0.5:
                    _LOGGER.debug("Normal continuous stop: %.1f cm at %.2f cm/s", 
                                distance_moved, avg_overall_speed)
                    return False
            
            # Fallback: very short movements (< 0.5s) are likely user releasing button, not collisions
            if movement_duration < 0.5:
                _LOGGER.debug("Very short continuous movement (%.1f s) - likely user released button", movement_duration)
                return False
            elif movement_duration > 10.0:  # Very long movement might indicate collision
                _LOGGER.debug("Very long continuous movement (%.1f s) - possible collision", movement_duration)
                return True
            else:
                _LOGGER.debug("Normal duration continuous movement (%.1f s) - likely user released button", movement_duration)
                return False
        
        elif self._movement_type == "targeted" and self._target_height is not None:
            # First check if we hit a physical height limit
            from .const import MIN_HEIGHT, MAX_HEIGHT
            height_limit_tolerance = 3.0  # Allow 3cm tolerance for height limits
            
            # Check if we're near the minimum height limit
            if self._height_cm <= MIN_HEIGHT + height_limit_tolerance:
                if self._target_height < self._height_cm:  # Was trying to go down
                    _LOGGER.debug("Hit minimum height limit at %.1f cm (target: %.1f cm)", 
                                self._height_cm, self._target_height)
                    return False
            
            # Check if we're near the maximum height limit  
            # This handles cases where desk can't reach the configured maximum
            if self._target_height >= MAX_HEIGHT - 1.0:  # Target was near max height
                if self._target_height > self._height_cm:  # Was trying to go up
                    # If we stopped within reasonable range of maximum, likely hit physical limit
                    distance_from_max = MAX_HEIGHT - self._height_cm
                    if distance_from_max <= 8.0:  # Within 8cm of configured maximum
                        _LOGGER.debug("Hit maximum height limit at %.1f cm (target: %.1f cm, %.1f cm from max)", 
                                    self._height_cm, self._target_height, distance_from_max)
                        return False
            
            # For targeted movements, check if we're close to the target
            height_tolerance = 1.0  # Allow 1cm tolerance
            at_target = abs(self._height_cm - self._target_height) <= height_tolerance
            if at_target:
                _LOGGER.debug("Reached target height %.1f cm (current: %.1f cm)", 
                            self._target_height, self._height_cm)
                return False
            else:
                _LOGGER.debug("Stopped at %.1f cm, away from target %.1f cm", 
                            self._height_cm, self._target_height)
                return True
        
        elif self._movement_type == "preset":
            # For preset movements, analyze movement patterns instead of arbitrary time threshold
            movement_duration = time.time() - self._movement_start_time
            
            # Calculate movement distance and average speed
            if hasattr(self, '_movement_start_height') and self._movement_start_height is not None:
                distance_moved = abs(self._height_cm - self._movement_start_height)
                avg_overall_speed = distance_moved / movement_duration if movement_duration > 0 else 0
                avg_recent_velocity = abs(self._get_average_velocity())  # Get recent velocity magnitude
                
                _LOGGER.debug("Preset movement: %.1f cm in %.1f seconds (overall: %.2f cm/s, recent: %.2f cm/s)", 
                            distance_moved, movement_duration, avg_overall_speed, avg_recent_velocity)
                
                # If minimal movement occurred, likely a collision
                if distance_moved < 0.5:  # Less than 5mm movement
                    _LOGGER.debug("Preset collision: minimal movement (%.1f cm)", distance_moved)
                    return True
                
                # Check recent velocity for signs of collision (very slow recent movement)
                if len(self._recent_velocities) >= 3 and avg_recent_velocity < 0.3:
                    _LOGGER.debug("Preset collision: recent velocity too slow (%.2f cm/s)", avg_recent_velocity)
                    return True
                
                # If overall movement was too slow, likely hit an obstacle
                if avg_overall_speed < 0.5:  # Less than 0.5 cm/s average speed
                    _LOGGER.debug("Preset collision: abnormally slow overall movement (%.2f cm/s)", avg_overall_speed)
                    return True
                
                # Check for abnormally short movement duration with significant distance
                # This indicates the desk reached its preset position normally
                if movement_duration < 0.5 and distance_moved > 2.0:
                    _LOGGER.debug("Preset reached quickly: %.1f cm in %.1f seconds", 
                                distance_moved, movement_duration)
                    return False
                
                # For normal preset movements (reasonable distance and speed), not a collision
                if distance_moved >= 1.0 and avg_overall_speed >= 1.0:
                    _LOGGER.debug("Normal preset completion: %.1f cm at %.2f cm/s", 
                                distance_moved, avg_overall_speed)
                    return False
            
            # Fallback: if we can't calculate distance, use improved time-based logic
            # Very short movements are likely preset completions, very long ones might be collisions
            if movement_duration < 1.0:
                _LOGGER.debug("Short preset movement (%.1f s) - likely reached preset", movement_duration)
                return False
            elif movement_duration > 10.0:  # Much longer threshold than before
                _LOGGER.debug("Very long preset movement (%.1f s) - possible collision", movement_duration)
                return True
            else:
                _LOGGER.debug("Normal duration preset movement (%.1f s) - likely completed normally", movement_duration)
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
                _LOGGER.info("Auto-clearing collision state after %.0f seconds", 
                           COLLISION_AUTO_CLEAR_SECONDS)
                self._collision_detected = False
                self._collision_time = None
                # Notify callbacks about the state change
                for callback in self._notification_callbacks:
                    callback(self._height_cm, self._collision_detected, self._is_moving)
        
        # Schedule the task only if there's a running event loop
        try:
            loop = asyncio.get_running_loop()
            self._auto_clear_task = asyncio.create_task(auto_clear())
        except RuntimeError:
            # No event loop running (e.g., in sync tests)
            _LOGGER.debug("No event loop available for auto-clear scheduling")
    
    def _cancel_collision_auto_clear(self) -> None:
        """Cancel any pending collision auto-clear task."""
        if self._auto_clear_task and not self._auto_clear_task.done():
            self._auto_clear_task.cancel()
        self._auto_clear_task = None

    def _handle_disconnect(self, client: BleakClient) -> None:
        """Handle disconnection from the desk."""
        _LOGGER.warning("Disconnected from Desky desk")
        self._client = None
        self._is_moving = False
        self._movement_direction = None
        
        # Cancel any pending auto-clear task
        self._cancel_collision_auto_clear()
        
        # Notify callbacks
        for callback in self._disconnect_callbacks:
            callback()