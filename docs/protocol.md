# Protocol notes

The desk controller's Bluetooth protocol, as the integration uses it, for contributors and anyone
debugging a controller the integration does not handle yet. Some of it was worked out by
observation and may not hold for every controller.

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
| Get lock status | `F1 F1 B2 00 B2 7E` |
| Get vibration | `F1 F1 B3 00 B3 7E` |
| Get light colour | `F1 F1 B4 00 B4 7E` |
| Get lighting on or off | `F1 F1 B5 00 B5 7E` |
| Get brightness | `F1 F1 B6 00 B6 7E` |

Versions before 2.0.0 also sent `F1 F1 A4 00 A4 7E` for the vibration intensity. The desk never
answered it, and the official app neither sends it nor sets the intensity, so it is no longer
sent.

Versions before 2.0.0 also sent `F1 F1 1D 00 1D 7E` for the collision sensitivity. On a real desk
its reply disagreed with the settings block, and the official app never sends it. The
integration now reads the sensitivity from the settings block only.

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
  display unit. The desk accepts 60-124 cm, or 24-48 in, and ignores a limit outside that range.
  It stores whole units, so the integration sends a limit rounded to a whole cm or a whole inch.

## Waking the desk

The handshake is sent after connecting, which enables movement commands. The controller also ignores
commands once its display sleeps, about a minute after the last touch. The handshake wakes it, so
the integration writes a handshake in front of every command that moves the desk or changes a
setting. Stop is sent on its own: a moving desk is awake, and a sleeping one has nothing to stop.

## Command timing

The integration sends each command with the repeats and spacing of the official Desky app
(Android app 4.5.4). The timings were read from the decompiled app. Times count from the first
frame of the command.

| Command | Frames |
| --- | --- |
| Lock, vibration, lighting on or off | Handshake, then the setting at 200 ms and 400 ms |
| Collision sensitivity, touch mode | Handshake, then the setting once at 500 ms |
| LED colour, brightness | Handshake, then the setting at 0 and 100 ms |
| Display unit | Handshake, then the setting at 0, 100 and 200 ms |
| Clear height limits | Handshake, then clear at 0 and 200 ms, then the limit query |
| Set a height limit | Handshake, then clear, upper limit and lower limit, each twice, 50 ms apart, then the limit query |
| Stop | Stop at 0 and 50 ms |
| Move to height | Handshake and stop, then the target at 200 ms and 300 ms. In press-and-hold touch mode, the target again every 100 ms until the desk is there |
| Move up, move down | Handshake and the command, then the command again every 100 ms |
| Presets | Handshake and the command. In press-and-hold touch mode, the command again every 100 ms |
| Connecting | Handshake and status, then each settings query 200 ms apart |

- The app sends colour, brightness, unit and limits without a handshake. The integration keeps
  the handshake in front of them, because the desk ignores commands while its display sleeps.
- The desk does not confirm a unit, touch mode or sensitivity change, so the integration asks
  for its settings at the end of the change: straight after the unit or touch mode, and 500 ms
  after the sensitivity, as the app does. Asked any sooner, the desk can still report the old
  level.
- **Height limits.** While a limit is set, the desk only accepts a tighter one: with the upper
  limit at 110 cm, 105 cm is applied but 124 cm is ignored, without an error. So, as the app does,
  the integration clears both limits first and then sets both. Setting one limit sends the other
  one again, exactly as the desk reported it, so it is kept. If the desk has not yet reported
  which limits are set and their values, nothing is cleared, so no limit is lost; a looser limit
  then needs another try once the desk has reported them. Limit changes go out one at a time,
  and the limits just sent count as known at once, so two changes in a row keep each other.
- **Held commands.** Move up and Move down are held buttons in every touch mode, as in the app:
  one command only nudges the desk, about 0.8 cm. In press-and-hold touch mode, presets and move
  to height are held too: one command only nudges the desk there. The integration holds a
  command by repeating it every 100 ms. The repeats end when you stop the desk, when it stops
  moving (three readings in a row at the same height), on a collision, when it has not moved
  within 5 seconds, on a new command, on a disconnect, or after 60 seconds. A move to height
  also stops repeating once the desk is within 0.5 cm of the target. In one-press mode, or while
  the touch mode is unknown, a preset or a move to height is sent as in the table, and one
  preset command runs the desk all the way.
