"""Constants for the Desky Desk integration."""
from typing import Final

DOMAIN: Final = "desky_desk"

# BLE Service and Characteristic UUIDs
SERVICE_UUID: Final = "00001800-0000-1000-8000-00805f9b34fb"  # Generic Access
WRITE_CHARACTERISTIC_UUID: Final = "00002a00-0000-1000-8000-00805f9b34fb"
NOTIFY_CHARACTERISTIC_UUID: Final = "00002a01-0000-1000-8000-00805f9b34fb"

# BLE Commands (converted from Java byte arrays to Python bytes)
COMMAND_MOVE_UP: Final = bytes([0xF1, 0xF1, 0x01, 0x00, 0x01, 0x7E])
COMMAND_MOVE_DOWN: Final = bytes([0xF1, 0xF1, 0x02, 0x00, 0x02, 0x7E])
COMMAND_STOP: Final = bytes([0xF1, 0xF1, 0x2B, 0x00, 0x2B, 0x7E])
COMMAND_GET_STATUS: Final = bytes([0xF1, 0xF1, 0x07, 0x00, 0x07, 0x7E])
COMMAND_MEMORY_1: Final = bytes([0xF1, 0xF1, 0x05, 0x00, 0x05, 0x7E])
COMMAND_MEMORY_2: Final = bytes([0xF1, 0xF1, 0x06, 0x00, 0x06, 0x7E])
COMMAND_MEMORY_3: Final = bytes([0xF1, 0xF1, 0x27, 0x00, 0x27, 0x7E])
COMMAND_MEMORY_4: Final = bytes([0xF1, 0xF1, 0x28, 0x00, 0x28, 0x7E])

# Height notification header
HEIGHT_NOTIFICATION_HEADER: Final = bytes([0x98, 0x98])

# Desk height limits (in cm)
MIN_HEIGHT: Final = 60.0
MAX_HEIGHT: Final = 130.0
DEFAULT_HEIGHT: Final = 75.0

# Update intervals
UPDATE_INTERVAL_SECONDS: Final = 1
RECONNECT_INTERVAL_SECONDS: Final = 30

# Entity attributes
ATTR_HEIGHT_CM: Final = "height_cm"
ATTR_COLLISION_DETECTED: Final = "collision_detected"
ATTR_MOVING: Final = "moving"

# Cover position constants
COVER_CLOSED_POSITION: Final = 0  # Desk at minimum height
COVER_OPEN_POSITION: Final = 100  # Desk at maximum height