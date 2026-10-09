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
- **Sequencer** (`sequencer.py`): writes frames one at a time and sends timed sequences (see Command Timing); `limits.py` holds the known height limits, `errors.py` the command errors
- **Config Flow** (`config_flow.py`): Manages integration setup through UI, including Bluetooth device discovery (`title_placeholders` names the desk on the discovery card). The picker hides desks already configured, a typed address must be a MAC address (`invalid_address`), and the user steps set the unique ID with `raise_on_progress=False` so an open discovery card does not block them. Every path probes the desk with a real `connect()` and always disconnects it afterwards
- **Platform Entities**: Each platform file (cover.py, number.py, etc.) implements specific Home Assistant entities

### Key Design Patterns

1. **Coordinator Pattern**: All entities receive updates through a central `DeskUpdateCoordinator` that manages:
   - Bluetooth connection state
   - Status polling 30 seconds after the last update: every `async_set_updated_data()` restarts the timer, so a quiet desk is polled about every 30 seconds. The poll writes nothing while a movement frame is being repeated
   - Reconnection when the desk advertises again, with backoff (see Connection Management)
   - Data distribution to all entities
   - Movement tracking for the cover state and collision detection (see Movement Tracking below)

2. **Bluetooth Communication**:
   - Uses characteristic UUIDs for write (0xfe61) and notify (0xfe62)
   - Commands are typically 6-8 byte arrays with checksum
   - Handshake command (0xFE) must be sent after connection to enable movement. This was observed on the L-BTMEB95; for the commands the official app sends without a handshake, see Command Timing
   - Height notifications can have different headers depending on firmware version
   - Height frames carry tenths of the desk's display unit (cm or inches); `_decode_height()` converts them to cm, so everything downstream works in cm (see BLE Notification Formats)
   - `_handle_notification()` notifies the entities after every recognised frame; an unrecognised or truncated frame notifies nothing. `set_lock_status()` also notifies after a successful write, because it shows the lock before the reply

3. **Entity Implementation**:
   - Cover entity: Main control interface (0-100% position mapping) with proper direction tracking
   - Number entities: Direct height control (60-130cm range), height limits. There is no vibration intensity entity: the desk never answers the `A4` query, and the official app neither sends it nor sets it
   - Button entities: Four preset positions + manual Move Up/Down controls
   - Binary sensor: Collision detection
   - Light entity: LED strip control with brightness, effects and a colour wheel (`ColorMode.HS`; `color_mode` is always `hs`). `hs_color` reports the desk colour (White 0/0, Red 0, Yellow 60, Green 120, Blue 240, saturation 100) and `None` in Party mode; a requested colour snaps with `_nearest_color()` (saturation below 30 is White, otherwise the nearest hue, a tie going to the colour below). `ColorMode.COLOR_TEMP` is supported only so HA passes a colour temperature on instead of converting it to a hue (2700 K would snap to red); any kelvin sets White. An effect wins over a colour
   - Switch entities: Vibration on/off, desk lock
   - Select entities: Collision sensitivity (`high`/`medium`/`low`), touch mode (`one_press`/`press_and_hold`), display unit (`cm`/`in`); states are keys with translated labels
   - Sensor entities: Height display (cm, device class distance), posture, standing/sitting time today
   - No entity has extra state attributes; diagnostics carry the full desk data

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
   - Not seen from the L-BTMEB95 desk (firmware Rev01), which reports movement in status frames. Which controllers send it is unverified, and the official app does not read it

2. **Status Response Notification** (0xF2 0xF2 0x01 0x03):
   - Header: `0xF2 0xF2 0x01 0x03` (bytes 0-3)
   - Height data: bytes 4-5 (big-endian)
   - Sent in response to GET_STATUS command
   - Example: `F2 F2 01 03 02 D0` = 72.0 cm (0x02D0 = 720 / 10.0)
   - Value: `((byte4 << 8) | byte5) / 10.0`, in the display unit
   - Sent during movement too, about every 200 ms

