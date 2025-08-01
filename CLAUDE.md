# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

**IMPORTANT**: All Python commands should be run within an activated virtual environment (see Virtual Environment Setup below).

### Testing the Integration
```bash
# Activate virtual environment first (see Virtual Environment Setup)
source venv/bin/activate  # On Unix/macOS
# OR
venv\Scripts\activate     # On Windows

# Run Home Assistant in development mode with this integration
hass -c config --debug

# Validate HACS compatibility
hacs validate

# Check integration structure
python -m pytest tests/
```

### Development Setup
1. Clone this repository into `custom_components/desky_desk` in your Home Assistant config directory
2. Set up a virtual environment (see Virtual Environment Setup below)
3. Enable debug logging by adding to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.desky_desk: debug
```

### Virtual Environment Setup
Always use a virtual environment when working with this project to avoid dependency conflicts:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Unix/macOS:
source venv/bin/activate

# On Windows:
venv\Scripts\activate

# Install test dependencies
pip install -r requirements_test.txt

# When done working, deactivate virtual environment
deactivate
```

## Codebase Architecture

### Integration Structure
This is a Home Assistant custom integration that follows the standard component structure:

- **Entry Point** (`__init__.py`): Sets up the integration, defines platforms (cover, number, button, binary_sensor, light, switch, select, sensor), and manages config entry lifecycle
- **Data Coordinator** (`coordinator.py`): Implements `DataUpdateCoordinator` pattern for centralized data updates and connection management
- **Bluetooth Layer** (`bluetooth.py`): Handles BLE communication using `bleak` library with retry logic via `bleak-retry-connector`
- **Config Flow** (`config_flow.py`): Manages integration setup through UI, including Bluetooth device discovery
- **Platform Entities**: Each platform file (cover.py, number.py, etc.) implements specific Home Assistant entities

### Key Design Patterns

1. **Coordinator Pattern**: All entities receive updates through a central `DeskUpdateCoordinator` that manages:
   - Bluetooth connection state
   - Periodic status polling (30-second intervals)
   - Automatic reconnection attempts
   - Data distribution to all entities
   - Movement direction tracking for proper cover state

2. **Bluetooth Communication**:
   - Uses characteristic UUIDs for write (0xfe61) and notify (0xfe62)
   - Commands are typically 6-8 byte arrays with checksum
   - Handshake command (0xFE) must be sent after connection to enable movement
   - Height notifications can have different headers depending on firmware version
   - Height calculation: `(byte4 | (byte5 << 8)) / 10.0` cm

3. **Entity Implementation**:
   - Cover entity: Main control interface (0-100% position mapping) with proper direction tracking
   - Number entities: Direct height control (60-130cm range), height limits, vibration intensity
   - Button entities: Four preset positions + manual Move Up/Down controls
   - Binary sensor: Collision detection
   - Light entity: LED strip control with color, brightness, and effects
   - Switch entities: Vibration on/off, desk lock
   - Select entities: Collision sensitivity, touch mode, unit preference
   - Sensor entities: Height display with units, light color name, sensitivity level

### BLE Protocol Commands
```python
COMMAND_HANDSHAKE = bytes([0xF1, 0xF1, 0xFE, 0x00, 0xFE, 0x7E])  # Required initialization
COMMAND_MOVE_UP = bytes([0xF1, 0xF1, 0x01, 0x00, 0x01, 0x7E])
COMMAND_MOVE_DOWN = bytes([0xF1, 0xF1, 0x02, 0x00, 0x02, 0x7E])
COMMAND_STOP = bytes([0xF1, 0xF1, 0x2B, 0x00, 0x2B, 0x7E])
COMMAND_MEMORY_1 = bytes([0xF1, 0xF1, 0x05, 0x00, 0x05, 0x7E])
COMMAND_MEMORY_2 = bytes([0xF1, 0xF1, 0x06, 0x00, 0x06, 0x7E])
COMMAND_MEMORY_3 = bytes([0xF1, 0xF1, 0x27, 0x00, 0x27, 0x7E])
COMMAND_MEMORY_4 = bytes([0xF1, 0xF1, 0x28, 0x00, 0x28, 0x7E])

# Additional commands for advanced features
COMMAND_GET_LIGHT_COLOR = bytes([0xF1, 0xF1, 0xB4, 0x00, 0xB4, 0x7E])
COMMAND_GET_BRIGHTNESS = bytes([0xF1, 0xF1, 0xB6, 0x00, 0xB6, 0x7E])
COMMAND_GET_LIGHTING = bytes([0xF1, 0xF1, 0xB5, 0x00, 0xB5, 0x7E])
COMMAND_GET_VIBRATION = bytes([0xF1, 0xF1, 0xB3, 0x00, 0xB3, 0x7E])
COMMAND_GET_LOCK_STATUS = bytes([0xF1, 0xF1, 0xB2, 0x00, 0xB2, 0x7E])
COMMAND_GET_SENSITIVITY = bytes([0xF1, 0xF1, 0x1D, 0x00, 0x1D, 0x7E])
COMMAND_GET_LIMITS = bytes([0xF1, 0xF1, 0x0C, 0x00, 0x0C, 0x7E])
COMMAND_CLEAR_LIMITS = bytes([0xF1, 0xF1, 0x23, 0x00, 0x23, 0x7E])

# Move to specific height command structure:
# bytes([0xF1, 0xF1, 0x1B, 0x02, height_high_byte, height_low_byte, checksum, 0x7E])
# where height is in mm (e.g., 850mm = 0x0352, so high=0x03, low=0x52)
# checksum = (0x1B + 0x02 + height_high + height_low) & 0xFF

# Set commands with parameters use similar structure:
# bytes([0xF1, 0xF1, command_byte, 0x01, value, checksum, 0x7E])
# where checksum = (command_byte + 0x01 + value) & 0xFF
```

