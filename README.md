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
- **Cover**: Main control entity for desk movement
- **Number**: Current height in cm (60-130cm range)
- **Buttons**: Four preset position buttons
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

### Automation Example
```yaml
automation:
  - alias: "Morning Standup"
    trigger:
      - platform: time
        at: "09:00:00"
    action:
      - service: desky_desk.move_to_preset
        target:
          entity_id: cover.desky_desk
        data:
          preset: 2  # Standing position

  - alias: "Afternoon Sit"
    trigger:
      - platform: time
        at: "13:00:00"
    action:
      - service: desky_desk.move_to_height
        target:
          entity_id: cover.desky_desk
        data:
          height: 75  # Sitting height in cm
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

### ESPHome Bluetooth Proxy
This integration fully supports ESPHome Bluetooth proxies. To use:
1. Set up an ESPHome device with `esp32_ble_tracker` and `bluetooth_proxy`
2. The desk will be discovered through the proxy automatically

## Technical Details

### BLE Protocol
The integration uses the following BLE commands:
- Move Up: `0xF1 0xF1 0x01 0x00 0x01 0x7E`
- Move Down: `0xF1 0xF1 0x02 0x00 0x02 0x7E`
- Stop: `0xF1 0xF1 0x2B 0x00 0x2B 0x7E`
- Preset 1-4: Various command codes

Height notifications use header `0x98 0x98` with height data at bytes 4-5.

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