- **Repeats are not confirmed.** The desk takes a held command as released as soon as the
  repeats arrive unevenly. Waiting for each write's confirmation through a Bluetooth proxy takes
  70-700 ms, which made a held preset stop part way. So the repeats go out without waiting for
  confirmation, evenly 100 ms apart, as the app writes them. The first command, the stops and
  every setting still wait for it. While a command is held, the 30-second status poll sends
  nothing, so it cannot hold up the repeats.
- A pause never holds up a stop. A stop, a new movement command or a disconnect cancels the
  movement frames still due. A disconnect also cancels any setting still being sent.
- Every other write waits for the desk to confirm it, so a write that fails shows as an error.
  If a write is slow, the frames after it move later and keep their spacing. Through a Bluetooth proxy
  a write takes about 70-130 ms, so frames 50 ms apart come out about 90 ms apart.
- A write already on its way to the desk is never cut off: a stop waits for it to finish, since
  the Bluetooth stack rejects a write while another is in progress. A write the desk has not
  confirmed within 5 seconds fails, so a stop never waits longer than that behind it.
- Limits are forgotten when the desk disconnects, as they can change on the hand controller
  meanwhile. Until the desk reports them again, setting a limit sends only the new one.

## Notifications

Responses arrive on `0xfe62`.

### Height frames

The desk reports its height in one of two frames, depending on the controller's firmware.

**Movement frame** `98 98 …`: height in bytes 4-5, little-endian.

```text
98 98 00 00 52 03    0x0352 = 850 → 85.0
```

The L-BTMEB95 controller does not send this frame; it reports movement in status frames.

**Status frame** `F2 F2 01 03 …`: height in bytes 4-5, big-endian, unlike the movement frame.
Sent in reply to a status request, and about every 200 ms while the desk moves.

```text
F2 F2 01 03 02 D0    0x02D0 = 720 → 72.0
```

### Display units

Both height frames carry tenths of the desk's display unit. While the desk shows inches,
`F2 F2 01 03 01 12 …` is 27.4 in, which is 69.6 cm, not 27.4 cm.

The integration reads each frame in the unit the desk last reported (the `0x0E` response),
converts inches with 2.54, and rounds to 0.1 cm. The desk's physical range, 60-130 cm or about
23.6-51.2 in, does not overlap between the units. When the unit is changed on the hand controller,
a frame in the new unit arrives before the unit report, so a value that is impossible in the
reported unit but plausible in the other is read in the other unit. Before the desk has reported a
unit, a value below 55.0 is read as inches.

Height limit responses are decoded the same way, after one correction. The desk reports a limit a
tenth low: 124.0 cm comes back as 1239. Like the official app, the integration adds one tenth to a
limit value that is not a multiple of 5. Height frames are not corrected.

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
| `F2 F2 B2 01` | Lock | 0 unlocked, 1 locked |
| `F2 F2 B3 01` | Vibration | 0 off, 1 on |
| `F2 F2 B4 01` | Light colour | 1 white, 2 red, 3 green, 4 blue, 5 yellow, 6 party mode, 7 off. 0 also means off: the official app sets it to turn the LED off |
| `F2 F2 B5 01` | Lighting | 0 off, 1 on |
| `F2 F2 B6 01` | Brightness | 0-100 |

### The settings block

The desk has no query for the display unit or touch mode on their own. It sends a block of settings
(presets `0x25`-`0x28`, unit `0x0E`, touch mode `0x19`, an unknown `0x17`, sensitivity `0x1D`) in
reply to a status request that follows a handshake. It also sends the block unprompted when the unit
is changed on the hand controller. It does not confirm a change to the unit, touch mode or
collision sensitivity, so the integration asks for the block after changing any of them.

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