Note: The two formats use different byte orders for height data - movement notifications use little-endian while status notifications use big-endian.

**Display units.** Both formats carry tenths of the desk's display unit. While the desk shows inches, `f2 f2 01 03 01 12 …` is 27.4 in, which is 69.6 cm, not 27.4 cm. `_decode_height()` reads a frame in the unit the desk reported (`0x0E` response), converting inches with 2.54 and rounding to 0.1 cm. The desk's physical range (60-130 cm, about 23.6-51.2 in) does not overlap between units, so a value impossible in the reported unit but plausible in the other is read in the other unit (a frame in the new unit arrives before the unit report when the unit changes on the hand controller), and before the desk has reported a unit a value below 55.0 is inches. Height limit responses (`0x21`/`0x22`) are decoded the same way after `_decode_limit()` adds one tenth to a raw value that is not a multiple of 5 (the desk reports 124.0 cm as 1239; the official app does the same), and the limit setters send display units. Height frames are never corrected. The move-to-height target (`0x1B`) is always in mm, whatever the display unit.

### Advanced Feature Response Formats

Additional device features send responses with specific headers:

1. **Light Color Response** (0xF2 0xF2 0xB4 0x01):
   - Values: 1=White, 2=Red, 3=Green, 4=Blue, 5=Yellow, 6=Party mode, 7=Off
   - 0 also means off: the official app turns the LED off by setting colour 0. `OFF_COLORS` (`const.py`) holds both, and `LED_COLORS` (`light.py`) holds only the colours the LED shows, each with its effect name and its hue and saturation (none for Party mode); the light is off and turning it on restores a colour. The integration never sends 0; it turns the light off with the lighting command (`B5 00`)

2. **Brightness Response** (0xF2 0xF2 0xB6 0x01):
   - Value: 0-100 (percentage). The official app offers 20-100 in steps of 20; other values work too

3. **Lock Status Response** (0xF2 0xF2 0xB2 0x01):
   - Value: 0=Unlocked, 1=Locked

4. **Sensitivity Response** (0xF2 0xF2 0x1D 0x01):
   - Values: 1=High, 2=Medium, 3=Low
   - Read from the settings block only. The integration never sends the `0x1D` query (`F1 F1 1D 00`): on a real desk its reply disagreed with the block, and the official app never sends it. A lone `0x1D` frame is still parsed

5. **Display Unit Response** (0xF2 0xF2 0x0E 0x01):
   - Values: 0=cm (`f2 f2 0e 01 00 0f 7e`), 1=inches (`f2 f2 0e 01 01 10 7e`)

6. **Touch Mode Response** (0xF2 0xF2 0x19 0x01):
   - Values: 0=One press (`f2 f2 19 01 00 1a 7e`), 1=Press and hold (`f2 f2 19 01 01 1b 7e`)

   The desk has no query for a single setting. It sends a settings block (presets `0x25`-`0x28`, unit `0x0E`, touch mode `0x19`, `0x17`, sensitivity `0x1D`) for a status request (`0x07`) that follows a handshake, which the integration sends on connect and at the end of the unit, touch-mode and sensitivity setters (`SETTINGS_REQUEST`, also `get_settings()`). It also sends the block unprompted when the unit is changed on the hand controller. It does not confirm a unit, touch-mode or sensitivity change by itself. The preset heights (`0x25`-`0x28`) in the block are in the display unit; the integration does not read them.

