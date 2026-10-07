# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

**IMPORTANT**: All Python commands run inside an activated virtual environment. The latest
stable Home Assistant needs Python 3.14; the minimum supported release (2025.10) needs 3.13.

### Virtual Environment Setup
```bash
python3.14 -m venv .venv
source .venv/bin/activate               # Windows: .venv\Scripts\activate
pip install -r requirements_test.txt    # or requirements_test_min.txt on Python 3.13
pip install -r <(python script/ha_test_requirements.py)  # HA bluetooth stack pins
pre-commit install
```

`script/ha_test_requirements.py` prints the requirements of the HA components this
integration loads, pinned to whatever Home Assistant version is installed.

### Lint, Type-check and Test
```bash
pre-commit run --all-files   # everything below plus file hygiene checks
ruff check .                 # lint (add --fix to autofix)
ruff format .                # format
mypy                         # type-check custom_components/desky_desk
pytest --cov                 # tests with coverage
```

CI runs the same checks: `lint.yml` (ruff, mypy), `test.yml` (pytest against HA 2025.10 and
latest stable, plus a non-blocking beta job) and `validate.yml` (hassfest, HACS).

### Running in Home Assistant
1. Copy or symlink `custom_components/desky_desk` into your Home Assistant config directory
2. Enable debug logging in `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.desky_desk: debug
```

### Pull Requests and Releases
PR titles must follow Conventional Commits (`feat:`, `fix:`, `docs:`, `ci:` ...). PRs are
squash-merged, so the title becomes the commit on `main`. release-please turns those commits
into a release PR that bumps `manifest.json` and updates `CHANGELOG.md`; merging it publishes
the GitHub release HACS installs from. See `CONTRIBUTING.md`.

## Codebase Architecture

### Integration Structure
This is a Home Assistant custom integration that follows the standard component structure:

- **Entry Point** (`__init__.py`): Sets up the integration, defines platforms (cover, number, button, binary_sensor, light, switch, select, sensor), and manages config entry lifecycle
- **Data Coordinator** (`coordinator.py`): Implements `DataUpdateCoordinator` pattern for centralized data updates and connection management
- **Posture** (`posture.py`): `PostureTracker` follows sitting/standing from the height the desk settles at
- **Bluetooth Layer** (`bluetooth.py`): Handles BLE communication using `bleak` library with retry logic via `bleak-retry-connector`
- **Config Flow** (`config_flow.py`): Manages integration setup through UI, including Bluetooth device discovery
- **Platform Entities**: Each platform file (cover.py, number.py, etc.) implements specific Home Assistant entities

### Key Design Patterns

1. **Coordinator Pattern**: All entities receive updates through a central `DeskUpdateCoordinator` that manages:
   - Bluetooth connection state
   - Periodic status polling (30-second intervals)
   - Reconnection when the desk advertises again, with backoff (see Connection Management)
   - Data distribution to all entities
   - Movement tracking for the cover state and collision detection (see Movement Tracking below)

2. **Bluetooth Communication**:
   - Uses characteristic UUIDs for write (0xfe61) and notify (0xfe62)
   - Commands are typically 6-8 byte arrays with checksum
   - Handshake command (0xFE) must be sent after connection to enable movement
   - Height notifications can have different headers depending on firmware version
   - Height frames carry tenths of the desk's display unit (cm or inches); `_decode_height()` converts them to cm, so everything downstream works in cm (see BLE Notification Formats)

3. **Entity Implementation**:
   - Cover entity: Main control interface (0-100% position mapping) with proper direction tracking
   - Number entities: Direct height control (60-130cm range), height limits, vibration intensity
   - Button entities: Four preset positions + manual Move Up/Down controls
   - Binary sensor: Collision detection
   - Light entity: LED strip control with color, brightness, and effects
   - Switch entities: Vibration on/off, desk lock
   - Select entities: Collision sensitivity, touch mode, unit preference
   - Sensor entities: Height display with units, light color name, sensitivity level, posture, standing/sitting time today

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

### BLE Device Information Service (0x180A)

The integration automatically reads device information from the standard BLE Device Information Service during connection:

```python
# Service UUID
DEVICE_INFORMATION_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"

# Characteristic UUIDs  
MANUFACTURER_NAME_CHAR_UUID = "00002a29-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER_CHAR_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
SERIAL_NUMBER_CHAR_UUID = "00002a25-0000-1000-8000-00805f9b34fb"
HARDWARE_REVISION_CHAR_UUID = "00002a27-0000-1000-8000-00805f9b34fb"
FIRMWARE_REVISION_CHAR_UUID = "00002a26-0000-1000-8000-00805f9b34fb"
SOFTWARE_REVISION_CHAR_UUID = "00002a28-0000-1000-8000-00805f9b34fb"
```

