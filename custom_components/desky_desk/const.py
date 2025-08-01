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

# Additional commands discovered from Android app
# Lighting commands
COMMAND_GET_LIGHT_COLOR: Final = bytes([0xF1, 0xF1, 0xB4, 0x00, 0xB4, 0x7E])
COMMAND_GET_BRIGHTNESS: Final = bytes([0xF1, 0xF1, 0xB6, 0x00, 0xB6, 0x7E])
COMMAND_GET_LIGHTING: Final = bytes([0xF1, 0xF1, 0xB5, 0x00, 0xB5, 0x7E])

# Vibration commands
COMMAND_GET_VIBRATION: Final = bytes([0xF1, 0xF1, 0xB3, 0x00, 0xB3, 0x7E])
COMMAND_GET_VIBRATION_INTENSITY: Final = bytes([0xF1, 0xF1, 0xA4, 0x00, 0xA4, 0x7E])

# Lock commands
COMMAND_GET_LOCK_STATUS: Final = bytes([0xF1, 0xF1, 0xB2, 0x00, 0xB2, 0x7E])

# Sensitivity/Anti-collision commands
COMMAND_GET_SENSITIVITY: Final = bytes([0xF1, 0xF1, 0x1D, 0x00, 0x1D, 0x7E])

# Height limit commands
COMMAND_GET_LIMITS: Final = bytes([0xF1, 0xF1, 0x0C, 0x00, 0x0C, 0x7E])
COMMAND_CLEAR_LIMITS: Final = bytes([0xF1, 0xF1, 0x23, 0x00, 0x23, 0x7E])

# Controller info command
COMMAND_CONTROLLER_DATA: Final = bytes([0xF1, 0xF1, 0xFE, 0x00, 0xFE, 0x7E])  # Same as handshake

# Move to specific height command structure:
# bytes([0xF1, 0xF1, 0x1B, 0x02, height_high_byte, height_low_byte, checksum, 0x7E])
# where height is in mm (e.g., 850mm = 0x0352, so high=0x03, low=0x52)
# checksum = (0x1B + 0x02 + height_high + height_low) & 0xFF

# Height notification headers
HEIGHT_NOTIFICATION_HEADER: Final = bytes([0x98, 0x98])  # Movement/real-time notifications
STATUS_NOTIFICATION_HEADER: Final = bytes([0xF2, 0xF2, 0x01, 0x03])  # Status response notifications

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

# Response headers for device features
LIGHT_COLOR_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0xB4, 0x01])
BRIGHTNESS_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0xB6, 0x01])
LIGHTING_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0xB5, 0x01])
VIBRATION_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0xB3, 0x01])
VIBRATION_INTENSITY_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0xA4, 0x01])
LOCK_STATUS_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0xB2, 0x01])
SENSITIVITY_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0x1D, 0x01])
LIMIT_UPPER_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0x21, 0x02])
LIMIT_LOWER_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0x22, 0x02])
LIMIT_STATUS_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0x20, 0x01])

# Light color options
LIGHT_COLORS: Final = {
    1: "White",
    2: "Red", 
    3: "Green",
    4: "Blue",
    5: "Yellow",
    6: "Party mode",
    7: "Off"
}

# Sensitivity levels
SENSITIVITY_LEVELS: Final = {
    1: "High",
    2: "Medium",
    3: "Low"
}

# Touch modes
TOUCH_MODES: Final = {
    0: "One press",
    1: "Press and hold"
}