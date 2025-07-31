"""Constants for the Desky Desk integration."""
from typing import Final

DOMAIN: Final = "desky_desk"

# BLE Service and Characteristic UUIDs
SERVICE_UUID: Final = "0000fe60-0000-1000-8000-00805f9b34fb"  # Desky Service
WRITE_CHARACTERISTIC_UUID: Final = "0000fe61-0000-1000-8000-00805f9b34fb"
NOTIFY_CHARACTERISTIC_UUID: Final = "0000fe62-0000-1000-8000-00805f9b34fb"

# BLE Commands (converted from Java byte arrays to Python bytes)
COMMAND_HANDSHAKE: Final = bytes([0xF1, 0xF1, 0xFE, 0x00, 0xFE, 0x7E])  # Required initialization
COMMAND_MOVE_UP: Final = bytes([0xF1, 0xF1, 0x01, 0x00, 0x01, 0x7E])
COMMAND_MOVE_DOWN: Final = bytes([0xF1, 0xF1, 0x02, 0x00, 0x02, 0x7E])
COMMAND_STOP: Final = bytes([0xF1, 0xF1, 0x2B, 0x00, 0x2B, 0x7E])
COMMAND_GET_STATUS: Final = bytes([0xF1, 0xF1, 0x07, 0x00, 0x07, 0x7E])
COMMAND_MEMORY_1: Final = bytes([0xF1, 0xF1, 0x05, 0x00, 0x05, 0x7E])
COMMAND_MEMORY_2: Final = bytes([0xF1, 0xF1, 0x06, 0x00, 0x06, 0x7E])
COMMAND_MEMORY_3: Final = bytes([0xF1, 0xF1, 0x27, 0x00, 0x27, 0x7E])
COMMAND_MEMORY_4: Final = bytes([0xF1, 0xF1, 0x28, 0x00, 0x28, 0x7E])

# Move to specific height command structure:
# bytes([0xF1, 0xF1, 0x1B, 0x02, height_high_byte, height_low_byte, checksum, 0x7E])
# where height is in mm (e.g., 850mm = 0x0352, so high=0x03, low=0x52)
# checksum = (0x1B + 0x02 + height_high + height_low) & 0xFF

# Height notification header
HEIGHT_NOTIFICATION_HEADER: Final = bytes([0x98, 0x98])

# Desk height limits (in cm)
MIN_HEIGHT: Final = 60.0
MAX_HEIGHT: Final = 130.0
DEFAULT_HEIGHT: Final = 75.0

# Update intervals
UPDATE_INTERVAL_SECONDS: Final = 30
RECONNECT_INTERVAL_SECONDS: Final = 30

# Connection timeouts
DIRECT_CONNECTION_TIMEOUT: Final = 20.0  # Direct Bluetooth connection
PROXY_CONNECTION_TIMEOUT: Final = 30.0   # ESPHome proxy connection
PROXY_MAX_ATTEMPTS: Final = 5            # Retry attempts for proxy
DIRECT_MAX_ATTEMPTS: Final = 3           # Retry attempts for direct

# Entity attributes
ATTR_HEIGHT_CM: Final = "height_cm"
ATTR_COLLISION_DETECTED: Final = "collision_detected"
ATTR_MOVING: Final = "moving"

# Cover position constants
COVER_CLOSED_POSITION: Final = 0  # Desk at minimum height
COVER_OPEN_POSITION: Final = 100  # Desk at maximum height