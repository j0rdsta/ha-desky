# Desky Standing Desk for Home Assistant

[![Documentation](https://img.shields.io/badge/docs-j0rdsta.github.io%2Fha--desky-blue)](https://j0rdsta.github.io/ha-desky/)
[![GitHub release](https://img.shields.io/github/v/release/j0rdsta/ha-desky)](https://github.com/j0rdsta/ha-desky/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Quality scale: Silver](https://img.shields.io/badge/quality%20scale-silver-C0C0C0)](https://github.com/j0rdsta/ha-desky/blob/main/custom_components/desky_desk/quality_scale.yaml)
[![Test](https://github.com/j0rdsta/ha-desky/actions/workflows/test.yml/badge.svg)](https://github.com/j0rdsta/ha-desky/actions/workflows/test.yml)
[![Lint](https://github.com/j0rdsta/ha-desky/actions/workflows/lint.yml/badge.svg)](https://github.com/j0rdsta/ha-desky/actions/workflows/lint.yml)
[![Validate](https://github.com/j0rdsta/ha-desky/actions/workflows/validate.yml/badge.svg)](https://github.com/j0rdsta/ha-desky/actions/workflows/validate.yml)
[![codecov](https://codecov.io/gh/j0rdsta/ha-desky/graph/badge.svg)](https://codecov.io/gh/j0rdsta/ha-desky)

Control a [Desky](https://www.desky.com.au) standing desk from Home Assistant over the same
Bluetooth connection the Desky app uses. There's no extra hardware to buy or wire into the desk.

![A Desky desk's device page in Home Assistant, with its controls, sensors and settings](https://raw.githubusercontent.com/j0rdsta/ha-desky/main/docs/assets/screenshot-device.png)

## Features

- Raise, lower and stop the desk, or move it to a height or one of its four presets. The desk is
  a cover entity, so it works in dashboards, scenes and voice assistants.
- Live height in centimetres while the desk moves, whatever unit its display shows.
- A sitting or standing sensor, and today's sitting and standing time, recorded in long-term
  statistics.
- Collision detection for movements commanded from Home Assistant.
- Height limits, lock, LED strip, vibration, collision sensitivity, touch mode and display unit,
  on desks that have them.
- Actions to move to a height and to set or clear height limits.
- Blueprints for a sit/stand reminder, a scheduled stand and a collision alert.
- Stays connected, with changes pushed as they happen, and reconnects on its own through whichever
  adapter or ESPHome Bluetooth proxy hears the desk.
- Diagnostics for bug reports, with the desk's Bluetooth address and serial number redacted.

| Dashboard | Options | Posture history |
| --- | --- | --- |
| ![A dashboard card with the desk's cover, height, presets and posture](https://raw.githubusercontent.com/j0rdsta/ha-desky/main/docs/assets/screenshot-dashboard.png) | ![The desk's options, with the standing threshold](https://raw.githubusercontent.com/j0rdsta/ha-desky/main/docs/assets/screenshot-options.png) | ![A graph of daily sitting and standing time](https://raw.githubusercontent.com/j0rdsta/ha-desky/main/docs/assets/screenshot-posture-history.png) |

## Quick start

You need Home Assistant 2025.10 or newer, a Bluetooth adapter or an ESPHome Bluetooth proxy in
range of the desk, and a Desky desk with Bluetooth. The desk takes one connection at a time, so
close the Desky app on your phone.

1. Add this repository to HACS as a custom repository of type **Integration**:

   [![Open your Home Assistant instance and open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=j0rdsta&repository=ha-desky&category=integration)

   Or in HACS, open the three dots menu, select **Custom repositories** and add
   `https://github.com/j0rdsta/ha-desky`.
2. Download **Desky Standing Desk** in HACS and restart Home Assistant.
3. Power on the desk. Home Assistant discovers it under **Settings → Devices & services**; select
   **Add**. If it is not discovered, select **Add integration**, search for **Desky Standing
   Desk** and pick the desk or enter its Bluetooth address.

## Documentation

The full documentation is at **[j0rdsta.github.io/ha-desky](https://j0rdsta.github.io/ha-desky/)**:

- [Installation](https://j0rdsta.github.io/ha-desky/installation/),
  [configuration](https://j0rdsta.github.io/ha-desky/configuration/) and
  [removal](https://j0rdsta.github.io/ha-desky/removal/): manual installation and options
- [Entities](https://j0rdsta.github.io/ha-desky/entities/) and
  [actions](https://j0rdsta.github.io/ha-desky/actions/): everything the integration adds
- [Use cases](https://j0rdsta.github.io/ha-desky/use-cases/) and
  [blueprints](https://j0rdsta.github.io/ha-desky/blueprints/): dashboards, reminders and
  automations
- [Supported devices and limitations](https://j0rdsta.github.io/ha-desky/supported-devices/),
  including Upsy Desky compatibility
- [Troubleshooting](https://j0rdsta.github.io/ha-desky/troubleshooting/): connection problems,
  Bluetooth proxies, diagnostics and debug logs
- [Protocol notes](https://j0rdsta.github.io/ha-desky/protocol/) for contributors

## Safety

A standing desk is motorised furniture. Before you automate it, read the
[safety guidance](https://j0rdsta.github.io/ha-desky/safety/): only move the desk when someone is
at it, and keep the hand controller within reach.

## Contributing

Bug reports, captures from other desk controllers and pull requests are welcome. See
[CONTRIBUTING.md](https://github.com/j0rdsta/ha-desky/blob/main/CONTRIBUTING.md) for the development setup, checks and pull request process.

## Disclaimer and licence

This is an unofficial integration. It is not affiliated with, endorsed by or supported by Desky,
and "Desky" is a trademark of its owner. Use it at your own risk: the authors accept no
responsibility for damage to your desk, property or person.

Released under the [MIT License](https://github.com/j0rdsta/ha-desky/blob/main/LICENSE).
