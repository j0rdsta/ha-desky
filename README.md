# Desky Standing Desk Integration for Home Assistant

[![Test](https://github.com/j0rdsta/ha-desky/actions/workflows/test.yml/badge.svg)](https://github.com/j0rdsta/ha-desky/actions/workflows/test.yml)
[![Lint](https://github.com/j0rdsta/ha-desky/actions/workflows/lint.yml/badge.svg)](https://github.com/j0rdsta/ha-desky/actions/workflows/lint.yml)
[![Validate](https://github.com/j0rdsta/ha-desky/actions/workflows/validate.yml/badge.svg)](https://github.com/j0rdsta/ha-desky/actions/workflows/validate.yml)
[![codecov](https://codecov.io/gh/j0rdsta/ha-desky/graph/badge.svg)](https://codecov.io/gh/j0rdsta/ha-desky)
[![GitHub release](https://img.shields.io/github/v/release/j0rdsta/ha-desky)](https://github.com/j0rdsta/ha-desky/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Control your Desky standing desk via Bluetooth Low Energy (BLE) in Home Assistant. This integration supports ESPHome Bluetooth proxies and works with all Home Assistant installation types.

[Desky](https://www.desky.com.au) makes electric sit-stand desks. Desks with a Bluetooth control box are normally driven from the hand controller or the Desky app. This integration talks to the same control box directly, so Home Assistant can read the desk's height and settings, move it to a height or preset, and control its light, vibration and lock.

## Features

### Core Features
- **Movement Control**: Raise, lower, and stop desk movement
- **Height Sensor**: Real-time height monitoring in centimeters
- **Preset Positions**: Move to any of 4 saved preset positions
- **Collision Detection**: Binary sensor for collision events
- **Cover Entity**: Control desk as a cover (0% = minimum height, 100% = maximum height)

### Supported Entities
All entities belong to one device per desk. Their names are translated and prefixed with the
device name; the entity IDs below are for a desk named "Desky Desk". Entities created by earlier
versions keep their existing entity IDs.

| Platform | Name | Entity ID | Description |
| --- | --- | --- | --- |
| Cover | Desky Desk | `cover.desky_desk` | Main control: raise, lower, stop and move to a position (0% = 60 cm, 100% = 130 cm) |
| Number | Height | `number.desky_desk_height` | Current height in cm; set it to move the desk (60–130 cm) |
| Number | Upper height limit | `number.desky_desk_upper_height_limit` | Highest height the desk will move to |
| Number | Lower height limit | `number.desky_desk_lower_height_limit` | Lowest height the desk will move to |
| Number | Vibration intensity | `number.desky_desk_vibration_intensity` | Vibration strength (0–100%) |
| Button | Preset 1 – Preset 4 | `button.desky_desk_preset_1` … `_4` | Move to a saved preset position |
| Button | Move up / Move down | `button.desky_desk_move_up`, `button.desky_desk_move_down` | Manual movement |
| Binary sensor | Collision detected | `binary_sensor.desky_desk_collision_detected` | On when the desk detects a collision |
| Light | LED strip | `light.desky_desk_led_strip` | LED strip brightness and colour (as effects) |
| Switch | Vibration | `switch.desky_desk_vibration` | Vibration on or off |
| Switch | Lock | `switch.desky_desk_lock` | Lock the desk controls |
| Select | Collision sensitivity | `select.desky_desk_collision_sensitivity` | High, Medium or Low |
| Select | Touch mode | `select.desky_desk_touch_mode` | One press or Press and hold |
| Select | Display unit | `select.desky_desk_display_unit` | cm or in |
| Sensor | Height display | `sensor.desky_desk_height_display` | Height in the desk's display unit |
| Sensor | LED color | `sensor.desky_desk_led_color` | Current LED colour |
| Sensor | Vibration intensity display | `sensor.desky_desk_vibration_intensity_display` | Current vibration strength |
| Sensor | Posture | `sensor.desky_desk_posture` | Sitting or Standing, from the height the desk stops at (see [Options](#options)) |
| Sensor | Standing time today | `sensor.desky_desk_standing_time_today` | Minutes spent standing today |
| Sensor | Sitting time today | `sensor.desky_desk_sitting_time_today` | Minutes spent sitting today |

Not every desk supports every feature. All entities are unavailable while the desk is not
connected.

### Actions

Target the desk's cover entity, its device, or an area. An action fails with an error if the desk is
not connected, or if a height is out of range; it never does nothing silently.

| Action | Fields | What it does |
| --- | --- | --- |
| `desky_desk.move_to_height` | `height` (cm) | Moves the desk to a height. The height must be within the desk's height limits, or 60–130 cm if none are set |
| `desky_desk.set_height_limit` | `limit` (`upper` or `lower`), `height` (cm, 60–130) | Sets a height limit. The upper limit must be above the lower one |
| `desky_desk.clear_height_limits` | | Removes both height limits |

```yaml
- action: desky_desk.move_to_height
  target:
    entity_id: cover.desky_desk
  data:
    height: 100

- action: desky_desk.set_height_limit
  target:
    entity_id: cover.desky_desk
  data:
    limit: upper
    height: 120

- action: desky_desk.clear_height_limits
  target:
    entity_id: cover.desky_desk
```

To move to a saved preset, press its button entity (`button.desky_desk_preset_1` … `_4`).

## ⚠️ IMPORTANT SAFETY WARNING

**USE AT YOUR OWN RISK**: Standing desks are motorized furniture with inherent safety hazards including:
- **Crushing hazards** - Keep hands, feet, children, and pets away from moving parts
- **Collision risks** - Ensure clear space above and below desk before movement
- **Electrical hazards** - Risk of injury from unexpected movement or malfunction
- **Pinch points** - Be aware of potential pinch points in the desk mechanism

**This is an UNOFFICIAL integration** with no affiliation, endorsement, or support from Desky. The integration author(s) assume no responsibility for:
- Damage to property or equipment
- Personal injury resulting from desk operation
- Loss of desk warranty due to third-party control
- Any malfunction or unexpected behavior

Always follow manufacturer safety guidelines and maintain physical access to manual controls.

### 🚨 Automation Safety Guidelines

When creating automations for your standing desk, **ALWAYS** include safety measures:

1. **Use Presence Detection** - Never automate desk movement without confirming someone is present
   - Include presence sensor conditions in ALL desk automations
   - Consider using multiple sensors for redundancy
   - Account for pets and children who might be under the desk

2. **Implement Safety Conditions**:
   - Require presence for at least 1 minute before movement
   - Add time-of-day restrictions
   - Include manual override capabilities
   - Set maximum movement duration limits

3. **Test Thoroughly**:
   - Test automations with desk unplugged first
   - Verify all safety conditions work as expected
   - Keep manual controls easily accessible

⚠️ **WARNING**: Unattended desk movement can cause serious injury or property damage. The integration authors are not responsible for any incidents resulting from unsafe automation practices.

## Compatibility Notice

**Upsy Desky Users:** If you have an Upsy Desky device installed between your desk's control box and handset, you must disconnect it before using this Bluetooth integration. The two systems cannot work simultaneously as Upsy Desky intercepts the RJ45 connection while this integration uses Bluetooth. See [Issue #4](https://github.com/j0rdsta/ha-desky/issues/4) for details.

## Requirements

- Home Assistant 2025.10 or newer
- The Bluetooth integration set up, with a Bluetooth adapter or an ESPHome Bluetooth proxy in range of the desk
- A Desky standing desk with Bluetooth support, powered on and not connected to the Desky app (the desk accepts one connection at a time)

## Installation

### HACS (Recommended)
1. Open HACS in Home Assistant
2. Click the three dots menu and select "Custom repositories"
3. Add this repository URL: `https://github.com/j0rdsta/ha-desky`
4. Select "Integration" as the category
5. Click "Add"
6. Search for "Desky Standing Desk" and install
7. Restart Home Assistant

### Manual Installation
1. Copy the `custom_components/desky_desk` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

Home Assistant usually discovers a desk that is advertising and shows it under Settings → Devices & Services as a discovered device. Click "Add" and confirm. To add a desk yourself:

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "Desky Standing Desk"
4. Choose your desk, or enter its Bluetooth address if none was found

Setup connects to the desk once before it finishes, and shows an error if the desk does not answer.

### Setup parameters

- **Device**: shown when Home Assistant has found desks nearby. Pick your desk from the list of Bluetooth devices whose name contains "Desky".
- **Bluetooth Address**: shown when no desk was found. The desk's Bluetooth address, for example `AA:BB:CC:DD:EE:FF`. You can find it under Settings → Devices & Services → Bluetooth → Advertisement monitor, in an ESPHome Bluetooth proxy's log, or with a BLE scanner app such as nRF Connect.

### Options

Open the desk under Settings → Devices & Services → Desky Standing Desk and select **Configure**.

| Option | Default | Range | Description |
| --- | --- | --- | --- |
| Standing threshold | 95 cm | 60–130 cm | The desk counts as standing when it stops at or above this height, and as sitting when it stops below it |

Saving the options reloads the desk. Today's sitting and standing times are kept.

## Removing the integration

Removing the integration needs no steps on the desk, though you may want to clear its height limits first (see below).

1. Go to Settings → Devices & Services and select **Desky Standing Desk**
2. Open the three dots menu on the desk's entry and select **Delete**

To remove the files as well, open HACS, select **Desky Standing Desk**, choose **Remove** from the three dots menu and restart Home Assistant. For a manual installation, delete `custom_components/desky_desk` and restart.

Height limits and presets are stored on the desk's control box and stay there. Clear the limits with the `desky_desk.clear_height_limits` action before removing the integration, or from the hand controller.

## Usage Examples

### Automation Blueprints

Blueprints turn the common desk automations into a form you fill in. Select a button to
import a blueprint into your Home Assistant, then go to Settings → Automations & scenes →
Blueprints and select it to create an automation. The desk fields only offer Desky entities.

The notification field takes the name of a notify action, such as
`notify.mobile_app_your_phone`. It defaults to `persistent_notification.create`, which shows
the message in Home Assistant itself.

#### Sit/stand reminder

[![Import the sit/stand reminder blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fj0rdsta%2Fha-desky%2Fmain%2Fblueprints%2Fautomation%2Fdesky_desk%2Fsit_stand_reminder.yaml)

Reminds you to stand once the posture sensor has said **Sitting** for a set number of minutes
(60 by default), only between a start and end time and on chosen weekdays. Leave the start and
end time the same to be reminded at any time of day. Time while the desk is unavailable does not
count: the timer starts again when the desk comes back.

#### Scheduled stand

[![Import the scheduled stand blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fj0rdsta%2Fha-desky%2Fmain%2Fblueprints%2Fautomation%2Fdesky_desk%2Fscheduled_stand.yaml)

Moves the desk at set times on chosen weekdays, to one of its presets or, with no preset chosen,
to a height in centimetres. Choose a person so the desk only moves while they are home. Read the
safety warning above before you use it.

#### Collision alert

[![Import the collision alert blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fj0rdsta%2Fha-desky%2Fmain%2Fblueprints%2Fautomation%2Fdesky_desk%2Fcollision_alert.yaml)

Sends a notification naming the desk when its collision sensor turns on, that is when a
commanded movement stopped early or bounced back.

### Dashboard Card
```yaml
type: entities
title: Standing Desk
entities:
  - entity: cover.desky_desk
    name: Desk Control
  - entity: number.desky_desk_height
    name: Current Height
  - type: section
    label: Manual Controls
  - entity: button.desky_desk_move_up
    name: Move Up
  - entity: button.desky_desk_move_down
    name: Move Down
  - type: section
    label: Presets
  - entity: button.desky_desk_preset_1
    name: Sitting
  - entity: button.desky_desk_preset_2
    name: Standing
  - entity: button.desky_desk_preset_3
    name: High Standing
  - entity: button.desky_desk_preset_4
    name: Storage
  - type: section
    label: Status
  - entity: binary_sensor.desky_desk_collision_detected
    name: Collision Status
```

### Sitting and Standing Time

The posture sensor reports **Standing** once the desk stops at or above the standing threshold
(95 cm unless changed in [Options](#options)), and **Sitting** once it stops below it. A desk
that passes the threshold without stopping does not change the posture.

**Standing time today** and **Sitting time today** count minutes in each posture while the desk
is connected. Time while the desk is unavailable counts towards neither. Both reset at local
midnight and keep their value across Home Assistant restarts on the same day. They are recorded
in long-term statistics, so a statistics graph shows each day's total:

```yaml
type: statistics-graph
title: Sitting and standing
entities:
  - entity: sensor.desky_desk_standing_time_today
    name: Standing
  - entity: sensor.desky_desk_sitting_time_today
    name: Sitting
chart_type: bar
period: day
stat_types:
  - change
days_to_show: 14
```

## Troubleshooting

### Desk Not Found
- Ensure Bluetooth is enabled on your Home Assistant host
- Check that the desk is powered on
- Try moving closer to the desk during setup
- Verify the desk name starts with "Desky"

### Connection Issues
When the connection to the desk drops, its entities become unavailable and the log gets one
warning:

```
The desk at AA:BB:CC:DD:EE:FF is unavailable
```

The integration reconnects as soon as Home Assistant sees the desk advertising again, through
whichever adapter or proxy hears it. If the desk is advertising but refuses the connection,
it retries after 5 seconds, doubling the wait each time up to 2 minutes. Retries are only
logged at debug level (`Could not reconnect to the desk at …, retrying in … seconds`), so a
long outage does not fill the log. Once the desk is back, the log gets one info line:

```
The desk at AA:BB:CC:DD:EE:FF is available again
```

Home Assistant does not run actions on unavailable entities. If the connection drops just as a
command is sent, the command fails with "The desk is not connected"; if the Bluetooth write
fails, it fails with "Could not send the command to the desk", followed by the Bluetooth
error. An automation records either as an error instead of carrying on as if the desk moved.

If the desk stays unavailable:
- Check that it is powered on and in range of an adapter or proxy
- Make sure no phone or other device is connected to it, which can keep Home Assistant out
- Check that a Bluetooth proxy has a free connection slot (see below)
- Try restarting the desk by unplugging it for 10 seconds

### Height sensor not updating?
- The integration supports multiple desk firmware versions with different notification formats
- Enable debug logging in Home Assistant to see which format your desk uses:
  ```yaml
  logger:
    default: info
    logs:
      custom_components.desky_desk: debug
  ```
- Look for "Received notification:" entries in the logs
- If issues persist, please include the notification format from your logs when reporting issues

### ESPHome Bluetooth Proxy
This integration fully supports ESPHome Bluetooth proxies. To use:
1. Set up an ESPHome device with `esp32_ble_tracker` and `bluetooth_proxy`, with
   `active: true` so the proxy can connect to devices
2. The desk will be discovered through the proxy automatically

The desk stays connected, so it holds one of the proxy's connection slots (an ESP32 proxy has
three by default). If every slot is taken by other devices, the desk cannot connect and stays
unavailable, retrying as described above. Free a slot or add another proxy near the desk.

## Technical Details

### Cover Entity Improvements
The cover entity now properly tracks movement direction, preventing Home Assistant from incorrectly disabling up/down buttons. The integration includes:
- Accurate `is_opening` and `is_closing` state tracking
- Automatic stop detection when the desk reaches its target position
- Manual Move Up/Down buttons that bypass any cover restrictions

### BLE Protocol
The integration uses the following BLE commands:
- Handshake: `0xF1 0xF1 0xFE 0x00 0xFE 0x7E` (required for movement control)
- Move Up: `0xF1 0xF1 0x01 0x00 0x01 0x7E`
- Move Down: `0xF1 0xF1 0x02 0x00 0x02 0x7E`
- Stop: `0xF1 0xF1 0x2B 0x00 0x2B 0x7E`
- Move to Height: `0xF1 0xF1 0x1B 0x02 [height_high] [height_low] [checksum] 0x7E`
- Preset 1-4: Various command codes

The desk sends height notifications with height data at bytes 4-5 (little-endian format). Different firmware versions may use different notification headers. The desk requires a handshake command after connection to enable movement controls.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, checks and the pull request process.

## Disclaimer

This integration is **NOT** affiliated with, endorsed by, or supported by Desky or any of its subsidiaries. "Desky" is a trademark of its respective owner(s). This is an independent, community-driven project.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Use of this integration is entirely at your own risk. The authors accept no responsibility for any damage to your desk, property, or person that may occur from using this software.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Home Assistant community for BLE integration examples
- Desky for making great standing desks
- Contributors and testers
