# Desky Standing Desk for Home Assistant

A custom integration that controls a Desky standing desk from Home Assistant over Bluetooth Low
Energy. It talks to the Bluetooth controller built into the desk, so no extra hardware goes on
the desk.

!!! warning "Unofficial integration"
    This project is not affiliated with, endorsed by or supported by Desky. A standing desk is
    motorised furniture: read [Safety](safety.md) before you automate it.

## What it does

- Raises, lowers and stops the desk, and moves it to a height or to one of its four presets.
- Reports the desk's height as it moves, in centimetres, whatever unit the desk's display shows.
- Shows the desk as a cover entity, so it works in dashboards, scenes and voice assistants.
- Tracks whether you are sitting or standing from the height the desk stops at, and counts the
  minutes in each posture every day.
- Detects when the desk stops or bounces back during a movement it was commanded to make, and
  reports it as a collision.
- Controls the settings the desk exposes over Bluetooth: height limits, collision sensitivity,
  touch mode, display unit, lock, vibration and the LED strip. Not every desk has every feature.
- Reconnects on its own when the desk comes back into range, through whichever Bluetooth adapter
  or ESPHome Bluetooth proxy hears it.

The integration keeps a connection open to the desk and gets height and settings changes pushed
to it as they happen. See [How data updates](data-updates.md).

## Requirements

- Home Assistant 2025.10 or newer.
- A Bluetooth adapter that Home Assistant can use, or an
  [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html) with active
  connections enabled, within range of the desk.
- A Desky desk with a Bluetooth controller. It advertises a Bluetooth name that starts with
  `Desky`. See [Supported devices](supported-devices.md).

## Get started

1. [Install](installation.md) the integration through HACS or by hand.
2. [Add the desk](configuration.md) in **Settings → Devices & services**.
3. See what the desk gives you on the [entities](entities.md) and [actions](actions.md) pages.
4. Look at the [use cases](use-cases.md) and [blueprints](blueprints.md) for ideas, and the
   [safety guidance](safety.md) before you write automations that move the desk.

## Quality scale

The integration meets the **Silver** tier of the Home Assistant
[Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/).
Home Assistant only checks the scale for its built-in integrations, so the status of each rule,
and the reason for every exemption, is recorded in
[`quality_scale.yaml`](https://github.com/j0rdsta/ha-desky/blob/main/custom_components/desky_desk/quality_scale.yaml).
