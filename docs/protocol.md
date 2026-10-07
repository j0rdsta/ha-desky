# Protocol notes

Notes on the Bluetooth protocol the desk's controller speaks, as the integration uses it. They are
for contributors and for anyone debugging a controller the integration does not handle yet. Some
of it was worked out by observation and may not hold for every controller.

## GATT layout

| Item | UUID |
| --- | --- |
| Desk service | `0000fe60-0000-1000-8000-00805f9b34fb` |
| Write characteristic (commands) | `0000fe61-0000-1000-8000-00805f9b34fb` |
| Notify characteristic (responses) | `0000fe62-0000-1000-8000-00805f9b34fb` |

## Command frames

Commands are written to `0xfe61`. Every frame starts with `F1 F1` and ends with `7E`:

```text
F1 F1 <command> <length> <data…> <checksum> 7E
```

The checksum is the sum of the command, length and data bytes, `& 0xFF`.

| Command | Frame |
| --- | --- |
| Handshake | `F1 F1 FE 00 FE 7E` |
| Move up | `F1 F1 01 00 01 7E` |
| Move down | `F1 F1 02 00 02 7E` |
| Stop | `F1 F1 2B 00 2B 7E` |
| Status | `F1 F1 07 00 07 7E` |
| Preset 1 | `F1 F1 05 00 05 7E` |
| Preset 2 | `F1 F1 06 00 06 7E` |
| Preset 3 | `F1 F1 27 00 27 7E` |
| Preset 4 | `F1 F1 28 00 28 7E` |
| Get height limits | `F1 F1 0C 00 0C 7E` |
| Clear height limits | `F1 F1 23 00 23 7E` |
| Get collision sensitivity | `F1 F1 1D 00 1D 7E` |
| Get lock status | `F1 F1 B2 00 B2 7E` |
| Get vibration | `F1 F1 B3 00 B3 7E` |
| Get vibration intensity | `F1 F1 A4 00 A4 7E` |
| Get light colour | `F1 F1 B4 00 B4 7E` |
| Get lighting on or off | `F1 F1 B5 00 B5 7E` |
| Get brightness | `F1 F1 B6 00 B6 7E` |

### Commands with a value

Settings take one data byte:

```text
F1 F1 <command> 01 <value> <checksum> 7E
```

| Command byte | Setting | Values |
| --- | --- | --- |
| `0x0E` | Display unit | 0 cm, 1 inches |
| `0x19` | Touch mode | 0 one press, 1 press and hold |
| `0x1D` | Collision sensitivity | 1 high, 2 medium, 3 low |
| `0xA4` | Vibration intensity | 0-100 |
| `0xB2` | Lock | 0 unlocked, 1 locked |
| `0xB3` | Vibration | 0 off, 1 on |
| `0xB4` | Light colour | 1-7, see below |
| `0xB5` | Lighting | 0 off, 1 on |
| `0xB6` | Brightness | 0-100 |

Heights take two data bytes, big-endian:

```text
F1 F1 <command> 02 <high> <low> <checksum> 7E
```

- **Move to height** (`0x1B`): the target is always in millimetres, whatever the display unit.
  850 mm is `0x0352`, so the frame is `F1 F1 1B 02 03 52 72 7E`.
- **Upper limit** (`0x21`) and **lower limit** (`0x22`): the limit is in tenths of the desk's
  display unit.

## Waking the desk

The handshake is sent after connecting, which enables movement commands. The controller also
ignores commands while its display is asleep, about a minute after the last touch, and the
handshake wakes it. So the integration writes a handshake in front of every command that moves
the desk or changes a setting. Stop is sent on its own: a moving desk is awake, and a sleeping one
has nothing to stop.

## Notifications

Responses arrive on `0xfe62`.

### Height frames

The desk reports its height in one of two frames, depending on the controller's firmware.

**Movement frame** `98 98 …`: height in bytes 4-5, little-endian.

```text
98 98 00 00 52 03    0x0352 = 850 → 85.0
```

The L-BTMEB95 controller does not send this frame; it reports movement in status frames.

**Status frame** `F2 F2 01 03 …`: height in bytes 4-5, big-endian. Sent in reply to a status
request, and about every 200 ms while the desk moves.

```text
F2 F2 01 03 02 D0    0x02D0 = 720 → 72.0
```

The two frames use opposite byte orders.

### Display units

Both height frames carry tenths of the desk's **display unit**. While the desk shows inches,
`F2 F2 01 03 01 12 …` is 27.4 in, which is 69.6 cm, not 27.4 cm.

The integration reads each frame in the unit the desk last reported (the `0x0E` response),
converts inches with 2.54, and rounds to 0.1 cm. The desk's physical range, 60-130 cm or about
23.6-51.2 in, does not overlap between the units. So a value that is impossible in the reported
unit but plausible in the other is read in the other unit: when the unit is changed on the hand
controller, a frame in the new unit arrives before the unit report. Before the desk has reported a
unit, a value below 55.0 is read as inches.

Height limit responses are decoded the same way.

### Setting responses

Setting responses start with `F2 F2 <command> <length>`:

| Header | Meaning | Values |
| --- | --- | --- |
| `F2 F2 0E 01` | Display unit | 0 cm (`F2 F2 0E 01 00 0F 7E`), 1 inches (`F2 F2 0E 01 01 10 7E`) |
| `F2 F2 19 01` | Touch mode | 0 one press, 1 press and hold |
| `F2 F2 1D 01` | Collision sensitivity | 1 high, 2 medium, 3 low |
| `F2 F2 20 01` | Height limits set | `00` none, `01` upper only, `10` lower only, `11` both |
| `F2 F2 21 02` | Upper limit | Two bytes, big-endian |
| `F2 F2 22 02` | Lower limit | Two bytes, big-endian |
| `F2 F2 A4 01` | Vibration intensity | 0-100 |
| `F2 F2 B2 01` | Lock | 0 unlocked, 1 locked |
| `F2 F2 B3 01` | Vibration | 0 off, 1 on |
| `F2 F2 B4 01` | Light colour | 1 white, 2 red, 3 green, 4 blue, 5 yellow, 6 party mode, 7 off |
| `F2 F2 B5 01` | Lighting | 0 off, 1 on |
| `F2 F2 B6 01` | Brightness | 0-100 |

### The settings block

The desk has no query for a single setting. It sends a block of settings (presets `0x25`-`0x28`,
unit `0x0E`, touch mode `0x19`, `0x17`, sensitivity `0x1D`) in reply to a status request that
follows a handshake. It also sends the block unprompted when the unit is changed on the hand
controller. It does not confirm a unit or touch mode change on its own, so the integration asks
for the block after changing either.

A desk connected within about a second of powering up ignores the settings request, and sends
`F2 F2 10 02 02 51` and `F2 F2 0F 02 00 07` instead. Their meaning is unknown.

## Device Information service

On connecting, the integration reads the standard Device Information service (`0x180A`) for the
device page:

| Characteristic | UUID |
| --- | --- |
| Manufacturer name | `00002a29-0000-1000-8000-00805f9b34fb` |
| Model number | `00002a24-0000-1000-8000-00805f9b34fb` |
| Serial number | `00002a25-0000-1000-8000-00805f9b34fb` |
| Hardware revision | `00002a27-0000-1000-8000-00805f9b34fb` |
| Firmware revision | `00002a26-0000-1000-8000-00805f9b34fb` |
| Software revision | `00002a28-0000-1000-8000-00805f9b34fb` |

Some controllers fill these with placeholders such as `Model Number`. The integration ignores
those and falls back to *Desky* and *Standing Desk*.