**Device Information Integration:**
- Automatically reads device info during initial connection
- Populates Home Assistant device registry with manufacturer, model, serial number, hardware/firmware/software versions
- Falls back to "Desky" and "Standing Desk" if device info service is unavailable
- Device information is preserved during disconnections and displayed in HA device info panel
- Visible in Home Assistant under Settings > Devices & Services > [Device Name] > Device Info

### BLE Notification Formats

The desk can send height updates in two different formats depending on firmware version:

1. **Movement Notification** (0x98 0x98):
   - Header: `0x98 0x98` (bytes 0-1)
   - Height data: bytes 4-5 (little-endian)
   - Typically sent during desk movement
   - Example: `98 98 00 00 52 03` = 85.0 cm (0x0352 = 850 / 10.0)
   - Value: `(byte4 | (byte5 << 8)) / 10.0`, in the display unit
   - Not seen from the L-BTMEB95 desk (firmware Rev01), which reports movement in status frames

2. **Status Response Notification** (0xF2 0xF2 0x01 0x03):
   - Header: `0xF2 0xF2 0x01 0x03` (bytes 0-3)
   - Height data: bytes 4-5 (big-endian)
   - Sent in response to GET_STATUS command
   - Example: `F2 F2 01 03 02 D0` = 72.0 cm (0x02D0 = 720 / 10.0)
   - Value: `((byte4 << 8) | byte5) / 10.0`, in the display unit
   - Sent during movement too, about every 200 ms

Note: The two formats use different byte orders for height data - movement notifications use little-endian while status notifications use big-endian.

**Display units.** Both formats carry tenths of the desk's display unit. While the desk shows inches, `f2 f2 01 03 01 12 …` is 27.4 in, which is 69.6 cm, not 27.4 cm. `_decode_height()` reads a frame in the unit the desk reported (`0x0E` response), converting inches with 2.54 and rounding to 0.1 cm. The desk's physical range (60-130 cm, about 23.6-51.2 in) does not overlap between units, so a value impossible in the reported unit but plausible in the other is read in the other unit (a frame in the new unit arrives before the unit report when the unit changes on the hand controller), and before the desk has reported a unit a value below 55.0 is inches. Height limit responses (`0x21`/`0x22`) are decoded the same way, and the limit setters send display units. The move-to-height target (`0x1B`) is always in mm, whatever the display unit.

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

5. **Display Unit Response** (0xF2 0xF2 0x0E 0x01):
   - Values: 0=cm (`f2 f2 0e 01 00 0f 7e`), 1=inches (`f2 f2 0e 01 01 10 7e`)

6. **Touch Mode Response** (0xF2 0xF2 0x19 0x01):
   - Values: 0=One press (`f2 f2 19 01 00 1a 7e`), 1=Press and hold (`f2 f2 19 01 01 1b 7e`)

   The desk has no query for a single setting. It sends a settings block (presets `0x25`-`0x28`, unit `0x0E`, touch mode `0x19`, `0x17`, sensitivity `0x1D`) for a status request (`0x07`) that follows a handshake, which the integration sends on connect and after changing the unit or touch mode (`get_settings()`). It also sends the block unprompted when the unit is changed on the hand controller. It does not confirm a unit or touch-mode change by itself.

7. **Height Limit Responses**:
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
3. Look for either "Height notification (0x98 0x98):" or "Status notification (0xF2 0xF2 0x01 0x03):"; both log the decoded height in cm
4. Look for "Display unit response:" (cm or in) after connecting. If heights look 2.54 times off, check that line and the raw frame next to it
5. Verify which format your desk uses
6. Report the notification format in issues for debugging

### Actions (`services.py`)

Three actions, registered in `async_setup` so they exist whether or not a desk is loaded:
- `move_to_height`: moves to a height in cm (`0x1B`). The height must be within the desk's limits when set, otherwise 60-130 cm
- `set_height_limit`: sets the `upper` or `lower` limit (`0x21`/`0x22`), then re-reads the limits (`0x0C`). The upper limit must be above the lower one
- `clear_height_limits`: clears both limits (`0x23`), then re-reads them

They are plain actions with a `target:` limited to the desk cover, not entity actions: Home Assistant skips unavailable entities in entity actions, so a disconnected desk would do nothing silently. The handler resolves the target to config entries and raises a translated `ServiceValidationError` (no desk targeted, entry not loaded, bad height) or `HomeAssistantError` (not connected, write failed). Validation runs for every targeted desk before any command is sent.

The limit status (`0x20`: `0x00` none, `0x01` upper, `0x10` lower, `0x11` both) is tracked per limit; a limit that is not set reads as `None`, so its number entity shows unknown.

### Connection Management

