# Supported devices and limitations

## Supported desks

The integration works with Desky desks whose controller has Bluetooth built in. Such a desk
advertises a Bluetooth name that starts with `Desky`, which is how Home Assistant discovers it.

Desky desks use more than one controller, and controllers differ in firmware. The integration
handles the differences it knows about:

- **Height reports.** Some controllers report the height in a dedicated movement frame, others
  only in their status frame. Both are read. See [Protocol notes](protocol.md#height-frames).
- **Display unit.** The desk reports heights in the unit its display shows, centimetres or
  inches. The integration converts to centimetres, so entities and actions always use cm.
- **Features.** On connecting, the integration asks the desk for its lighting, vibration, lock,
  collision sensitivity and height limit settings. Every entity is created whatever the desk
  answers; for a feature the desk does not report, the entity shows unknown or a default value.

The integration has been developed against an L-BTMEB95 desk controller. If you have a different
Desky controller and something does not work, [open an issue](https://github.com/j0rdsta/ha-desky/issues)
with a debug log (see [Troubleshooting](troubleshooting.md#debug-logging)).

Desks from other brands that use the same Bluetooth controller may work, but are not tested and
are not discovered automatically unless their name starts with `Desky`.

## Upsy Desky

!!! warning "Disconnect an Upsy Desky first"
    If an [Upsy Desky](https://github.com/tjhorner/upsy-desky) is installed between the desk's
    control box and its hand controller, disconnect it before using this integration. Upsy Desky
    intercepts the RJ45 connection to the control box, while this integration talks to the
    controller over Bluetooth, and the two cannot work at the same time. See
    [issue #4](https://github.com/j0rdsta/ha-desky/issues/4).

## Known limitations

- **One connection at a time.** The desk accepts one Bluetooth connection at a time, and the
  integration keeps its connection open. If Home Assistant cannot connect, close the Desky app on
  your phone.
- **Proxy connection slots.** The open connection uses one of a Bluetooth proxy's connection
  slots for as long as the desk is loaded. See
  [Troubleshooting](troubleshooting.md#esphome-bluetooth-proxies).
- **Fixed height range.** Heights are limited to 60-130 cm, the range of a typical Desky desk.
  The cover position maps 0 % to 60 cm and 100 % to 130 cm, whatever the desk's own range or
  height limits.
- **Presets are recalled, not saved.** The four preset buttons move the desk to the heights saved
  on the hand controller. Save or change a preset on the hand controller.
- **Collision detection is inferred.** The desk does not report collisions over Bluetooth. The
  integration infers one when a commanded movement stops early or bounces back, so movements
  made with the hand controller are never reported as collisions. The desk's own anti-collision
  system is what stops the desk. See [Safety](safety.md).
- **Settings changed elsewhere.** Settings such as the lock, lighting and vibration are read when
  the desk connects, and updated when you change them from Home Assistant. A change made on the
  desk or in the Desky app may not appear until the desk reconnects.
- **The desk's display wakes up.** The desk ignores commands while its display is asleep, so the
  integration wakes it before each command that moves the desk or changes a setting. The display
  lights up as it would if you touched the hand controller.
