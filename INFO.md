# Desky Standing Desk

Control your Desky standing desk via Bluetooth Low Energy (BLE) in Home Assistant.

## Features

- 🔼 **Movement Control** - Raise, lower, and stop desk movement
- 📏 **Height Monitoring** - Real-time height sensor in centimeters
- 🎯 **Preset Positions** - Quick access to 4 saved positions
- 💥 **Collision Detection** - Safety sensor for obstacle detection
- 🏠 **Full Integration** - Works with automations and scripts
- 📡 **ESPHome Support** - Compatible with Bluetooth proxies

## Quick Start

1. Install via HACS
2. Add Integration in Settings
3. Select your desk from Bluetooth scan
4. Start controlling your desk!

## Supported Entities

- **Cover** - Main desk control (open/close/position)
- **Number** - Current height display and control
- **Buttons** - Four preset position buttons
- **Binary Sensor** - Collision detection

## Example Automation

⚠️ **Safety Note**: Always include presence detection in desk automations to prevent unattended movement!

```yaml
automation:
  - alias: "Hourly Standing Reminder"
    trigger:
      - platform: time_pattern
        minutes: "0"
    condition:
      - condition: time
        after: "09:00:00"
        before: "17:00:00"
      # IMPORTANT: Add presence detection for safety
      - condition: state
        entity_id: binary_sensor.office_presence
        state: "on"
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "Time to stand up!"
          data:
            actions:
              - action: "RAISE_DESK"
                title: "Raise desk"
```

## Requirements

- Home Assistant 2023.12.0+
- Bluetooth adapter or ESPHome proxy
- Desky desk with Bluetooth

For detailed documentation, visit the [GitHub repository](https://github.com/j0rdsta/ha-desky).