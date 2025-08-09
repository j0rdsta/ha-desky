# Desky Standing Desk Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Control your Desky standing desk via Bluetooth Low Energy (BLE) in Home Assistant. This integration supports ESPHome Bluetooth proxies and works with all Home Assistant installation types.

## Features

### Core Features
- **Movement Control**: Raise, lower, and stop desk movement
- **Height Sensor**: Real-time height monitoring in centimeters
- **Preset Positions**: Move to any of 4 saved preset positions
- **Collision Detection**: Binary sensor for collision events
- **Cover Entity**: Control desk as a cover (0% = minimum height, 100% = maximum height)

### Supported Entities
- **Cover**: Main control entity for desk movement with proper direction tracking
- **Number**: Current height in cm (60-130cm range)
- **Buttons**: Four preset position buttons + Move Up/Down manual controls
- **Binary Sensor**: Collision detection

### Services
- `desky_desk.move_to_height`: Move to specific height in cm
- `desky_desk.move_to_preset`: Move to preset position (1-4)
- `desky_desk.set_position_limit`: Set min/max height limits

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

## Installation

### HACS (Recommended)
1. Open HACS in Home Assistant
2. Click the three dots menu and select "Custom repositories"
3. Add this repository URL: `https://github.com/j0rdsta/ha-desky`
4. Select "Integration" as the category
5. Click "Add"
6. Search for "Desky Desk" and install

### Manual Installation
1. Copy the `custom_components/desky_desk` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "Desky Desk"
4. The integration will scan for nearby Desky desks
5. Select your desk from the list or enter the Bluetooth address manually
6. Follow the setup flow

## Requirements

- Home Assistant 2023.12.0 or newer
- Bluetooth adapter or ESPHome Bluetooth proxy
- Desky standing desk with Bluetooth support

## Usage Examples

### Automation Examples

#### ⚠️ Basic Example (Add Safety Features!)
```yaml
# WARNING: These basic examples lack safety features!
# See "Safer Automation Example" below for recommended approach

automation:
  - alias: "Morning Standup - UNSAFE"
    trigger:
      - platform: time
        at: "09:00:00"
    action:
      - service: desky_desk.move_to_preset
        target:
          entity_id: cover.desky_desk
        data:
          preset: 2  # Standing position
```

#### ✅ Safer Automation Example (Recommended)
```yaml
automation:
  - alias: "Safe Morning Standup"
    trigger:
      - platform: time
        at: "09:00:00"
    condition:
      # CRITICAL: Only move desk if someone is present
      - condition: state
        entity_id: binary_sensor.office_presence  # Your presence sensor
        state: "on"
      # Ensure they've been present for at least 1 minute
      - condition: state
        entity_id: binary_sensor.office_presence
        state: "on"
        for: "00:01:00"
      # Only on weekdays
      - condition: time
        weekday:
          - mon
          - tue
          - wed
          - thu
          - fri
    action:
      # Send notification first
      - service: notify.mobile_app_your_phone
        data:
          message: "Desk will move to standing position in 10 seconds"
          data:
            tag: "desk_movement"
      # Wait for user to clear the area
      - delay: "00:00:10"
      # Final safety check
      - condition: state
        entity_id: binary_sensor.office_presence
        state: "on"
      # Move desk
      - service: desky_desk.move_to_preset
        target:
          entity_id: cover.desky_desk
        data:
          preset: 2  # Standing position

  - alias: "Safe Sitting Reminder"
    trigger:
      # Trigger after standing for 45 minutes
      - platform: state
        entity_id: sensor.desky_desk_height
        to: "110"  # Standing height
        for: "00:45:00"
    condition:
      # Only if someone is at the desk
      - condition: state
        entity_id: binary_sensor.office_presence
        state: "on"
      # During work hours
      - condition: time
        after: "08:00:00"
        before: "18:00:00"
    action:
      # Suggest sitting, don't force it
      - service: notify.mobile_app_your_phone
        data:
          message: "You've been standing for 45 minutes. Consider sitting?"
          data:
            tag: "desk_reminder"
            actions:
              - action: "MOVE_TO_SITTING"
                title: "Move to sitting position"
              - action: "DISMISS"
                title: "Keep standing"
```

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
  - entity: binary_sensor.desky_desk_collision
    name: Collision Status
```

### Advanced Safety Automation Example

This comprehensive example demonstrates multiple safety layers for desk automation:

```yaml
# Input helpers for user preferences (create in UI under Helpers)
input_boolean:
  desk_automation_enabled:
    name: "Desk Automation Enabled"
    icon: mdi:desk
    
input_number:
  desk_standing_duration:
    name: "Standing Duration (minutes)"
    min: 15
    max: 120
    step: 15
    unit_of_measurement: "min"