### BLE Notification Formats

The desk can send height updates in two different formats depending on firmware version:

1. **Movement Notification** (0x98 0x98):
   - Header: `0x98 0x98` (bytes 0-1)
   - Height data: bytes 4-5 (little-endian)
   - Typically sent during desk movement
   - Example: `98 98 00 00 52 03` = 85.0 cm (0x0352 = 850 / 10.0)
   - Calculation: `(byte4 | (byte5 << 8)) / 10.0` cm

2. **Status Response Notification** (0xF2 0xF2 0x01 0x03):
   - Header: `0xF2 0xF2 0x01 0x03` (bytes 0-3)
   - Height data: bytes 4-5 (big-endian)
   - Sent in response to GET_STATUS command
   - Example: `F2 F2 01 03 02 D0` = 72.0 cm (0x02D0 = 720 / 10.0)
   - Calculation: `((byte4 << 8) | byte5) / 10.0` cm

Note: The two formats use different byte orders for height data - movement notifications use little-endian while status notifications use big-endian.

### Advanced Feature Response Formats

Additional device features send responses with specific headers:

1. **Light Color Response** (0xF2 0xF2 0xB4 0x01):
   - Values: 1=White, 2=Red, 3=Green, 4=Blue, 5=Yellow, 6=Party mode, 7=Off

2. **Brightness Response** (0xF2 0xF2 0xB6 0x01):
   - Value: 0-100 (percentage)

3. **Lock Status Response** (0xF2 0xF2 0xB2 0x01):
   - Value: 0=Unlocked, 1=Locked

4. **Sensitivity Response** (0xF2 0xF2 0x1D 0x01):
   - Values: 1=High, 2=Medium, 3=Low

5. **Height Limit Responses**:
   - Upper limit (0xF2 0xF2 0x21 0x02): Height in mm (big-endian)
   - Lower limit (0xF2 0xF2 0x22 0x02): Height in mm (big-endian)
   - Limit status (0xF2 0xF2 0x20 0x01): 0x00=No limits, 0x01=Upper only, 0x10=Lower only, 0x11=Both

### Troubleshooting Height Updates

If height updates aren't working:

1. Enable debug logging to see notification format:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.desky_desk: debug
   ```

2. Check logs for "Received notification:" entries
3. Look for either "Height notification (0x98 0x98):" or "Status notification (0xF2 0xF2 0x01 0x03):"
4. Verify which format your desk uses
5. Report the notification format in issues for debugging

### Service Implementations

The integration provides these custom services:
- `move_to_height`: Sends direct height command to desk using the 0x1B command
- `move_to_preset`: Sends preset command via Bluetooth
- `set_position_limit`: Sets minimum or maximum height limit
- `clear_height_limits`: Clears all height limits using 0x23 command
- `set_light_color`: Sets LED strip color (1-7)
- `set_sensitivity`: Sets collision detection sensitivity (1-3)

### Connection Management

- Handshake command sent after connection to enable movement controls
- Automatic reconnection every 30 seconds when disconnected
- Connection state tracked in coordinator data
- All entities become unavailable when disconnected
- BLE device discovery uses Home Assistant's bluetooth component

## Important Technical Notes

1. **Height Range**: Hardcoded 60-130cm range based on typical Desky desk limits
2. **Update Strategy**: Passive updates via BLE notifications, with periodic status requests
3. **Error Handling**: Connection errors trigger reconnection; command errors are logged but don't crash
4. **Bluetooth Proxies**: Fully supported through Home Assistant's bluetooth component
5. **Multi-desk Support**: Each desk gets its own coordinator instance
6. **Movement Tracking**: Direction tracking prevents cover UI issues; auto-stop detection when desk reaches target
7. **Manual Controls**: Move Up/Down buttons bypass any cover entity restrictions
8. **Feature Detection**: Device capabilities are queried on connection; not all desks support all features