- Handshake command sent after connection to enable movement controls, and again before every command that moves the desk or changes a setting: the controller ignores commands while its display is asleep (about a minute after the last touch), and the handshake wakes it. `stop()` is sent without it
- Connections go through `establish_connection(BleakClientWithServiceCache, ...)`, which picks whichever adapter or proxy hears the desk; there is no proxy detection of our own
- While the entry is loaded the coordinator expects a connection. An advertisement callback for the desk's address hands the fresh `BLEDevice` to `DeskBLEDevice.set_ble_device()` and reconnects a disconnected desk at once. A failed attempt retries after 5 s, doubling to 120 s and reset on success; advertisements wait out a pending retry. A retry is skipped while HA no longer sees the desk
- `async_track_unavailable` fires when HA stops seeing the desk. A desk that is still connected is asked for its status first and dropped only if the write fails, since a connected desk may stop advertising
- A disconnect logs one warning and the recovery one info line (`The desk at <address> is unavailable` / `is available again`); everything in between is debug
- Commands raise `DeskNotConnectedError` or `DeskCommandError` (the bool returns are gone; bad arguments raise `ValueError`). Writes are serialised with an `asyncio.Lock`, and a woken command writes its handshake under the same lock. Entity command methods use `@desk_command` (`entity.py`), which turns those into translated `HomeAssistantError`s
- A poll on a disconnected desk sends nothing and is not an update failure; a poll whose status write fails drops the connection
- A desk connected within about a second of powering up ignores the settings request sent while connecting, and instead sends `f2 f2 10 02 02 51` and `f2 f2 0f 02 00 07` (meaning unknown). So the first scheduled poll after each connection asks for the settings again (`get_settings()`) if the unit or touch mode is still unknown. It asks only once per connection, because the handshake wakes the desk's display
- Connection state tracked in coordinator data
- All entities become unavailable when disconnected
- BLE device discovery uses Home Assistant's bluetooth component

### Posture Tracking

- `PostureTracker` (`posture.py`), owned by the coordinator, sets `DeskData.posture` (a `Posture` enum: `sitting`/`standing`) once the height has been unchanged for `POSTURE_SETTLE_SECONDS` (2 s) and no commanded move is in flight, so passing the threshold mid-move changes nothing. A height at or above the standing threshold (option `standing_threshold`, default 95 cm, 60-130 cm) is standing
- The posture is `None` while disconnected or before the first height. `posture_changed_at` is a `time.monotonic()` stamp: a change between postures dates from when the desk stopped, a posture that becomes known dates from that moment
- A posture change is published without `async_set_updated_data()`, which would push back the 30-second poll
- `PostureTimeSensor` (standing/sitting time today) counts minutes from those stamps on every coordinator update and a 1-minute tick. `state_class: total` with `last_reset` at local midnight; every update compares the local date too, so a day whose midnight a clock change skips still resets. It restores its value only if the restored `last_reset` is today
- The options flow is an `OptionsFlowWithReload`; saving reloads the entry, and the totals survive the reload through restore

## Important Technical Notes

1. **Height Range**: Hardcoded 60-130cm range based on typical Desky desk limits
2. **Update Strategy**: Passive updates via BLE notifications, with periodic status requests
3. **Error Handling**: Connection errors trigger reconnection; entity commands raise translated errors instead of failing silently
4. **Bluetooth Proxies**: Fully supported through Home Assistant's bluetooth component
5. **Multi-desk Support**: Each desk gets its own coordinator instance
6. **Movement Tracking** (`bluetooth.py`, one `_Movement` object, `None` when nothing is in flight):
   - A movement exists only after a command (Move up/down, preset, move to height). It starts once the height has moved from the height at command time by more than `HEIGHT_JITTER_CM` (0.5 cm) in the commanded direction (either direction for presets). Height changes with no command in flight, including hand-controller moves, update the height but never start a movement.
   - A command that has not moved the desk within `COMMAND_EXPIRY_SECONDS` (5 s) is dropped, checked on the next reading.
   - A movement ends, and all its state is forgotten through `_end_movement()`, on auto-stop (three readings without a change), `stop()`, a bounce-back, a new command or a disconnect.
   - A bounce-back is a reversal of more than `HEIGHT_JITTER_CM` from the furthest point reached in the commanded direction; it is reported as one collision and ends the movement. Presets have no direction, so they get no bounce check.
   - Auto-stop judges a collision from the active part of the movement (first to last height change), not from when the stop is confirmed.
   - Both height frame types feed the same `_process_height()`, so movement behaviour does not depend on the frame type.
7. **Manual Controls**: Move Up/Down buttons bypass any cover entity restrictions
8. **Feature Detection**: Device capabilities are queried on connection; not all desks support all features