# Presence detection using multiple methods
binary_sensor:
  - platform: template
    sensors:
      office_definitely_occupied:
        friendly_name: "Office Definitely Occupied"
        device_class: presence
        value_template: >
          {{ is_state('binary_sensor.office_motion', 'on') 
             and is_state('binary_sensor.desk_chair_occupied', 'on')
             and is_state('device_tracker.work_laptop', 'home') }}

automation:
  # Main standing desk automation with multiple safety checks
  - alias: "Ultra-Safe Desk Movement Control"
    trigger:
      - platform: time_pattern
        minutes: "/30"  # Check every 30 minutes
    condition:
      # Master enable switch
      - condition: state
        entity_id: input_boolean.desk_automation_enabled
        state: "on"
      # Multiple presence confirmations
      - condition: state
        entity_id: binary_sensor.office_definitely_occupied
        state: "on"
        for: "00:02:00"  # Present for at least 2 minutes
      # Not in a meeting (if calendar integrated)
      - condition: state
        entity_id: calendar.work
        state: "off"
      # Work hours only
      - condition: time
        after: "08:00:00"
        before: "18:00:00"
        weekday: [mon, tue, wed, thu, fri]
    action:
      # Determine if we should stand or sit
      - choose:
          # Time to stand
          - conditions:
              - condition: numeric_state
                entity_id: sensor.desky_desk_height
                below: 85  # Currently sitting
              - condition: template
                value_template: >
                  {{ (now() - states.sensor.desky_desk_height.last_changed).seconds > 1800 }}
            sequence:
              # Pre-movement safety protocol
              - service: light.turn_on
                target:
                  entity_id: light.office_lights
                data:
                  flash: short
              - service: notify.mobile_app_your_phone
                data:
                  message: "Preparing to raise desk. Clear the area!"
                  data:
                    tag: "desk_safety"
                    timeout: 30
                    actions:
                      - action: "CANCEL_MOVEMENT"
                        title: "Cancel"
              - delay: "00:00:15"
              # Final safety checks
              - condition: state
                entity_id: binary_sensor.office_definitely_occupied
                state: "on"
              - condition: state
                entity_id: binary_sensor.desky_desk_collision
                state: "off"
              # Move to standing
              - service: cover.open_cover
                target:
                  entity_id: cover.desky_desk
              # Monitor for collisions during movement
              - wait_template: "{{ is_state('cover.desky_desk', 'open') }}"
                timeout: "00:00:30"
                continue_on_timeout: false
              - service: notify.mobile_app_your_phone
                data:
                  message: "Desk raised to standing position"
                  
          # Time to sit
          - conditions:
              - condition: numeric_state
                entity_id: sensor.desky_desk_height
                above: 100  # Currently standing
              - condition: template
                value_template: >
                  {{ (now() - states.sensor.desky_desk_height.last_changed).seconds > 
                     (states('input_number.desk_standing_duration') | int * 60) }}
            sequence:
              # Sitting reminder only - no automatic lowering for safety
              - service: notify.mobile_app_your_phone
                data:
                  title: "Time to Sit"
                  message: "You've been standing for {{ states('input_number.desk_standing_duration') }} minutes"
                  data:
                    tag: "desk_reminder"
                    persistent: true
                    actions:
                      - action: "LOWER_DESK"
                        title: "Lower to sitting"
                      - action: "SNOOZE_15"
                        title: "Remind in 15 min"

  # Emergency stop automation
  - alias: "Desk Emergency Stop on Collision"
    trigger:
      - platform: state
        entity_id: binary_sensor.desky_desk_collision
        to: "on"
    action:
      - service: cover.stop_cover
        target:
          entity_id: cover.desky_desk
      - service: notify.mobile_app_your_phone
        data:
          title: "⚠️ Desk Collision Detected!"
          message: "Desk movement stopped for safety"
          data:
            priority: high
            tag: "desk_emergency"

  # Automation safety disable when away
  - alias: "Disable Desk Automation When Away"
    trigger:
      - platform: state
        entity_id: person.you
        to: "not_home"
    action:
      - service: input_boolean.turn_off
        target:
          entity_id: input_boolean.desk_automation_enabled
      - service: notify.mobile_app_your_phone
        data:
          message: "Desk automation disabled - you're away from home"
```

## Troubleshooting

### Desk Not Found
- Ensure Bluetooth is enabled on your Home Assistant host
- Check that the desk is powered on
- Try moving closer to the desk during setup
- Verify the desk name starts with "Desky"

### Connection Issues
- The integration automatically reconnects if connection is lost
- Check Home Assistant logs for detailed error messages
- Ensure no other device is connected to the desk
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
1. Set up an ESPHome device with `esp32_ble_tracker` and `bluetooth_proxy`
2. The desk will be discovered through the proxy automatically

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

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

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