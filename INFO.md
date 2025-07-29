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
    action:
      - service: desky_desk.move_to_preset
        data:
          preset: 2  # Standing position
```

## Requirements

- Home Assistant 2023.12.0+
- Bluetooth adapter or ESPHome proxy
- Desky desk with Bluetooth

For detailed documentation, visit the [GitHub repository](https://github.com/your-github-username/ha-desky).