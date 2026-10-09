"""Constants for the Desky Desk integration."""

from enum import StrEnum
from typing import Final

DOMAIN: Final = "desky_desk"

# BLE Service and Characteristic UUIDs
WRITE_CHARACTERISTIC_UUID: Final = "0000fe61-0000-1000-8000-00805f9b34fb"
NOTIFY_CHARACTERISTIC_UUID: Final = "0000fe62-0000-1000-8000-00805f9b34fb"

# BLE Device Information Service (0x180A) - Standard GATT service
DEVICE_INFORMATION_SERVICE_UUID: Final = "0000180a-0000-1000-8000-00805f9b34fb"
MANUFACTURER_NAME_CHAR_UUID: Final = "00002a29-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER_CHAR_UUID: Final = "00002a24-0000-1000-8000-00805f9b34fb"
SERIAL_NUMBER_CHAR_UUID: Final = "00002a25-0000-1000-8000-00805f9b34fb"
HARDWARE_REVISION_CHAR_UUID: Final = "00002a27-0000-1000-8000-00805f9b34fb"
FIRMWARE_REVISION_CHAR_UUID: Final = "00002a26-0000-1000-8000-00805f9b34fb"
SOFTWARE_REVISION_CHAR_UUID: Final = "00002a28-0000-1000-8000-00805f9b34fb"

# BLE Commands (converted from Java byte arrays to Python bytes)
COMMAND_HANDSHAKE: Final = bytes(
    [0xF1, 0xF1, 0xFE, 0x00, 0xFE, 0x7E]
)  # Required initialization
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

# Lock commands
COMMAND_GET_LOCK_STATUS: Final = bytes([0xF1, 0xF1, 0xB2, 0x00, 0xB2, 0x7E])

# Height limit commands
COMMAND_GET_LIMITS: Final = bytes([0xF1, 0xF1, 0x0C, 0x00, 0x0C, 0x7E])
COMMAND_CLEAR_LIMITS: Final = bytes([0xF1, 0xF1, 0x23, 0x00, 0x23, 0x7E])

# Move to specific height command structure:
# bytes([0xF1, 0xF1, 0x1B, 0x02, height_high_byte, height_low_byte, checksum, 0x7E])
# where height is in mm (e.g., 850mm = 0x0352, so high=0x03, low=0x52)
# checksum = (0x1B + 0x02 + height_high + height_low) & 0xFF

# Height notification headers
HEIGHT_NOTIFICATION_HEADER: Final = bytes(
    [0x98, 0x98]
)  # Movement/real-time notifications
STATUS_NOTIFICATION_HEADER: Final = bytes(
    [0xF2, 0xF2, 0x01, 0x03]
)  # Status response notifications

# Desk height limits (in cm)
CM_PER_INCH: Final = 2.54
MIN_HEIGHT: Final = 60.0
MAX_HEIGHT: Final = 130.0

# Height limits the desk accepts, in cm, by the unit the limit is sent in; it
# ignores a limit outside them without an error. The official app allows the
# same: 60-124 cm, or 24-48 in, here rounded inwards to 0.1 cm.
LIMIT_RANGE_CM: Final = {
    "cm": (60.0, 124.0),
    "in": (round(24 * CM_PER_INCH, 1), round(48 * CM_PER_INCH, 1)),
}

# Posture: a desk stopped at or above the standing threshold counts as standing
CONF_STANDING_THRESHOLD: Final = "standing_threshold"
DEFAULT_STANDING_THRESHOLD: Final = 95
# The height must stay unchanged this long before the posture follows it, so
# passing through the threshold mid-move is not a posture change
POSTURE_SETTLE_SECONDS: Final = 2


class Posture(StrEnum):
    """Where the desk has stopped: below or at least at the standing threshold."""

    SITTING = "sitting"
    STANDING = "standing"


class HeightLimit(StrEnum):
    """The desk's two height limits."""

    UPPER = "upper"
    LOWER = "lower"


# Update intervals
UPDATE_INTERVAL_SECONDS: Final = 30
# Delay before retrying a failed reconnect, doubling up to the maximum, so a
# desk that keeps refusing does not tie up a proxy's connection slots
RECONNECT_BACKOFF_MIN_SECONDS: Final = 5
RECONNECT_BACKOFF_MAX_SECONDS: Final = 120

# Cover position constants
COVER_CLOSED_POSITION: Final = 0  # Desk at minimum height

# Response headers for device features
LIGHT_COLOR_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0xB4, 0x01])
BRIGHTNESS_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0xB6, 0x01])
LIGHTING_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0xB5, 0x01])
VIBRATION_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0xB3, 0x01])
LOCK_STATUS_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0xB2, 0x01])
SENSITIVITY_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0x1D, 0x01])
LIMIT_UPPER_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0x21, 0x02])
LIMIT_LOWER_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0x22, 0x02])
LIMIT_STATUS_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0x20, 0x01])
# Sent with the settings block after a handshake and a status request, and
# unprompted when the setting changes on the hand controller
UNIT_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0x0E, 0x01])
TOUCH_MODE_RESPONSE_HEADER: Final = bytes([0xF2, 0xF2, 0x19, 0x01])

# Colours that mean the LED is off: the desk reports 7 as Off, and the official
# app turns the LED off by setting 0
OFF_COLORS: Final = frozenset({0, 7})

# Sensitivity levels
SENSITIVITY_LEVELS: Final = {1: "high", 2: "medium", 3: "low"}

# Touch modes
TOUCH_MODES: Final = {0: "one_press", 1: "press_and_hold"}
TOUCH_MODE_PRESS_AND_HOLD: Final = 1

# Display units, as reported in the unit response
DISPLAY_UNITS: Final = {0: "cm", 1: "in"}