7. **Height Limit Responses**:
   - Upper limit (0xF2 0xF2 0x21 0x02): tenths of the display unit (big-endian), one tenth low; a raw value not divisible by 5 is rounded up by one tenth before decoding
   - Lower limit (0xF2 0xF2 0x22 0x02): tenths of the display unit (big-endian), same correction
   - Limit status (0xF2 0xF2 0x20 0x01): 0x00=No limits, 0x01=Upper only, 0x10=Lower only, 0x11=Both
   - With no limits set, the desk was seen to answer `0x0C` with `f2 f2 07 04 04 e2 02 58` (125.0 and 60.0 cm). It may be this desk's travel range; the integration doesn't read it and keeps its fixed 60-130 cm range

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
- `move_to_height`: moves to a height in cm (`0x1B`). The height must be within the desk's limits when set, clamped to 60-130 cm, otherwise 60-130 cm (`validate_move_to_height` in `validation.py`)
- `set_height_limit`: sets the `upper` or `lower` limit (`0x21`/`0x22`); the limit sequence ends by re-reading the limits (`0x0C`). The limit must be within `DeskBLEDevice.limit_range` (`LIMIT_RANGE_CM`): 60-124 cm, or 24-48 in (61.0-121.9 cm) when limits are sent in inches, the unit the heights arrive in. The desk silently ignores a limit outside that range. The desk stores whole units (110.2 cm reads back as 110.0), so `round_limit()` rounds a limit half up to a whole cm, or a whole inch in that unit, and the rounded value is what is checked and sent (`checked_height_limit()` in `validation.py`, used by the action and the limit number entities). The upper limit must be above the lower one. The desk only tightens a limit that is set, so the limit is sent after clearing both and with the other limit again (see Command Timing). Home Assistant checks the limit entities' min/max before our rounding, so on an inch desk the entities refuse slightly more than the action does: 122.0 cm rounds to 48 in, which the action accepts, but it is above the entities' 121.9 cm max
- `clear_height_limits`: clears both limits (`0x23`); the sequence ends by re-reading them

They are plain actions with a `target:` limited to the desk cover, not entity actions: Home Assistant skips unavailable entities in entity actions, so a disconnected desk would do nothing silently. The handler resolves the target to config entries and raises a translated `ServiceValidationError` (no desk targeted, entry not loaded, bad height) or `HomeAssistantError` (not connected, write failed). Validation runs for every targeted desk before any command is sent.

The limit status (`0x20`: `0x00` none, `0x01` upper, `0x10` lower, `0x11` both) is tracked per limit in `HeightLimits`; a limit that is not set reads as `None`, so its number entity shows unknown.

### Connection Management

