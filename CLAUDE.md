# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Testing the Integration
```bash
# Run Home Assistant in development mode with this integration
hass -c config --debug

# Validate HACS compatibility
hacs validate

# Check integration structure
python -m pytest tests/
```

### Development Setup
1. Clone this repository into `custom_components/desky_desk` in your Home Assistant config directory
2. Enable debug logging by adding to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.desky_desk: debug
```

## Codebase Architecture

### Integration Structure
This is a Home Assistant custom integration that follows the standard component structure:

- **Entry Point** (`__init__.py`): Sets up the integration, defines platforms (cover, number, button, binary_sensor), and manages config entry lifecycle
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

2. **Bluetooth Communication**:
   - Uses characteristic UUIDs for write (0xfe61) and notify (0xfe62)
   - Commands are typically 6-8 byte arrays with checksum
   - Handshake command (0xFE) must be sent after connection to enable movement
   - Height notifications can have different headers depending on firmware version
   - Height calculation: `(byte4 | (byte5 << 8)) / 10.0` cm

3. **Entity Implementation**:
   - Cover entity: Main control interface (0-100% position mapping)
   - Number entity: Direct height control (60-130cm range)
   - Button entities: Four preset positions
   - Binary sensor: Collision detection

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

# Move to specific height command structure:
# bytes([0xF1, 0xF1, 0x1B, 0x02, height_high_byte, height_low_byte, checksum, 0x7E])
# where height is in mm (e.g., 850mm = 0x0352, so high=0x03, low=0x52)
# checksum = (0x1B + 0x02 + height_high + height_low) & 0xFF
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

The integration provides three custom services:
- `move_to_height`: Sends direct height command to desk using the 0x1B command
- `move_to_preset`: Sends preset command via Bluetooth
- `set_position_limit`: Would require desk firmware support (placeholder)

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