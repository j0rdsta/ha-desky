# Entities

Every desk is one device in Home Assistant, and all its entities belong to that device. Entity
names are translated and prefixed with the device name, which is the desk's Bluetooth name. The
entity IDs on this page are for a desk named "Desky Desk"; yours follow your desk's name.
Entities created by earlier versions of the integration keep their existing entity IDs.

Every entity is enabled by default. All of them are unavailable while the desk is not connected.

Heights are always in centimetres, whatever unit the desk's display shows, except for the
**Height display** sensor, which follows the display unit.

Not every desk has every feature. Every entity is created whatever the desk supports; for a
feature the desk does not report, the entity shows unknown or a default value (see
[Supported devices](supported-devices.md#supported-desks)).

## Summary

The category column shows where Home Assistant lists the entity on the device page: **Controls**
and **Sensors**, **Configuration** or **Diagnostic**.

| Entity | Entity ID | Platform | Unit | Category |
| --- | --- | --- | --- | --- |
| Desky Desk | `cover.desky_desk` | Cover | % | Controls |
| Height | `number.desky_desk_height` | Number | cm | Controls |
| Preset 1 – Preset 4 | `button.desky_desk_preset_1` … `_4` | Button | | Controls |
| Move up | `button.desky_desk_move_up` | Button | | Controls |
| Move down | `button.desky_desk_move_down` | Button | | Controls |
| LED strip | `light.desky_desk_led_strip` | Light | | Controls |
| Lock | `switch.desky_desk_lock` | Switch | | Controls |
| Height display | `sensor.desky_desk_height_display` | Sensor | cm or in | Sensors |
| Posture | `sensor.desky_desk_posture` | Sensor | | Sensors |
| Standing time today | `sensor.desky_desk_standing_time_today` | Sensor | min | Sensors |
| Sitting time today | `sensor.desky_desk_sitting_time_today` | Sensor | min | Sensors |
| Upper height limit | `number.desky_desk_upper_height_limit` | Number | cm | Configuration |
| Lower height limit | `number.desky_desk_lower_height_limit` | Number | cm | Configuration |
| Vibration intensity | `number.desky_desk_vibration_intensity` | Number | % | Configuration |
| Vibration | `switch.desky_desk_vibration` | Switch | | Configuration |
| Collision sensitivity | `select.desky_desk_collision_sensitivity` | Select | | Configuration |
| Touch mode | `select.desky_desk_touch_mode` | Select | | Configuration |
| Display unit | `select.desky_desk_display_unit` | Select | | Configuration |
| Collision detected | `binary_sensor.desky_desk_collision_detected` | Binary sensor | | Diagnostic |
| LED color | `sensor.desky_desk_led_color` | Sensor | | Diagnostic |
| Vibration intensity display | `sensor.desky_desk_vibration_intensity_display` | Sensor | % | Diagnostic |

## Movement

### Desk (cover)

The main control. The cover takes the device's name, so it is called after the desk.

- **Open** raises the desk, **close** lowers it and **stop** stops it.
- **Position** maps the fixed range of 60-130 cm to 0-100 %: 0 % is 60 cm and 100 % is 130 cm,
  whatever the desk's own range or height limits. Setting a position moves the desk to the
  matching height.
- The cover is **closed** at 0 %, that is at 60 cm or below.
- It shows **opening** or **closing** while a movement commanded from Home Assistant is under
  way, in the direction of that movement, so Home Assistant keeps the other direction's button
  available. Movements made with the hand controller update the position but not the opening or
  closing state.

### Height

The desk's current height in centimetres, to 0.1 cm, from 60 to 130 cm. Setting a value moves
the desk to that height. To move to a height in an automation and get an error for a height
outside the desk's limits, use the [`move_to_height` action](actions.md#move-to-height).

### Preset 1 – Preset 4

Moves the desk to the height saved in that preset on the hand controller. Presets are saved and
changed on the hand controller; the integration recalls them.

### Move up and Move down

Starts the desk moving up or down, the same as opening or closing the cover. Stop it with the
cover's stop. The buttons stay available whatever the cover's state.

### Collision detected

On when a movement commanded from Home Assistant stops early or bounces back, which the
integration reads as a collision. It turns off on its own after 10 seconds, sooner if a later
commanded movement runs normally more than 2 seconds after the collision, and when the desk
disconnects. Movements made
with the hand controller are never reported as collisions. The desk does not report collisions
over Bluetooth; this sensor is inferred, and is information rather than a safety device (see
[Safety](safety.md)).

Device class: problem.

## Height and posture

### Height display

The desk's height in the unit its display shows: centimetres or inches, to 0.1. Attributes:

| Attribute | Meaning |
| --- | --- |
| `height_cm` | The height in centimetres |
| `upper_limit_cm`, `lower_limit_cm` | The height limits in centimetres, present while at least one limit is set; a limit that is not set is `null` |

### Posture

**Sitting** or **Standing**, from the height the desk stops at. The desk counts as standing when
it stops at or above the standing threshold (95 cm unless changed in the
[options](configuration.md#options)), and as sitting when it stops below it.

The posture follows the height only once the desk has stayed at the same height for 2 seconds
and no movement commanded from Home Assistant is under way, so a desk that passes the threshold
without stopping does not change posture. After the desk connects, the state is unknown until
the desk has reported a height and stayed at it for those 2 seconds.

Device class: enum, with the states `sitting` and `standing`. Use these values in automations.

### Standing time today and Sitting time today

Minutes spent in each posture today, counted while the desk is connected. Time while the desk is
disconnected, or before its posture is known, counts towards neither.

- A change of posture counts from when the desk stopped in the new posture.
- Both totals reset at local midnight, including on a day whose midnight a clock change skips.
- They keep their value across a Home Assistant restart or a reload of the desk on the same day.
- They update every minute and whenever the desk reports a change.

Device class: duration, state class: total, with `last_reset` set to the start of the local day.
They are recorded in long-term statistics, so a statistics graph can show each day's total (see
[Use cases](use-cases.md#track-sitting-and-standing-time)).

## Desk settings

### Upper height limit and Lower height limit

The highest and lowest heights the desk will move to, stored on the desk's control box. From 60
to 130 cm in steps of 1 cm. Setting a value sets the limit on the desk, then reads the limits
back, so the entity shows what the desk reports. A limit that is not set shows as unknown.

Attribute `limits_enabled`: true while at least one limit is set.

To set or clear limits from an automation, use the [actions](actions.md), which also check that
the upper limit stays above the lower one.

### Vibration intensity

The strength of the desk's vibration, from 0 to 100 %. Setting it reads the value back from the
desk.

### Vibration

Turns the desk's vibration on or off. Attribute `intensity`: the vibration intensity in %, when
the desk has reported it.

### Lock

Locks the desk's controls. Turn it off to unlock them.

### Collision sensitivity

How sensitive the desk's own anti-collision system is: **High**, **Medium** or **Low**.

### Touch mode

The hand controller's touch mode: **One press** or **Press and hold**. The desk
does not confirm the change, so the integration asks for its settings again after changing it.

### Display unit

The unit the desk's display shows: **cm** or **in**. The integration converts heights to
centimetres either way; only the **Height display** sensor follows this setting. The integration
asks for the desk's settings again after changing it, and also picks up a change made on the
hand controller.

## LED strip

### LED strip (light)

Turns the desk's LED strip on or off and sets its brightness. The colours are effects: **White**,
**Red**, **Green**, **Blue**, **Yellow** and **Party mode**.

Turning the light on without an effect restores the last colour you chose other than party mode,
which is kept across restarts. Attribute `color_name`: the current colour.

### LED color

The LED strip's current colour as text: White, Red, Green, Blue, Yellow, Party mode or Off, and
Unknown until the desk has reported it. Attributes:

| Attribute | Meaning |
| --- | --- |
| `color_value` | The colour code the desk reports, 1-7 |
| `brightness` | The brightness in %, as the desk reports it |
| `lighting_enabled` | Whether the LED strip is on |

### Vibration intensity display

The vibration intensity in %, as a sensor, or 0 until the desk has reported it. Attribute
`vibration_enabled`: whether vibration is on.