- Handshake command sent after connection to enable movement controls, and again before every command that moves the desk or changes a setting: the controller ignores commands while its display is asleep (about a minute after the last touch), and the handshake wakes it. `stop()` is sent without it; see Command Timing for the spacing
- Connections go through `establish_connection(BleakClientWithServiceCache, ...)`, which picks whichever adapter or proxy hears the desk; there is no proxy detection of our own
- A connection attempt that fails after the link is up (notifications, handshake, status or capability queries) closes that link before `connect()` returns False, so it does not keep an adapter or proxy slot. The failure is reported as one disconnect. A disconnect callback from a client that is no longer `_client` is ignored, so an old link cannot drop a newer connection
- A connection the desk stops answering on (a failed poll or status check) is dropped with `drop_connection()`: it reports the disconnect first, so the entities go unavailable and commands fail as not connected at once, then closes the link within `CLOSE_TIMEOUT_SECONDS` (5 s). Through a proxy the close can hang for 20 s. The close runs as its own task, so cancelling the caller (unload cancels the coordinator's background tasks) does not abandon it; a reconnect and `disconnect()` wait for it. A failed setup keeps the opposite order (close, then report), so a cancel during the close leaves the link for `disconnect()`
- Connecting sends the handshake and status together, then the capability queries 0.2 s apart (see Command Timing). A query write that fails fails the connect; a desk without a feature just does not answer
- While the entry is loaded the coordinator expects a connection. An advertisement callback for the desk's address hands the fresh `BLEDevice` to `DeskBLEDevice.set_ble_device()` and reconnects a disconnected desk at once. A failed attempt retries after 5 s, doubling to 120 s and reset on success; advertisements wait out a pending retry. A retry is skipped while HA no longer sees the desk
- `async_track_unavailable` fires when HA stops seeing the desk. A desk that is still connected is asked for its status first and dropped only if the write fails, since a connected desk may stop advertising
- A disconnect logs one info line and the recovery another (`The desk at <address> is unavailable` / `is available again`); everything in between is debug. Home Assistant hides info lines unless the log level is info or lower
- Commands raise `DeskNotConnectedError` or `DeskCommandError` (the bool returns are gone; bad arguments raise `ValueError`). Writes are serialised with an `asyncio.Lock`, and a woken command writes its handshake under the same lock. Entity command methods use `@desk_command` (`entity.py`), which turns those into translated `HomeAssistantError`s
- A poll on a disconnected desk sends nothing and is not an update failure; a poll whose status write fails drops the connection
- A desk connected within about a second of powering up ignores the settings request sent while connecting, and instead sends `f2 f2 10 02 02 51` and `f2 f2 0f 02 00 07` (meaning unknown). So the first scheduled poll after each connection asks for the settings again (`get_settings()`) if the unit, touch mode or sensitivity is still unknown. It asks only once per connection, because the handshake wakes the desk's display
- Connection state tracked in coordinator data
- All entities become unavailable when disconnected. A disconnect forgets the unit, touch mode, sensitivity and height limits, which can change on the hand controller meanwhile; they show unknown until the desk reports them again
- BLE device discovery uses Home Assistant's bluetooth component

### Command Timing

Commands go out with the official Desky app's repeats and spacing, read from the decompiled Android app 4.5.4 (see `docs/protocol.md`):
- `Sequencer` (`sequencer.py`) owns the write lock, the running sequences, the motion slot and the clock. `DeskBLEDevice` gives it `_write_frame()` (one GATT write, raising `DeskNotConnectedError`/`DeskCommandError` from `errors.py`) and uses its named entry points: `write(*frames)` for immediate writes, `run_setting(steps)`, `run_motion(steps)` and `start_repeat(steps)` (the background hold-repeat). `_write_frame(frame, response)` always passes `response=` to bleak explicitly; only `start_repeat` writes without response
- A sequence is `(time, frame)` steps, with times in seconds from its start. Pauses are awaited without the write lock, so a stop is never held up. Frames due at the same time go out in one `write()`, so a handshake stays with its command. A late step, after a slow write, moves the rest back instead of sending a burst (through a proxy each write with response takes about 70-130 ms, so 50 ms spacing comes out nearer 90 ms)
- A radio write is never interrupted. A cancel during one waits for it to finish before the write lock is released, because BlueZ rejects the next write (InProgress) while one is still running; a cancelled write still running after `WRITE_SETTLE_SECONDS` (2 s, timed on the sequencer's clock) has hung and is given up. Every write also has a bound: `_write_frame()` raises `DeskCommandError` for a write the desk has not confirmed within `WRITE_TIMEOUT_SECONDS` (5 s, real time, since the test clock passes pauses at once), so a stop never waits behind a hung write for longer. A movement command whose write fails after a stop has taken over leaves the movement alone, so it cannot cancel that stop
- Movement and stop sequences share one motion slot: a new one, `cancel_motion()` (from `_begin_movement()` and `_end_movement()`) or a disconnect (`cancel_all()`) cancels the one there. Each cancel records its reason: a superseded caller returns quietly, a disconnected one gets `DeskNotConnectedError`. A stop does not cancel a setting in progress
- Lock, vibration, lighting: handshake, set at 0.2 and 0.4 s. Sensitivity, touch mode: handshake, set at 0.5 s. Colour, brightness: handshake, set at 0 and 0.1 s. Unit: handshake, set at 0, 0.1 and 0.2 s. Clear limits: handshake, clear at 0 and 0.2 s. Stop: at 0 and 0.05 s, no handshake. Move to height: handshake and stop, then `1B` at 0.2 and 0.3 s (in press-and-hold mode then repeated, see Hold-repeat). Connect: `SETTINGS_REQUEST` (handshake and status), then each query 0.2 s apart
- The unit, touch-mode and sensitivity setters end their own sequence with `SETTINGS_REQUEST`, `READ_BACK_DELAY` (0.5 s) after the last set, as the app does for sensitivity. The select does not ask again. A sequence cut short by a failed write is not read back
- Touch mode and unit are checked (`_send_checked_setting()`): the set sequence goes out, then after `READ_BACK_DELAY` the report waiter is registered and only then the settings request is written, so an older report (another read-back, the first poll's re-ask, a hand-controller change) cannot answer it. The desk can ignore a set (measured: a preset then ran the whole way from one frame, as in one-press mode). If the settings block reports the old value, the setting is sent once more; still old, it raises `DeskSettingNotAppliedError`, which `translate_desk_errors()` turns into the translated `setting_not_applied` error. A desk that sends no report within `READ_BACK_TIMEOUT_SECONDS` is not checked. `_expect_report(header)` returns a future the next frame with that header completes, and `Sequencer.wait_for()` waits on the sequencer's clock
- Set a limit: handshake, clear ×2, upper ×2, lower ×2, 0.05 s apart, sending the other limit again. This is needed for correctness, not only timing: while a limit is set the desk only accepts a tighter one and silently ignores a looser one (measured: upper 110 set, 124 ignored, 105 applied). Limits are one `HeightLimits` value (`limits.py`); no clear is sent unless `fully_known` (the desk has reported which limits are set and the value of each set one), so no limit is wiped, and the new limit then goes out alone, twice. The other limit is re-sent as the raw tenths the desk reported, or converted from cm after a unit change. Each limit sequence, and a clear, ends with the `0x0C` limit query, inside the limit-only lock, so the reply usually arrives before the next change starts, though nothing guarantees it (callers no longer ask separately). Once the sequence succeeds, the limits sent become the known limits (a clear marks both not set) and entities are notified; the reply corrects anything the desk did differently. A reply from one change arriving during the next is overwritten when that change succeeds. The lock keeps limit changes from interleaving; stop never takes it. A disconnect forgets the limits (`HeightLimits()`), so a reconnect clears nothing until the desk reports them again
- The app sends movement commands (move up and down, presets, move to height), colour, brightness, unit and limits without a handshake. The integration keeps it, because the desk ignores commands while its display sleeps
- **Hold-repeat:** move up/down and cover open/close repeat their frame every 0.1 s in every touch mode, as the app's arrows (one frame only nudges about 0.8 cm). In press-and-hold touch mode (`TOUCH_MODE_PRESS_AND_HOLD`) presets repeat too, and move to height repeats `1B` after its two target frames until `_reached()` (within `HEIGHT_JITTER_CM` of the target, or past it). One-press or unknown touch mode sends one preset frame (it runs the whole way) and move to height as the app does. The repeat is capped at 60 s and ends with the movement, because `_end_movement()` cancels it (stop, auto-stop after three unchanged readings, bounce-back, expiry, a new command, a disconnect), and by itself once `COMMAND_EXPIRY_SECONDS` pass without the desk starting to move, even with no height reading. A started, held movement also ends once no height reading has come for `READING_WATCHDOG_SECONDS` (3 s; a moving desk reports about every 200 ms, but through a proxy the reports bunch, with gaps over 1 s), since bounce and collision detection are blind without readings. `_readings_stopped()` only answers the question; `_hold()` puts a done callback on the repeat (`_hold_ended()`) that ends the movement and notifies once the repeat has stopped for that reason. A move to height first asks for the status if the desk has not reported a height (still 0.0), and fails rather than moving blind if no reading comes. A stop or newer movement command during that wait wins: `_motion_commands` counts them, and the move to height gives up if it changed
- **Repeats go out without response** (`start_repeat`), evenly every 0.1 s. Measured: with-response writes take 70-700 ms through a proxy, the uneven stream made the desk treat a held preset as released, and without-response repeats took it smoothly 75 → 95 cm. `0xfe61` advertises `write-without-response` and `write`. The first frame, Stop, settings and limits keep `response=True`, so failures are still reported. The coordinator's status poll writes nothing while `DeskBLEDevice.is_repeating`, since a with-response write would hold up the repeats
- Other read-backs (`get_lock_status()`, ...) run after the setter's sequence returns
- Tests run the timing on `FakeClock` (`tests/__init__.py`). A test's own desk takes it as `DeskBLEDevice(..., clock=clock)` or `Sequencer(write, clock)`; the autouse `clock` fixture patches `sequencer.Clock` for desks the integration builds. Set `clock.auto = False` and call `clock.advance()` to control each pause. `record_writes()` records each write's time, frame and write type. The desk fixtures tests build themselves (`desk` in `test_timing.py`, `connected_device` in `test_bluetooth.py`) cancel what the desk still sends at teardown, since Move up/down repeat until stopped. A reconnect runs as a background task and yields while its queries are spaced, so wait with `hass.async_block_till_done(wait_background_tasks=True)`

### Posture Tracking

- `PostureTracker` (`posture.py`), owned by the coordinator, sets `DeskData.posture` (a `Posture` enum: `sitting`/`standing`) once the height has been unchanged for `POSTURE_SETTLE_SECONDS` (2 s) and no commanded move is in flight, so passing the threshold mid-move changes nothing. A height at or above the standing threshold (option `standing_threshold`, default 95 cm, 60-130 cm) is standing
- The posture is `None` while disconnected or before the first height. `posture_changed_at` is a `time.monotonic()` stamp: a change between postures dates from when the desk stopped, a posture that becomes known dates from that moment
- A posture change is published without `async_set_updated_data()`, which would push back the 30-second poll
- `PostureTimeSensor` (standing/sitting time today) counts minutes from those stamps on every coordinator update and a 1-minute tick. `state_class: total` with `last_reset` at local midnight; every update compares the local date too, so a day whose midnight a clock change skips still resets. It restores its value only if the restored `last_reset` is today
- The options flow is an `OptionsFlowWithReload`; saving reloads the entry, and the totals survive the reload through restore

## Important Technical Notes

1. **Height Range**: Hardcoded 60-130cm range for heights and moves, based on typical Desky desk limits. Height limits are 60-124 cm (24-48 in), the range the desk accepts
2. **Update Strategy**: Passive updates via BLE notifications, with periodic status requests
3. **Error Handling**: Connection errors trigger reconnection; entity commands raise translated errors instead of failing silently
4. **Bluetooth Proxies**: Fully supported through Home Assistant's bluetooth component
5. **Multi-desk Support**: Each desk gets its own coordinator instance
6. **Movement Tracking** (`bluetooth.py`, one `_Movement` object, `None` when nothing is in flight):
   - A movement exists only after a command (Move up/down, preset, move to height). It starts once the height has moved from the height at command time by more than `HEIGHT_JITTER_CM` (0.5 cm) in the commanded direction (either direction for presets). Height changes with no command in flight, including hand-controller moves, update the height but never start a movement.
   - A command that has not moved the desk within `COMMAND_EXPIRY_SECONDS` (5 s) is dropped, checked on the next reading.
   - A movement ends, and all its state is forgotten and any frames still due for it are cancelled, through `_end_movement()`, on auto-stop (three readings without a change), `stop()`, a bounce-back, a new command or a disconnect.
   - A bounce-back is a reversal of more than `HEIGHT_JITTER_CM` from the furthest point reached in the commanded direction; it is reported as one collision and ends the movement. Presets have no direction, so they get no bounce check.
   - Collisions, bounce-backs and their clearing log at debug. The collision binary sensor shows them.
   - Auto-stop judges a collision from the active part of the movement (first to last height change), not from when the stop is confirmed.
   - Both height frame types feed the same `_process_height()`, so movement behaviour does not depend on the frame type.
7. **Manual Controls**: Move Up/Down buttons bypass any cover entity restrictions
8. **Feature Detection**: Device capabilities are queried on connection. A desk without a feature does not answer its query, so that value stays unknown
